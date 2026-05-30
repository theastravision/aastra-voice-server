import { useState } from 'react'
import AstraInterviewDashboard from './AstraInterviewDashboard.jsx'
import VoiceTrainingPanel from './VoiceTrainingPanel.jsx'
import './index.css'

export default function App() {
  const [tab, setTab] = useState('interview')

  return (
    <div>
      <nav className="flex justify-center gap-2 p-3 bg-[#0a0e17] border-b border-white/10">
        <button
          type="button"
          onClick={() => setTab('interview')}
          className={`px-4 py-2 rounded-lg text-sm font-semibold ${
            tab === 'interview' ? 'bg-indigo-600 text-white' : 'text-[#8b95a8] hover:text-white'
          }`}
        >
          Interview
        </button>
        <button
          type="button"
          onClick={() => setTab('training')}
          className={`px-4 py-2 rounded-lg text-sm font-semibold ${
            tab === 'training' ? 'bg-indigo-600 text-white' : 'text-[#8b95a8] hover:text-white'
          }`}
        >
          Training
        </button>
      </nav>
      {tab === 'interview' ? <AstraInterviewDashboard /> : <VoiceTrainingPanel />}
    </div>
  )
}
