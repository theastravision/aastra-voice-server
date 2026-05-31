import { useCallback, useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || ''
const WS_BASE = import.meta.env.VITE_WS_BASE || ''
const LANG_STORAGE_KEY = 'astra_interview_lang'
const VOICE_STORAGE_KEY = 'astra_interview_voice'

function wsUrl() {
  if (WS_BASE) return `${WS_BASE.replace(/\/$/, '')}/ws/voice`
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/ws/voice`
}

function loadVoiceStreamClient() {
  if (window.VoiceStreamClient) return Promise.resolve(window.VoiceStreamClient)
  return new Promise((resolve, reject) => {
    const src = `${API_BASE}/static/voice-stream-client.js`
    let script = document.querySelector(`script[src="${src}"]`)
    const onLoad = () => {
      if (window.VoiceStreamClient) resolve(window.VoiceStreamClient)
      else reject(new Error('VoiceStreamClient not defined'))
    }
    const onError = () => reject(new Error('Failed to load voice-stream-client.js'))
    if (script) {
      script.addEventListener('load', onLoad)
      script.addEventListener('error', onError)
      return
    }
    script = document.createElement('script')
    script.src = src
    script.async = true
    script.addEventListener('load', onLoad)
    script.addEventListener('error', onError)
    document.body.appendChild(script)
  })
}

async function fetchDemoConfig() {
  const defaults = {
    candidate_name: 'Aashish',
    stt_provider: 'whisper_chunk',
    tts_provider: 'f5',
    interview_job_title: 'Software Engineer',
    models_ready: true,
    warmup_error: null,
    interview_opening_enabled: true,
  }
  try {
    const res = await fetch(`${API_BASE}/api/v1/demo/config`)
    if (res.ok) return { ...defaults, ...(await res.json()) }
  } catch {
    /* defaults */
  }
  return defaults
}

async function waitForModelsReady(initialCfg) {
  let cfg = initialCfg
  if (cfg.warmup_error && cfg.models_ready !== true) {
    throw new Error(`Voice models failed to load: ${cfg.warmup_error}`)
  }
  if (cfg.models_ready === true) return cfg
  for (let i = 0; i < 90 && cfg.models_ready !== true; i++) {
    await new Promise((r) => setTimeout(r, 2000))
    cfg = await fetchDemoConfig()
    if (cfg.warmup_error && cfg.models_ready !== true) {
      throw new Error(`Voice models failed to load: ${cfg.warmup_error}`)
    }
  }
  if (cfg.models_ready !== true) {
    throw new Error('Voice models are still loading. Please wait and try again.')
  }
  return cfg
}

const STATE_LABELS = {
  IDLE: 'Ready',
  LOADING_MODELS: 'Loading voice models…',
  CONNECTING: 'Connecting…',
  LISTENING: 'Listening',
  THINKING: 'Thinking…',
  SPEAKING: 'Astra speaking',
}

const LANG_OPTIONS = [
  { value: 'en', label: 'English (Indian accent)' },
  { value: 'hi', label: 'Hindi (हिंदी)' },
  { value: 'hinglish', label: 'Hinglish' },
]

const LANG_VOICE_PRIORITY = {
  en: ['en-in', 'hinglish', 'hi', 'en-us'],
  hi: ['hi', 'hinglish', 'en-in'],
  hinglish: ['hinglish', 'en-in', 'hi', 'en-us'],
}

const ALLOWED_VOICE_LANGS = new Set(['en-in', 'hi', 'hinglish', 'en-us'])

function normalizeVoiceLang(code) {
  const c = (code || '').toLowerCase().replace('_', '-')
  if (c === 'en' || c === 'english') return 'en-in'
  if (c === 'en-in' || c === 'en-indian') return 'en-in'
  if (c === 'en-us' || c === 'en-gb') return c
  if (c === 'hi' || c === 'hindi') return 'hi'
  if (c === 'hinglish') return 'hinglish'
  return c
}

function allowedVoices(voices) {
  if (!voices?.length) return []
  return voices.filter((v) => ALLOWED_VOICE_LANGS.has(normalizeVoiceLang(v.language)))
}

function pickVoiceForLanguage(voices, language) {
  const pool = allowedVoices(voices)
  if (!pool.length) return 'astra'
  const prefs = LANG_VOICE_PRIORITY[language] || LANG_VOICE_PRIORITY.en
  for (const pref of prefs) {
    const match = pool.find((v) => normalizeVoiceLang(v.language) === pref)
    if (match) return match.id
  }
  return pool[0].id
}

function resolveVoiceId(voices, language, requestedId) {
  const pool = allowedVoices(voices)
  if (!pool.length) return requestedId || 'astra'
  if (requestedId && pool.some((v) => v.id === requestedId)) return requestedId
  return pickVoiceForLanguage(voices, language)
}

function voicesForLanguage(voices, language) {
  const pool = allowedVoices(voices)
  if (!pool.length) return [{ id: 'astra', display_name: 'Astra (Indian English)' }]
  const prefs = LANG_VOICE_PRIORITY[language] || LANG_VOICE_PRIORITY.en
  const ordered = []
  const seen = new Set()
  for (const pref of prefs) {
    for (const v of pool) {
      if (!seen.has(v.id) && normalizeVoiceLang(v.language) === pref) {
        ordered.push(v)
        seen.add(v.id)
      }
    }
  }
  return ordered
}

export default function AstraInterviewDashboard() {
  const [sessionId, setSessionId] = useState(null)
  const [interviewState, setInterviewState] = useState('IDLE')
  const [astraText, setAstraText] = useState('')
  const [userText, setUserText] = useState('')
  const [partial, setPartial] = useState('')
  const [error, setError] = useState('')
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [wsReady, setWsReady] = useState(false)
  const [modelsReady, setModelsReady] = useState(true)
  const [warmupError, setWarmupError] = useState('')
  const [openingEnabled, setOpeningEnabled] = useState(true)
  const [language, setLanguage] = useState(() => {
    try {
      return sessionStorage.getItem(LANG_STORAGE_KEY) || 'en'
    } catch {
      return 'en'
    }
  })
  const [voiceId, setVoiceId] = useState(() => {
    try {
      return sessionStorage.getItem(VOICE_STORAGE_KEY) || 'astra'
    } catch {
      return 'astra'
    }
  })
  const [voices, setVoices] = useState([])
  const [jobTitle, setJobTitle] = useState('Software Engineer')

  const clientRef = useRef(null)
  const sessionStartedRef = useRef(false)
  const startingRef = useRef(false)
  const greetingPendingRef = useRef(false)
  const greetingWaitRef = useRef(null)

  const unpauseMicAfterPlayback = useCallback(async (client) => {
    if (!client || !sessionStartedRef.current) return
    await client.waitForPlaybackDone()
    if (typeof client.resetAfterTurn === 'function') {
      client.resetAfterTurn()
    }
    client.setListenPaused(false)
    if (typeof client.notifyListenReady === 'function') {
      client.notifyListenReady()
    }
    setInterviewState('LISTENING')
  }, [])

  const resolveGreetingWait = useCallback(() => {
    if (greetingWaitRef.current) {
      greetingWaitRef.current()
      greetingWaitRef.current = null
    }
    greetingPendingRef.current = false
  }, [])

  const handleConnectionChange = useCallback((connected) => {
    setWsReady(connected)
    if (!connected && sessionStartedRef.current) {
      setError('Connection lost. Please end the call and try again.')
      setInterviewState('IDLE')
      sessionStartedRef.current = false
      greetingPendingRef.current = false
      resolveGreetingWait()
    }
  }, [resolveGreetingWait])

  const handleEvent = useCallback(
    (msg, client) => {
      if (!client) return
      switch (msg.type) {
        case 'config':
          if (msg.ok) {
            setWsReady(true)
            if (msg.session_id) setSessionId(msg.session_id)
          }
          break
        case 'turn_start':
          client.setListenPaused(true)
          if (!greetingPendingRef.current) {
            setAstraText('')
          }
          setInterviewState('THINKING')
          break
        case 'stt_partial':
          setPartial(msg.text || '')
          break
        case 'stt_final':
          setUserText(msg.text || '')
          setPartial('')
          setInterviewState('THINKING')
          break
        case 'stt_processing':
          setInterviewState('THINKING')
          break
        case 'assistant_delta':
          client.setListenPaused(true)
          setAstraText((t) => t + (msg.text || ''))
          setInterviewState('SPEAKING')
          break
        case 'assistant_text':
          setAstraText(msg.text || '')
          break
        case 'audio_config':
          client.setListenPaused(true)
          setInterviewState('SPEAKING')
          break
        case 'turn_end':
          void (async () => {
            await unpauseMicAfterPlayback(client)
            if (greetingPendingRef.current) {
              resolveGreetingWait()
            }
          })()
          break
        case 'barge_in':
          client.interrupt(false)
          client.setListenPaused(false)
          if (typeof client.resetAfterTurn === 'function') {
            client.resetAfterTurn()
          }
          setInterviewState('LISTENING')
          break
        case 'error':
          setError(msg.message || 'Error')
          if (greetingPendingRef.current) {
            resolveGreetingWait()
          }
          if (typeof client.resetAfterTurn === 'function') {
            client.resetAfterTurn()
          }
          client.setListenPaused(false)
          setInterviewState('LISTENING')
          break
        default:
          break
      }
    },
    [unpauseMicAfterPlayback, resolveGreetingWait]
  )

  const waitForGreetingTurn = () =>
    new Promise((resolve) => {
      greetingWaitRef.current = resolve
      setTimeout(resolve, 120000)
    })

  const startCall = async () => {
    if (startingRef.current || interviewState === 'CONNECTING') return
    startingRef.current = true
    setError('')
    setAstraText('')
    setUserText('')
    setPartial('')
    setWsReady(false)
    setInterviewState('LOADING_MODELS')

    let client = null
    try {
      let cfg = await fetchDemoConfig()
      setModelsReady(cfg.models_ready !== false)
      setWarmupError(cfg.warmup_error || '')
      if (cfg.interview_opening_enabled !== undefined) {
        setOpeningEnabled(!!cfg.interview_opening_enabled)
      }

      cfg = await waitForModelsReady(cfg)
      setModelsReady(true)
      setWarmupError('')

      if (Array.isArray(cfg.voices) && cfg.voices.length) {
        setVoices(cfg.voices)
      }
      if (cfg.interview_job_title) setJobTitle(cfg.interview_job_title)

      const activeVoice = resolveVoiceId(cfg.voices || voices, language, voiceId)
      if (activeVoice !== voiceId) setVoiceId(activeVoice)

      sessionStorage.setItem(LANG_STORAGE_KEY, language)
      sessionStorage.setItem(VOICE_STORAGE_KEY, activeVoice)

      const VoiceStreamClient = await loadVoiceStreamClient()

      client = new VoiceStreamClient({
        wsUrl: wsUrl(),
        vadThreshold: 0.028,
        bargeInThreshold: 0.045,
        onEvent: (msg) => handleEvent(msg, client),
        onError: (e) => setError(e.message || String(e)),
        onConnectionChange: handleConnectionChange,
        onSpeakingChange: setIsSpeaking,
        onEndUtterance: () => {
          setInterviewState('THINKING')
          setPartial('')
        },
        onBargeIn: () => {
          setInterviewState('LISTENING')
        },
      })
      clientRef.current = client

      await client.ensurePlaybackReady(24000)

      setInterviewState('CONNECTING')
      greetingPendingRef.current = true
      const greetingDone = waitForGreetingTurn()

      await client.connect({
        type: 'config',
        greet: true,
        stt_provider: cfg.stt_provider || 'whisper_chunk',
        tts_provider: cfg.tts_provider || 'f5',
        ...(cfg.interview_opening_enabled
          ? {}
          : { candidate_name: cfg.candidate_name || 'Aashish' }),
        language,
        voice_id: activeVoice,
      })

      sessionStartedRef.current = true
      client.setListenPaused(true)

      try {
        await client.startMic()
      } catch (micErr) {
        await client.disconnect()
        clientRef.current = null
        const msg =
          micErr?.name === 'NotAllowedError'
            ? 'Microphone access denied. Allow mic permission and try again.'
            : micErr?.message || String(micErr)
        throw new Error(msg)
      }

      await greetingDone
      setInterviewState('LISTENING')
    } catch (e) {
      if (clientRef.current) {
        await clientRef.current.disconnect()
        clientRef.current = null
      }
      setError(e.message || String(e))
      setInterviewState('IDLE')
      sessionStartedRef.current = false
      greetingPendingRef.current = false
      resolveGreetingWait()
    } finally {
      startingRef.current = false
    }
  }

  const endCall = async () => {
    sessionStartedRef.current = false
    greetingPendingRef.current = false
    resolveGreetingWait()
    startingRef.current = false
    if (clientRef.current) {
      await clientRef.current.disconnect()
      clientRef.current = null
    }
    setSessionId(null)
    setWsReady(false)
    setInterviewState('IDLE')
    setPartial('')
  }

  useEffect(() => {
    void loadVoiceStreamClient().catch(() => {})
    void fetchDemoConfig().then((cfg) => {
      if (Array.isArray(cfg.voices) && cfg.voices.length) {
        setVoices(cfg.voices)
      }
      setModelsReady(cfg.models_ready !== false)
      setWarmupError(cfg.warmup_error || '')
      if (cfg.interview_opening_enabled !== undefined) {
        setOpeningEnabled(!!cfg.interview_opening_enabled)
      }
      if (cfg.interview_job_title) setJobTitle(cfg.interview_job_title)
    })
    void fetch(`${API_BASE}/api/v1/voices`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => {
        if (Array.isArray(list) && list.length) setVoices(list)
      })
      .catch(() => {})
    return () => {
      void endCall()
    }
  }, [])

  useEffect(() => {
    if (modelsReady || warmupError) return undefined
    let cancelled = false
    const poll = async () => {
      for (let i = 0; i < 90 && !cancelled; i++) {
        await new Promise((r) => setTimeout(r, 2000))
        const cfg = await fetchDemoConfig()
        if (cancelled) return
        if (cfg.warmup_error) {
          setWarmupError(cfg.warmup_error)
          return
        }
        if (cfg.models_ready === true) {
          setModelsReady(true)
          if (Array.isArray(cfg.voices) && cfg.voices.length) setVoices(cfg.voices)
          return
        }
      }
    }
    void poll()
    return () => {
      cancelled = true
    }
  }, [modelsReady, warmupError])

  useEffect(() => {
    if (!voices.length) return
    const resolved = resolveVoiceId(voices, language, voiceId)
    setVoiceId((current) => (current === resolved ? current : resolved))
  }, [language, voices])

  const statusLabel = STATE_LABELS[interviewState] || interviewState
  const callActive = interviewState !== 'IDLE'
  const startDisabled = startingRef.current || (!modelsReady && !warmupError && interviewState === 'IDLE')
  const orbClass =
    interviewState === 'LISTENING'
      ? 'scale-105 shadow-[0_0_56px_rgba(99,102,241,0.45)] animate-pulse'
      : interviewState === 'SPEAKING' || isSpeaking
        ? 'shadow-[0_0_48px_rgba(168,85,247,0.5)]'
        : interviewState === 'THINKING'
          ? 'shadow-[0_0_40px_rgba(99,102,241,0.45)]'
          : 'shadow-[0_0_40px_rgba(99,102,241,0.35)]'

  return (
    <div className="min-h-screen bg-[#0a0e17] bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,#1e2a4a_0%,#0a0e17_55%)] flex items-center justify-center p-4 font-sans text-[#e8ecf4]">
      <div className="w-full max-w-md rounded-3xl border border-white/10 bg-[#121a2b] shadow-[0_24px_80px_rgba(0,0,0,0.45)] overflow-hidden">
        <header className="px-6 pt-6 pb-4 text-center border-b border-white/10">
          <h1 className="m-0 text-xl font-bold tracking-tight">Astra Interview</h1>
          <p className="mt-1 text-sm text-[#8b95a8]">
            {jobTitle} · Voice interview
          </p>
        </header>

        {!callActive && (
          <div className="px-6 pt-4">
            {!modelsReady && !warmupError && (
              <p className="mb-3 text-xs text-amber-400/90">
                Loading voice models… Start call will wait until ready.
              </p>
            )}
            {warmupError && !modelsReady && (
              <p className="mb-3 text-xs text-red-400/90">
                Model warmup error: {warmupError}
              </p>
            )}
            {openingEnabled && (
              <p className="mb-3 text-xs text-[#8b95a8]">
                Astra will ask for your name first before the technical interview.
              </p>
            )}
            <label className="block text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
              Interview language
            </label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500"
            >
              {LANG_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {(language === 'hi' || language === 'hinglish') && (
              <p className="mt-2 text-xs text-emerald-400/90">
                GPT output: Devanagari {language === 'hi' ? 'Hindi' : 'Hinglish'}
              </p>
            )}
            <label className="block text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2 mt-4">
              Interviewer voice
            </label>
            <select
              value={voiceId}
              onChange={(e) => setVoiceId(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500"
            >
              {voicesForLanguage(voices, language).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.display_name || v.id}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="flex justify-center py-6">
          <div
            className={`w-[120px] h-[120px] rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center transition-all duration-300 ${orbClass}`}
            aria-hidden
          >
            <svg className="w-12 h-12 opacity-90" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3" />
            </svg>
          </div>
        </div>

        <p
          className={`text-center text-xs font-semibold uppercase tracking-widest mb-1 ${
            interviewState === 'LISTENING'
              ? 'text-emerald-400'
              : interviewState === 'IDLE'
                ? 'text-[#8b95a8]'
                : 'text-violet-300'
          }`}
        >
          {statusLabel}
          {isSpeaking && interviewState !== 'SPEAKING' ? ' · audio' : ''}
        </p>
        {wsReady && callActive && (
          <p className="text-center text-[10px] text-[#8b95a8] mb-3">WebSocket connected</p>
        )}

        {error && (
          <div className="mx-4 mb-4 rounded-xl border border-red-400/40 bg-red-950/40 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="px-4 pb-4 space-y-3 max-h-[220px] overflow-y-auto">
          <section className="rounded-2xl bg-[#2d1f4e]/80 border border-white/5 px-4 py-3">
            <h2 className="m-0 text-xs font-semibold uppercase tracking-wider text-violet-300 mb-1">Astra</h2>
            <p className="m-0 text-sm leading-relaxed">{astraText || '—'}</p>
          </section>
          <section className="rounded-2xl bg-[#1e3a5f]/80 border border-white/5 px-4 py-3">
            <h2 className="m-0 text-xs font-semibold uppercase tracking-wider text-sky-300 mb-1">You</h2>
            <p className="m-0 text-sm leading-relaxed text-[#c5d0e6]">{userText || partial || '—'}</p>
          </section>
        </div>

        <div className="px-6 pb-6 pt-2">
          {interviewState === 'IDLE' ? (
            <button
              type="button"
              onClick={startCall}
              disabled={startDisabled}
              className="w-full rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 py-3.5 font-semibold text-white shadow-lg transition-transform hover:-translate-y-0.5 active:translate-y-0 disabled:opacity-60"
            >
              {!modelsReady && !warmupError ? 'Loading models…' : 'Start call'}
            </button>
          ) : (
            <button
              type="button"
              onClick={endCall}
              className="w-full rounded-xl border border-red-400/50 bg-red-950/30 py-3.5 font-semibold text-red-300 hover:bg-red-950/50 transition-colors"
            >
              End call
            </button>
          )}
          {sessionId && (
            <p className="mt-3 text-center text-xs text-[#8b95a8]">Session {sessionId.slice(0, 8)}…</p>
          )}
        </div>
      </div>
    </div>
  )
}
