import { useMemo, useState } from 'react'
import { useMission } from '../store/missionStore'

interface Preset {
  label: string
  type: string
  r: number
  text: string
}

const PRESETS: Preset[] = [
  { label: '⛈ Thunderstorm ahead', type: 'storm', r: 240, text: 'Sudden thunderstorm over the corridor ahead — reroute around it.' },
  { label: '🚫 Pop-up no-fly zone', type: 'nofly', r: 180, text: 'Emergency no-fly zone declared on the path ahead.' },
  { label: '🏥 Hospital emergency', type: 'nofly', r: 160, text: 'Hospital B emergency protocol — airspace restricted, split delivery if needed.' },
]

export function DisruptionPanel() {
  const mission = useMission((s) => s.mission)
  const replan = useMission((s) => s.replan)
  const loading = useMission((s) => s.loading)
  const hud = useMission((s) => s.droneHUD)
  const activeFlight = useMission((s) => s.activeFlight)
  const events = useMission((s) => s.events)
  const [text, setText] = useState('')

  const flownSteps = Math.round(hud.progress * Math.max(1, activeFlight.length - 1))
  const center = useMemo(() => {
    const ahead = activeFlight[Math.min(activeFlight.length - 1, flownSteps + 1)]
    return ahead ? { x: ahead.x, y: ahead.y } : { x: 0, y: 0 }
  }, [activeFlight, flownSteps])

  const lastReplan = [...events].reverse().find((e) => e.type === 'replan_complete')
  const lastDisrupt = [...events].reverse().find((e) => e.type === 'disruption_detected')

  const trigger = (p: { type: string; r: number; text: string }) =>
    replan({ type: p.type, x: center.x, y: center.y, r: p.r }, flownSteps, p.text)

  if (!mission) {
    return <div className="p-4 text-sm text-slate-500">Generate a mission first, then inject a disruption mid-flight.</div>
  }

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3 text-sm">
      <div>
        <div className="mb-1 text-[11px] uppercase tracking-widest text-cyan-400">Dynamic Replanning · Eq. 8</div>
        <div className="mono text-[11px] text-slate-400">
          Drone at step <span className="text-cyan-300">{flownSteps}</span> / {activeFlight.length - 1} · the flown
          prefix is preserved (causality).
        </div>
      </div>

      <div className="flex flex-col gap-2">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            disabled={loading}
            onClick={() => trigger(p)}
            className="rounded border border-slate-700 bg-mission-bg px-3 py-2 text-left text-slate-200 hover:border-amber-400 disabled:opacity-50"
          >
            <div className="font-medium">{p.label}</div>
            <div className="text-[11px] text-slate-500">{p.text}</div>
          </button>
        ))}
      </div>

      <div className="border-t border-slate-800 pt-2">
        <div className="mb-1 text-[11px] uppercase tracking-widest text-slate-400">Free-text disruption</div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="e.g. sudden thunderstorm over Sector Gamma; Hospital B emergency protocol activated"
          className="w-full rounded border border-slate-700 bg-mission-bg p-2 text-xs text-slate-200"
        />
        <button
          disabled={loading || !text.trim()}
          onClick={() => {
            replan({ type: 'storm', x: center.x, y: center.y, r: 220 }, flownSteps, text.trim())
            setText('')
          }}
          className="mt-1 w-full rounded bg-amber-500 px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-amber-400 disabled:opacity-50"
        >
          {loading ? 'Replanning…' : 'Trigger Disruption & Replan'}
        </button>
      </div>

      {(lastDisrupt || lastReplan) && (
        <div className="rounded border border-slate-700 bg-mission-bg p-2 mono text-[11px] text-slate-300">
          {lastDisrupt && (
            <div className="text-amber-300">⚠ {String((lastDisrupt.summary as string) || 'disruption injected')}</div>
          )}
          {lastReplan && (
            <div className="mt-1">
              new dist <span className="text-cyan-300">{String(lastReplan.dist)} m</span> · feasible{' '}
              <span className={lastReplan.feasible ? 'text-emerald-400' : 'text-red-400'}>
                {String(lastReplan.feasible)}
              </span>{' '}
              · V(π) <span className={lastReplan.verifier_ok ? 'text-emerald-400' : 'text-red-400'}>
                {String(lastReplan.verifier_ok)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
