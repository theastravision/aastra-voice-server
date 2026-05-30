import { useState } from 'react'
import AstraInterviewDashboard from './AstraInterviewDashboard.jsx'
import VoiceTrainingPanel from './VoiceTrainingPanel.jsx'
import TtsLabPanel from './TtsLabPanel.jsx'
import './index.css'

const TABS = [
  { id: 'interview', label: 'Interview' },
  { id: 'training', label: 'Training' },
  { id: 'tts', label: 'TTS Lab' },
]

export default function App() {
  const [tab, setTab] = useState('interview')

  return (
    <div>
      <nav className="flex justify-center gap-2 p-3 bg-[#0a0e17] border-b border-white/10">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-lg text-sm font-semibold ${
              tab === t.id ? 'bg-indigo-600 text-white' : 'text-[#8b95a8] hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>
      {tab === 'interview' && <AstraInterviewDashboard />}
      {tab === 'training' && <VoiceTrainingPanel />}
      {tab === 'tts' && <TtsLabPanel />}
    </div>
  )
}
