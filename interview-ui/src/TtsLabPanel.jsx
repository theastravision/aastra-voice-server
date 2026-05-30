import { useCallback, useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

const LANG_TABS = [
  { id: 'en', label: 'English' },
  { id: 'hi', label: 'Hindi' },
  { id: 'hinglish', label: 'Hinglish' },
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
    'Welcome! मैं आज आपका technical interview लूँगी।',
    'आप apne last project के बारे में थोड़ा बताइए।',
  ],
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
  const [status, setStatus] = useState('')
  const [statusKind, setStatusKind] = useState('')
  const [generating, setGenerating] = useState(false)
  const [audioUrl, setAudioUrl] = useState(null)
  const playerRef = useRef(null)

  const revokeAudio = useCallback(() => {
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
  }, [])

  useEffect(() => () => revokeAudio(), [revokeAudio])

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/demo/config`)
        if (!res.ok) return
        const data = await res.json()
        setVoices(data.voices || [])
      } catch {
        /* optional */
      }
    })()
  }, [])

  const switchLanguage = (lang) => {
    setLanguage(lang)
    setText(SAMPLES[lang]?.[0] || '')
    revokeAudio()
    setStatus('')
    setStatusKind('')
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
          <p className="mt-1 text-sm text-[#8b95a8]">Generate &amp; play English, Hindi, Hinglish</p>
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
            <label className="block text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
              Text to speak
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={5}
              spellCheck={false}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-4 py-3 text-sm text-white outline-none focus:border-indigo-500 resize-y min-h-[120px]"
              placeholder="Enter text…"
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
              <option value="">Auto (by language)</option>
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.display_name || v.id} ({v.language})
                </option>
              ))}
            </select>
          </div>

          {(language === 'hi' || language === 'hinglish') && (
            <p className="text-xs text-emerald-400/90">
              Use Devanagari for Hindi words — same as the interview.
            </p>
          )}

          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => void onGenerate()}
              disabled={generating}
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
            {status || 'Ready — type text and click Generate.'}
          </p>

          {audioUrl && (
            <div className="rounded-xl border border-white/10 bg-black/20 p-3">
              <p className="text-xs font-semibold uppercase tracking-wider text-indigo-400 mb-2">
                Playback
              </p>
              <audio
                ref={playerRef}
                controls
                className="w-full"
                onEnded={() => {
                  setStatus('Done — replay from the bar above.')
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
