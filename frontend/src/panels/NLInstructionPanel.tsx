import { useState } from 'react'
import { useMission } from '../store/missionStore'

const PRESETS = [
  'From SDM Hospital pick up urgent insulin (keep 2–8°C) and deliver to KIMS before the deadline.',
  'Also collect a fuel canister from Suretech — but never co-carry it with the oxygen cylinder.',
  'Split the insulin delivery: fly to the hospital perimeter, a ground agent takes the final 200 m.',
  'Emergency return to depot now.',
]

export function NLInstructionPanel() {
  const nl = useMission((s) => s.nl)
  const send = useMission((s) => s.sendInstruction)
  const mission = useMission((s) => s.mission)
  const [text, setText] = useState('')
  const [phase, setPhase] = useState('preflight')

  const submit = () => {
    if (!text.trim()) return
    send(text, phase)
    setText('')
  }

  return (
    <div className="flex h-full flex-col p-3 text-sm">
      <div className="mb-2 text-xs text-slate-400">
        Type a natural-language brief or mid-flight order — parsed by the real LLM into structured actions (same schema as
        the node builder).
      </div>
      <div className="mb-2 flex gap-1">
        {['preflight', 'midflight'].map((p) => (
          <button
            key={p}
            onClick={() => setPhase(p)}
            className={`rounded px-2 py-0.5 text-[11px] ${phase === p ? 'bg-cyan-500 text-slate-900' : 'border border-slate-600 text-slate-300'}`}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="mb-2 flex-1 space-y-1 overflow-y-auto rounded bg-black/30 p-2">
        {nl.length === 0 && <div className="text-[11px] text-slate-600">No instructions yet.</div>}
        {nl.map((m, i) => (
          <div key={i} className={`text-[11px] ${m.role === 'user' ? 'text-slate-200' : 'text-cyan-300'}`}>
            <span className="text-slate-500">{m.role === 'user' ? '▸ you' : `◂ llm${m.source ? `[${m.source}]` : ''}`}: </span>
            {m.text}
          </div>
        ))}
      </div>
      <div className="mb-2 flex flex-wrap gap-1">
        {PRESETS.map((p, i) => (
          <button
            key={i}
            onClick={() => setText(p)}
            className="rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400 hover:border-cyan-500"
          >
            preset {i + 1}
          </button>
        ))}
      </div>
      <div className="flex gap-1">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          placeholder={mission ? 'Type an instruction…' : 'Generate a mission first'}
          className="flex-1 rounded border border-slate-600 bg-mission-bg px-2 py-1 text-xs"
        />
        <button onClick={submit} className="rounded bg-cyan-500 px-3 text-xs font-medium text-slate-900 hover:bg-cyan-400">
          Send
        </button>
      </div>
    </div>
  )
}
