import { useCallback, useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const LANG_TABS = [
  { id: 'en', label: 'English' },
  { id: 'hi', label: 'Hindi' },
  { id: 'hinglish', label: 'Hinglish' },
]

const PLAYBACK_SPEEDS = [
  { value: 0.5, label: '0.5×' },
  { value: 0.75, label: '0.75×' },
  { value: 0.85, label: '0.85×' },
  { value: 1, label: '1×' },
]

const SAMPLES = {
  en: [
    'Hello! My name is Astra. I will conduct your technical interview today.',
    'Tell me about your experience with React and Node.js.',
  ],
  hi: [
    'नमस्ते, मैं Astra हूँ। आप अपने बारे में थोड़ा बताइए।',
    'आप React और Python में कितना experience रखते हैं?',
  ],
  hinglish: [
    'Phir Aashish ne decide kiya, ki woh bada hokar engineer banega. Aur aisi technology banayega, jo gaon, shehar aur desh ke logon ki zindagi aasaan bana sake.',
    'Welcome! Aaj main aapka technical interview loongi.',
  ],
}

const LANG_VOICE_PRIORITY = {
  en: ['en-in', 'hinglish', 'hi', 'en-us'],
  hi: ['hi', 'hinglish', 'en-in'],
  hinglish: ['hinglish', 'en-in', 'hi', 'en-us'],
}

function normalizeVoiceLang(code) {
  const c = (code || '').toLowerCase().replace('_', '-')
  if (c === 'en' || c === 'english') return 'en-in'
  if (c === 'hi' || c === 'hindi') return 'hi'
  if (c === 'hinglish') return 'hinglish'
  return c
}

function voicesForLanguage(voices, language) {
  if (!voices?.length) return []
  const prefs = LANG_VOICE_PRIORITY[language] || LANG_VOICE_PRIORITY.en
  const ordered = []
  const seen = new Set()
  for (const pref of prefs) {
    for (const v of voices) {
      const lang = normalizeVoiceLang(v.language)
      if (!seen.has(v.id) && (lang === pref || (pref === 'hi' && lang === 'hinglish'))) {
        ordered.push(v)
        seen.add(v.id)
      }
    }
  }
  for (const v of voices) {
    if (!seen.has(v.id)) ordered.push(v)
  }
  return ordered
}

function pickVoiceForLanguage(voices, language) {
  const pool = voicesForLanguage(voices, language)
  if (!pool.length) return ''
  const indian = pool.find((v) => v.id === 'astra_hinglish')
  if ((language === 'hi' || language === 'hinglish') && indian) return indian.id
  return pool[0].id
}

function apiErrorDetail(data, fallback = 'Request failed') {
  if (!data?.detail) return fallback
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d))).join('; ')
  }
  return String(data.detail)
}

