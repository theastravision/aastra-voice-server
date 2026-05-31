/**
 * WebSocket PCM voice client for /ws/voice (STT partial/final, LLM deltas, streaming TTS).
 */
(function (global) {
  const TARGET_SR = 16000;
  const CHUNK_MS = 100;
  const SAMPLES_PER_CHUNK = Math.floor(TARGET_SR * CHUNK_MS / 1000);
  const DEFAULT_SILENCE_END_MS = 900;
  const MIN_SPEECH_MS = 500;
  const END_COOLDOWN_MS = 1200;
  const BARGE_IN_DEBOUNCE_MS = 300;
  const PLAYBACK_PREBUFFER_MS = 250;
  const PLAYBACK_MERGE_MS = 150;
  const CROSSFADE_MS = 8;

  function pcmBytesToFloat32(pcmBytes) {
    const n = pcmBytes.byteLength / 2;
    const view = new DataView(pcmBytes);
    const floats = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      floats[i] = view.getInt16(i * 2, true) / 32768;
    }
    return floats;
  }

  function applyCrossfade(samples, fadeSamples) {
    const n = samples.length;
    if (fadeSamples <= 0 || n < fadeSamples * 2) return samples;
    for (let i = 0; i < fadeSamples; i++) {
      const gain = i / fadeSamples;
      samples[i] *= gain;
      samples[n - 1 - i] *= gain;
    }
    return samples;
  }

  class PcmPlaybackQueue {
    constructor(client) {
      this._client = client;
      this._pending = [];
      this._pendingBytes = 0;
      this._draining = false;
      this._playbackStarted = false;
    }

    reset() {
      this._pending = [];
      this._pendingBytes = 0;
      this._playbackStarted = false;
    }

    enqueue(arrayBuffer) {
      if (!arrayBuffer || !arrayBuffer.byteLength) return;
      this._pending.push(new Uint8Array(arrayBuffer));
      this._pendingBytes += arrayBuffer.byteLength;
      if (!this._draining) {
        this._draining = true;
        void this._drainLoop();
      }
    }

    _takeBytes(n) {
      const out = new Uint8Array(n);
      let offset = 0;
      while (offset < n && this._pending.length) {
        const head = this._pending[0];
        const need = n - offset;
        if (head.length <= need) {
          out.set(head, offset);
          offset += head.length;
          this._pending.shift();
        } else {
          out.set(head.subarray(0, need), offset);
          this._pending[0] = head.subarray(need);
          offset = n;
        }
      }
      this._pendingBytes -= n;
      return out;
    }

    async _drainLoop() {
      const client = this._client;
      try {
        while (this._pendingBytes >= 2) {
          const sr = client._playbackSourceRate || 24000;
          const bytesPerMs = (sr * 2) / 1000;
          const prebufferBytes = Math.floor(bytesPerMs * PLAYBACK_PREBUFFER_MS);
          const mergeBytes = Math.max(2, Math.floor(bytesPerMs * PLAYBACK_MERGE_MS));

          if (!this._playbackStarted && this._pendingBytes < prebufferBytes) {
            await new Promise((resolve) => setTimeout(resolve, 8));
            continue;
          }
          this._playbackStarted = true;

          let take = Math.min(this._pendingBytes, mergeBytes);
          take -= take % 2;
          if (take < 2) break;

          const merged = this._takeBytes(take);
          await client._schedulePcmChunk(merged.buffer, sr);
        }
      } finally {
        this._draining = false;
        if (this._pendingBytes >= 2) {
          this._draining = true;
          void this._drainLoop();
        }
      }
    }
  }

  function floatTo16kPcm(input, inputRate) {
    const ratio = inputRate / TARGET_SR;
    const outLen = Math.floor(input.length / ratio);
    const out = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const idx = Math.floor(i * ratio);
      const s = Math.max(-1, Math.min(1, input[idx]));
      out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return out;
  }

  function rmsInt16(slice) {
    let s = 0;
    for (let i = 0; i < slice.length; i++) s += slice[i] * slice[i];
    return Math.sqrt(s / slice.length) / 32768;
  }

  class VoiceStreamClient {
    constructor(options) {
      this.wsUrl = options.wsUrl;
      this.onEvent = options.onEvent || (() => {});
      this.onError = options.onError || (() => {});
      this.onConnectionChange = options.onConnectionChange || (() => {});
      this.onSpeakingChange = options.onSpeakingChange || (() => {});
      this.onEndUtterance = options.onEndUtterance || (() => {});
      this.onBargeIn = options.onBargeIn || (() => {});
      this.ws = null;
      this.audioCtx = null;
      this.micStream = null;
      this.processor = null;
      this.playbackCtx = null;
      /** Sample rate of incoming PCM (e.g. 24000 from F5-TTS), not AudioContext.rate */
      this.playbackSampleRate = 24000;
      this._playbackSourceRate = 24000;
      this.nextPlayTime = 0;
      this.micActive = false;
      this.silenceMs = 0;
      this.speechMs = 0;
      this._carry = new Int16Array(0);
      this._vadThreshold = options.vadThreshold ?? 0.028;
      this._bargeInThreshold = options.bargeInThreshold ?? 0.045;
      this._listenPaused = false;
      this._endCooldownUntil = 0;
      this._utteranceEnded = true;
      this._isSpeaking = false;
      this.turnPlaybackStartTime = 0;
      this._bargeInArmedAt = 0;
      this._playbackSources = [];
      this._silenceEndMs = options.silenceEndMs ?? DEFAULT_SILENCE_END_MS;
      this._pcmQueue = new PcmPlaybackQueue(this);
    }

    setListenPaused(paused) {
      this._listenPaused = !!paused;
      if (paused) {
        this.silenceMs = 0;
        this.speechMs = 0;
      }
    }

    /** Call after turn_end so the next spoken phrase can trigger end_utterance again. */
    resetAfterTurn() {
      this._utteranceEnded = false;
      this.silenceMs = 0;
      this.speechMs = 0;
      this._endCooldownUntil = 0;
      this._bargeInArmedAt = 0;
    }

    async ensurePlaybackReady(sourceSampleRate) {
      if (sourceSampleRate) {
        this._playbackSourceRate = sourceSampleRate;
        this.playbackSampleRate = sourceSampleRate;
      }
      if (!this.playbackCtx) {
        const rate = sourceSampleRate || 24000;
        try {
          this.playbackCtx = new AudioContext({ sampleRate: rate });
        } catch (_) {
          this.playbackCtx = new AudioContext();
        }
        this.nextPlayTime = 0;
      }
      if (this.playbackCtx.state === 'suspended') {
        await this.playbackCtx.resume();
      }
      return this.playbackCtx;
    }

    notifyListenReady() {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: 'listen_ready' }));
      }
    }

    _setSpeaking(speaking) {
      if (this._isSpeaking === speaking) return;
      this._isSpeaking = speaking;
      this.onSpeakingChange(speaking);
    }

    _stopPlaybackSources() {
      for (const src of this._playbackSources) {
        try {
          src.stop();
        } catch (_) {}
        try {
          src.disconnect();
        } catch (_) {}
      }
      this._playbackSources = [];
    }

    isPlaybackActive() {
      if (!this.playbackCtx) return false;
      return this.playbackCtx.currentTime < this.nextPlayTime - 0.05;
    }

    waitForPlaybackDone(maxMs) {
      const limit = maxMs ?? 120000;
      const start = Date.now();
      return new Promise((resolve) => {
        const tick = () => {
          if (!this.isPlaybackActive()) {
            this._setSpeaking(false);
            resolve();
            return;
          }
          if (Date.now() - start > limit) {
            this.nextPlayTime = 0;
            this._setSpeaking(false);
            resolve();
            return;
          }
          requestAnimationFrame(tick);
        };
        tick();
      });
    }

    async connect(config) {
      if (this.ws) await this.disconnect();
      return new Promise((resolve, reject) => {
        this.ws = new WebSocket(this.wsUrl);
        this.ws.binaryType = 'arraybuffer';
        this.ws.onopen = () => {
          this.ws.send(JSON.stringify({ type: 'config', ...config }));
          this.onConnectionChange(true);
          resolve();
        };
        this.ws.onerror = () => {
          const err = new Error('WebSocket connection failed');
          this.onError(err);
          reject(err);
        };
        this.ws.onclose = () => {
          this.onConnectionChange(false);
          this.stopMic();
        };
        this.ws.onmessage = async (ev) => {
          if (ev.data instanceof ArrayBuffer) {
            this._pcmQueue.enqueue(ev.data);
            return;
          }
          let msg;
          try {
            msg = JSON.parse(ev.data);
          } catch {
            return;
          }
          if (msg.type === 'audio_config' && msg.sample_rate) {
            await this.ensurePlaybackReady(msg.sample_rate);
          }
          if (msg.type === 'barge_in') {
            this.interrupt(false);
          }
          this.onEvent(msg);
        };
      });
    }

    async disconnect() {
      this.stopMic();
      if (this.ws) {
        const w = this.ws;
        this.ws = null;
        w.close();
      }
      this._stopPlaybackSources();
      this._pcmQueue.reset();
      if (this.playbackCtx) {
        try {
          await this.playbackCtx.close();
        } catch (_) {}
        this.playbackCtx = null;
      }
      this._setSpeaking(false);
      this.onConnectionChange(false);
    }

    async _schedulePcmChunk(pcmBytes, sampleRate) {
      const srcRate = sampleRate || this._playbackSourceRate || 24000;
      const ctx = await this.ensurePlaybackReady(srcRate);
      const floats = pcmBytesToFloat32(pcmBytes);
      const fadeSamples = Math.floor((srcRate * CROSSFADE_MS) / 1000);
      applyCrossfade(floats, fadeSamples);

      const startAt = Math.max(this.nextPlayTime, ctx.currentTime);
      if (!this.turnPlaybackStartTime) {
        this.turnPlaybackStartTime = startAt;
      }

      const buf = ctx.createBuffer(1, floats.length, srcRate);
      buf.copyToChannel(floats, 0);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(startAt);
      this._playbackSources.push(src);
      src.onended = () => {
        const idx = this._playbackSources.indexOf(src);
        if (idx >= 0) this._playbackSources.splice(idx, 1);
      };
      this.nextPlayTime = startAt + buf.duration;
      this._setSpeaking(true);
    }

    interrupt(notifyServer = true) {
      this._stopPlaybackSources();
      this._pcmQueue.reset();
      if (notifyServer && this.ws && this.ws.readyState === WebSocket.OPEN) {
        let offset = 0;
        if (this.playbackCtx && this.turnPlaybackStartTime) {
          offset = Math.max(
            0,
            (this.playbackCtx.currentTime - this.turnPlaybackStartTime) * 1000
          );
        }
        this.ws.send(JSON.stringify({ type: 'barge_in', offset_ms: offset }));
      }
      this.nextPlayTime = 0;
      this.turnPlaybackStartTime = 0;
      this._setSpeaking(false);
      this._bargeInArmedAt = 0;
      this.onBargeIn();
    }

    endUtterance() {
      const now = Date.now();
      if (now < this._endCooldownUntil) return;
      if (this._listenPaused) return;
      if (this.speechMs < MIN_SPEECH_MS) return;
      if (this._utteranceEnded) return;
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      this.setListenPaused(true);
      this.ws.send(JSON.stringify({ type: 'end_utterance' }));
      this._utteranceEnded = true;
      this._endCooldownUntil = now + END_COOLDOWN_MS;
      this.silenceMs = 0;
      this.speechMs = 0;
      this.onEndUtterance();
    }

    _maybeBargeIn(level) {
      if (!this._listenPaused) return;
      if (level < this._bargeInThreshold) {
        this._bargeInArmedAt = 0;
        return;
      }
      const now = Date.now();
      if (!this._bargeInArmedAt) {
        this._bargeInArmedAt = now;
        return;
      }
      if (now - this._bargeInArmedAt >= BARGE_IN_DEBOUNCE_MS) {
        this.interrupt(true);
        this.setListenPaused(false);
        this.resetAfterTurn();
      }
    }

    async startMic() {
      if (this.micActive) return;
      this.micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: { ideal: 1 },
        },
      });
      this.audioCtx = new AudioContext();
      if (this.audioCtx.state === 'suspended') {
        await this.audioCtx.resume();
      }
      const src = this.audioCtx.createMediaStreamSource(this.micStream);
      this.processor = this.audioCtx.createScriptProcessor(4096, 1, 1);
      this.processor.onaudioprocess = (e) => {
        if (!this.micActive || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        const input = e.inputBuffer.getChannelData(0);
        const pcm = floatTo16kPcm(input, this.audioCtx.sampleRate);
        const merged = new Int16Array(this._carry.length + pcm.length);
        merged.set(this._carry);
        merged.set(pcm, this._carry.length);
        let offset = 0;
        while (offset + SAMPLES_PER_CHUNK <= merged.length) {
          const slice = merged.subarray(offset, offset + SAMPLES_PER_CHUNK);
          // Always send PCM so server can detect barge-in while agent speaks.
          this.ws.send(
            slice.buffer.slice(slice.byteOffset, slice.byteOffset + slice.byteLength)
          );
          const level = rmsInt16(slice);
          if (this._listenPaused) {
            this._maybeBargeIn(level);
            offset += SAMPLES_PER_CHUNK;
            continue;
          }
          if (level > this._vadThreshold) {
            this.silenceMs = 0;
            this.speechMs += CHUNK_MS;
            this._utteranceEnded = false;
          } else {
            this.silenceMs += CHUNK_MS;
          }
          if (
            this.speechMs >= MIN_SPEECH_MS &&
            this.silenceMs >= this._silenceEndMs
          ) {
            this.endUtterance();
          }
          offset += SAMPLES_PER_CHUNK;
        }
        this._carry = merged.subarray(offset);
      };
      src.connect(this.processor);
      this.processor.connect(this.audioCtx.destination);
      this.micActive = true;
    }

    stopMic() {
      this.micActive = false;
      if (this.processor) {
        try {
          this.processor.disconnect();
        } catch (_) {}
        this.processor = null;
      }
      if (this.micStream) {
        this.micStream.getTracks().forEach((t) => t.stop());
        this.micStream = null;
      }
      if (this.audioCtx) {
        void this.audioCtx.close();
        this.audioCtx = null;
      }
      this._carry = new Int16Array(0);
    }
  }

  global.VoiceStreamClient = VoiceStreamClient;
})(typeof window !== 'undefined' ? window : globalThis);
