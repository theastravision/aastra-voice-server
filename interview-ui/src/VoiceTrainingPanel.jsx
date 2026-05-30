import { useCallback, useEffect, useRef, useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || ''

function apiErrorDetail(data, fallback = 'Request failed') {
  if (!data?.detail) return fallback
  if (typeof data.detail === 'string') return data.detail
  if (Array.isArray(data.detail)) {
    return data.detail.map((d) => (typeof d === 'string' ? d : d.msg || JSON.stringify(d))).join('; ')
  }
  return String(data.detail)
}

function isKokoroZip(files) {
  return files.length === 1 && files[0].name.toLowerCase().endsWith('.zip')
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export default function VoiceTrainingPanel() {
  const [jobs, setJobs] = useState([])
  const [voices, setVoices] = useState([])
  const [language, setLanguage] = useState('hi')
  const [voiceName, setVoiceName] = useState('')
  const [registerVoice, setRegisterVoice] = useState(true)
  const [files, setFiles] = useState([])
  const [status, setStatus] = useState('')
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const [jRes, vRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/training/jobs`),
        fetch(`${API_BASE}/api/v1/voices`),
      ])
      if (jRes.ok) setJobs(await jRes.json())
      if (vRes.ok) setVoices(await vRes.json())
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    void refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  const addFiles = (incoming) => {
    const list = Array.from(incoming || [])
    if (!list.length) return
    setFiles((prev) => {
      const names = new Set(prev.map((f) => `${f.name}-${f.size}`))
      const merged = [...prev]
      for (const f of list) {
        const key = `${f.name}-${f.size}`
        if (!names.has(key)) {
          merged.push(f)
          names.add(key)
        }
      }
      return merged
    })
  }

  const removeFile = (index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const onUpload = async (e) => {
    e.preventDefault()
    if (!files.length) {
      setStatus('Choose audio files or a Kokoro dataset ZIP from your computer.')
      return
    }

    setUploading(true)
    setStatus('')

    const fd = new FormData()
    fd.append('language', language)

    try {
      if (isKokoroZip(files)) {
        fd.append('dataset_zip', files[0])
        fd.append('start_whisper_job', 'true')
        if (voiceName.trim()) fd.append('voice_name', voiceName.trim())

        const res = await fetch(`${API_BASE}/api/v1/training/import-kokoro`, {
          method: 'POST',
          body: fd,
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(apiErrorDetail(data, 'Kokoro import failed'))

        setStatus(
          `Imported ${data.sample_count} clips (${data.hours}h)` +
            (data.voice_id ? ` · voice “${data.voice_id}”` : '') +
            (data.job_id ? ` · training job ${data.job_id.slice(0, 8)}…` : '')
        )
      } else {
        fd.append('register_voice', registerVoice ? 'true' : 'false')
        if (voiceName.trim()) fd.append('voice_name', voiceName.trim())
        for (const f of files) fd.append('files', f)

        const res = await fetch(`${API_BASE}/api/v1/training/jobs`, {
          method: 'POST',
          body: fd,
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(apiErrorDetail(data, 'Upload failed'))

        setStatus(`Job ${data.id.slice(0, 8)}… queued (${data.sample_count} clips, ${data.hours}h)`)
      }

      setFiles([])
      if (fileInputRef.current) fileInputRef.current.value = ''
      await refresh()
    } catch (err) {
      setStatus(err.message || String(err))
    } finally {
      setUploading(false)
    }
  }

  const kokoroMode = isKokoroZip(files)

  return (
    <div className="min-h-screen bg-[#0a0e17] text-[#e8ecf4] p-6 font-sans">
      <div className="max-w-2xl mx-auto space-y-6">
        <header>
          <h1 className="text-2xl font-bold">Voice & STT Training</h1>
          <p className="text-sm text-[#8b95a8] mt-1">
            Upload audio from your computer to fine-tune Whisper STT and register F5-TTS voices.
          </p>
        </header>

        <form
          onSubmit={onUpload}
          className="rounded-2xl border border-white/10 bg-[#121a2b] p-5 space-y-4"
        >
          <h2 className="text-sm font-semibold uppercase tracking-wider text-indigo-400">
            Upload from your computer
          </h2>

          <div>
            <label className="block text-xs text-[#8b95a8] mb-1">Language</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-3 py-2 text-sm"
            >
              <option value="en">English</option>
              <option value="hi">Hindi</option>
              <option value="hinglish">Hinglish</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-[#8b95a8] mb-1">Voice name (for Kokoro ZIP / TTS)</label>
            <input
              type="text"
              placeholder="e.g. Divya"
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-[#1c2642] px-3 py-2 text-sm"
            />
          </div>

          {!kokoroMode && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={registerVoice}
                onChange={(e) => setRegisterVoice(e.target.checked)}
              />
              Register TTS voice from uploaded clips (when applicable)
            </label>
          )}

          <div
            role="button"
            tabIndex={0}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              addFiles(e.dataTransfer.files)
            }}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
            }}
            className={`rounded-xl border-2 border-dashed px-4 py-8 text-center cursor-pointer transition-colors ${
              dragOver
                ? 'border-indigo-400 bg-indigo-950/30'
                : 'border-white/20 bg-[#1c2642]/50 hover:border-indigo-500/50'
            }`}
          >
            <p className="text-sm font-medium">Click to choose files or drag & drop here</p>
            <p className="text-xs text-[#8b95a8] mt-2">
              WAV / MP3 / FLAC — or one Kokoro ZIP (<code className="text-indigo-300">metadata.csv</code> +{' '}
              <code className="text-indigo-300">wavs/</code>)
            </p>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="audio/*,.zip,application/zip"
              className="hidden"
              onChange={(e) => {
                addFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          {files.length > 0 && (
            <ul className="text-sm space-y-1 rounded-xl bg-[#0a0e17]/60 p-3 max-h-40 overflow-y-auto">
              {files.map((f, i) => (
                <li key={`${f.name}-${f.size}`} className="flex justify-between items-center gap-2">
                  <span className="truncate">
                    {f.name}{' '}
                    <span className="text-[#8b95a8]">({formatBytes(f.size)})</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => removeFile(i)}
                    className="text-red-400 text-xs shrink-0 hover:underline"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}

          {kokoroMode && (
            <p className="text-xs text-violet-300 bg-violet-950/30 rounded-lg px-3 py-2">
              Kokoro ZIP detected — will import STT corpus and start Whisper training
              {voiceName.trim() ? ` · register voice “${voiceName.trim()}”` : ''}.
            </p>
          )}

          <button
            type="submit"
            disabled={uploading || !files.length}
            className="w-full rounded-xl bg-indigo-600 py-2.5 font-semibold disabled:opacity-50"
          >
            {uploading
              ? 'Uploading…'
              : kokoroMode
                ? 'Import Kokoro ZIP & train'
                : 'Upload & start training'}
          </button>
        </form>

        <section className="rounded-2xl border border-white/10 bg-[#121a2b] p-5 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-indigo-400">
            Hinglish vocab corpus
          </h2>
          <p className="text-xs text-[#8b95a8]">
            Uses <code className="text-indigo-300">data/vocab/*.csv</code> to synthesize F5 audio and build a
            Whisper training manifest.
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-xl bg-violet-700 px-4 py-2 text-sm font-semibold disabled:opacity-50"
              disabled={uploading}
              onClick={async () => {
                setUploading(true)
                setStatus('')
                try {
                  const res = await fetch(`${API_BASE}/api/v1/training/hinglish/synthesize`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ max_rows: 5000, voice_id: 'astra', dry_run: false }),
                  })
                  const data = await res.json().catch(() => ({}))
                  if (!res.ok) throw new Error(apiErrorDetail(data, res.statusText))
                  setStatus(`Hinglish synth job started: ${data.id}`)
                  void refresh()
                } catch (e) {
                  setStatus(e.message || String(e))
                } finally {
                  setUploading(false)
                }
              }}
            >
              Build Hinglish corpus (F5 synth)
            </button>
            <button
              type="button"
              className="rounded-xl border border-white/20 px-4 py-2 text-sm disabled:opacity-50"
              disabled={uploading}
              onClick={async () => {
                setUploading(true)
                try {
                  const res = await fetch(`${API_BASE}/api/v1/training/hinglish/export-artifacts`, {
                    method: 'POST',
                  })
                  const data = await res.json().catch(() => ({}))
                  if (!res.ok) throw new Error(apiErrorDetail(data, res.statusText))
                  setStatus(`Exported vocab artifacts (${data.particle_count} particles)`)
                } catch (e) {
                  setStatus(e.message || String(e))
                } finally {
                  setUploading(false)
                }
              }}
            >
              Export vocab artifacts
            </button>
          </div>
        </section>

        {status && (
          <p className="text-sm text-violet-300 rounded-xl bg-violet-950/30 px-4 py-3">{status}</p>
        )}

        <section className="rounded-2xl border border-white/10 bg-[#121a2b] p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-indigo-400 mb-3">Training jobs</h2>
          {jobs.length === 0 ? (
            <p className="text-sm text-[#8b95a8]">No jobs yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {jobs.map((j) => (
                <li key={j.id} className="flex justify-between border-b border-white/5 pb-2">
                  <span>
                    {j.language} · {j.job_type || 'whisper_finetune'} · {j.status}
                    {j.error ? ` · ${j.error}` : ''}
                  </span>
                  <span className="text-[#8b95a8]">
                    {j.sample_count} clips · {j.hours}h
                    {j.manifest_path ? ` · ${j.manifest_path}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-2xl border border-white/10 bg-[#121a2b] p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-indigo-400 mb-3">Registered voices</h2>
          <ul className="space-y-1 text-sm">
            {voices.length === 0 ? (
              <li className="text-[#8b95a8]">No voices registered yet.</li>
            ) : (
              voices.map((v) => (
                <li key={v.id}>
                  <strong>{v.display_name}</strong>{' '}
                  <span className="text-[#8b95a8]">
                    ({v.id} · {v.language})
                  </span>
                </li>
              ))
            )}
          </ul>
        </section>
      </div>
    </div>
  )
}