export default function TtsLabPanel() {
  const [language, setLanguage] = useState('en')
  const [text, setText] = useState(SAMPLES.en[0])
  const [voices, setVoices] = useState([])
  const [voiceId, setVoiceId] = useState('')
  const [playbackSpeed, setPlaybackSpeed] = useState(0.85)
  const [status, setStatus] = useState('')
  const [statusKind, setStatusKind] = useState('')
  const [generating, setGenerating] = useState(false)
  const [listening, setListening] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [audioUrl, setAudioUrl] = useState(null)
  const playerRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const streamRef = useRef(null)

  const revokeAudio = useCallback(() => {
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
  }, [])

  useEffect(() => () => revokeAudio(), [revokeAudio])

  useEffect(() => {
    const el = playerRef.current
    if (el) el.playbackRate = playbackSpeed
  }, [playbackSpeed, audioUrl])

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/demo/config`)
        if (!res.ok) return
        const data = await res.json()
        setVoices(data.voices || [])
        setVoiceId((prev) => prev || pickVoiceForLanguage(data.voices || [], language))
      } catch {
        /* optional */
      }
    })()
  }, [])

  const switchLanguage = (lang) => {
    setLanguage(lang)
    setText(SAMPLES[lang]?.[0] || '')
    setVoiceId(pickVoiceForLanguage(voices, lang))
    revokeAudio()
    setStatus('')
    setStatusKind('')
  }

  const stopMicStream = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }

  const transcribeBlob = async (blob) => {
    setTranscribing(true)
    setStatus('Transcribing…')
    setStatusKind('')
    try {
      const fd = new FormData()
      fd.append('audio', blob, 'utterance.webm')
      fd.append('language', language)
      const res = await fetch(`${API_BASE}/api/v1/demo/transcribe`, {
        method: 'POST',
        body: fd,
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(apiErrorDetail(data, res.statusText))
      }
      const data = await res.json()
      const heard = (data.text || '').trim()
      if (!heard) {
        setStatus('No speech detected — try again.')
        setStatusKind('error')
        return
      }
      setText((prev) => (prev.trim() ? `${prev.trim()} ${heard}` : heard))
      setStatus(`Heard: "${heard.length > 60 ? `${heard.slice(0, 60)}…` : heard}"`)
      setStatusKind('ok')
    } catch (err) {
      setStatus(err.message || 'Transcription failed')
      setStatusKind('error')
    } finally {
      setTranscribing(false)
      setListening(false)
    }
  }

  const onMicToggle = async () => {
    if (transcribing) return
    if (listening) {
      stopMicStream()
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      audioChunksRef.current = []
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' })
      mediaRecorderRef.current = recorder
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data)
      }
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' })
        audioChunksRef.current = []
        if (blob.size >= 512) {
          void transcribeBlob(blob)
        } else {
          setListening(false)
          setStatus('Recording too short — hold mic longer.')
          setStatusKind('error')
        }
      }
      recorder.start()
      setListening(true)
      setStatus('Listening… click mic again when done.')
      setStatusKind('')
    } catch (err) {
      setStatus(err.message || 'Microphone access denied')
      setStatusKind('error')
      setListening(false)
    }
  }

  const onGenerate = async () => {
    const trimmed = text.trim()
    if (!trimmed) {
      setStatus('Enter some text first.')
      setStatusKind('error')
      return
    }

    setGenerating(true)
    setStatus('Generating…')
    setStatusKind('')
    revokeAudio()

    try {
      const res = await fetch(`${API_BASE}/api/v1/demo/tts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: trimmed,
          language,
          voice_id: voiceId || null,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(apiErrorDetail(data, res.statusText))
      }
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      setAudioUrl(url)
      setStatus('Playing…')
      setStatusKind('ok')
      requestAnimationFrame(() => {
        const el = playerRef.current
        if (el) {
          el.src = url
          el.playbackRate = playbackSpeed
          void el.play().catch(() => {
            setStatus('Ready — press play on the audio bar.')
            setStatusKind('ok')
          })
        }
      })
    } catch (err) {
      setStatus(err.message || 'Generation failed')
      setStatusKind('error')
    } finally {
      setGenerating(false)
    }
  }

  const onStop = () => {
    const el = playerRef.current
    if (el) {
      el.pause()
      el.currentTime = 0
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0e17] bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,#1e2a4a_0%,#0a0e17_55%)] flex items-start justify-center p-4 font-sans text-[#e8ecf4]">
      <div className="w-full max-w-lg rounded-3xl border border-white/10 bg-[#121a2b] shadow-[0_24px_80px_rgba(0,0,0,0.45)] overflow-hidden mt-4">
        <header className="px-6 pt-6 pb-4 text-center border-b border-white/10">
          <h1 className="m-0 text-xl font-bold tracking-tight">TTS Lab</h1>
          <p className="mt-1 text-sm text-[#8b95a8]">STT mic · TTS play · English, Hindi, Hinglish</p>
        </header>

        <div className="flex border-b border-white/10">
          {LANG_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => switchLanguage(tab.id)}
              className={`flex-1 py-3 text-sm font-semibold transition-colors ${
                language === tab.id
                  ? 'text-white bg-indigo-600/20 border-b-2 border-indigo-500'
                  : 'text-[#8b95a8] hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="px-6 py-5 space-y-4">
          <div>
            <div className="flex items-center justify-between gap-2 mb-2">
              <label className="text-xs font-semibold uppercase tracking-wider text-indigo-400">
                Text to speak
              </label>
              <button
                type="button"
                onClick={() => void onMicToggle()}
                disabled={transcribing || generating}
                title={listening ? 'Stop recording' : 'Speak to transcribe'}
                className={`flex items-center justify-center w-10 h-10 rounded-full border transition-all ${
                  listening
                    ? 'bg-red-500/20 border-red-400 text-red-300 animate-pulse'
                    : 'bg-white/5 border-white/15 text-[#e8ecf4] hover:border-indigo-500 hover:bg-indigo-600/20'
                } disabled:opacity-40`}
                aria-label={listening ? 'Stop recording' : 'Start microphone'}
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
                  <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
                  <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3" />
                </svg>
              </button>
            </div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={5}
              spellCheck={false}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500 resize-y min-h-[120px]"
              placeholder="Type or use mic…"
            />
            <div className="flex flex-wrap gap-2 mt-2">
              {(SAMPLES[language] || []).map((sample) => (
                <button
                  key={sample}
                  type="button"
                  onClick={() => setText(sample)}
                  className="text-xs px-2.5 py-1 rounded-full border border-white/10 bg-white/5 text-[#8b95a8] hover:text-white hover:border-indigo-500/50 truncate max-w-full"
                  title={sample}
                >
                  {sample.length > 42 ? `${sample.slice(0, 42)}…` : sample}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
              Voice
            </label>
            <select
              value={voiceId}
              onChange={(e) => setVoiceId(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500"
            >
              {voicesForLanguage(voices, language).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.display_name || v.id} ({v.language})
                </option>
              ))}
            </select>
          </div>

          {(language === 'hi' || language === 'hinglish') && (
            <p className="text-xs text-emerald-400/90">
              Roman Hinglish + auto pauses (, ...) for Swara. Speak/type naturally — commas slow
              the voice down.
            </p>
          )}

          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => void onGenerate()}
              disabled={generating || listening || transcribing}
              className="flex-1 min-w-[140px] rounded-xl bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed px-4 py-3 text-sm font-bold text-white transition-colors"
            >
              {generating ? 'Generating…' : 'Generate & play'}
            </button>
            <button
              type="button"
              onClick={onStop}
              disabled={!audioUrl}
              className="rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 disabled:opacity-40 px-4 py-3 text-sm font-semibold text-[#e8ecf4] transition-colors"
            >
              Stop
            </button>
          </div>

          <p
            className={`text-sm min-h-[1.25rem] ${
              statusKind === 'error'
                ? 'text-red-400'
                : statusKind === 'ok'
                  ? 'text-emerald-400'
                  : 'text-[#8b95a8]'
            }`}
          >
            {status || 'Ready — type or mic, then Generate.'}
          </p>

          {audioUrl && (
            <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <p className="text-xs font-semibold uppercase tracking-wider text-indigo-400 m-0">
                  Playback
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-[#8b95a8]">Speed</span>
                  <select
                    value={playbackSpeed}
                    onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
                    className="rounded-lg border border-white/10 bg-[#1c2642] px-2 py-1 text-xs text-white outline-none focus:border-indigo-500"
                    aria-label="Playback speed"
                  >
                    {PLAYBACK_SPEEDS.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <audio
                ref={playerRef}
                controls
                className="w-full"
                onLoadedMetadata={(e) => {
                  e.currentTarget.playbackRate = playbackSpeed
                }}
                onEnded={() => {
                  setStatus('Done — replay or change speed above.')
                  setStatusKind('ok')
                }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
