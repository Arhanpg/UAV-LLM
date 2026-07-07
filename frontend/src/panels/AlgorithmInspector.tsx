import { useMemo } from 'react'
import { useMission } from '../store/missionStore'
import type { TelemetryEvent } from '../api/types'

function last(events: TelemetryEvent[], type: string): TelemetryEvent | undefined {
  for (let i = events.length - 1; i >= 0; i--) if (events[i].type === type) return events[i]
  return undefined
}

function Phase1Table() {
  const events = useMission((s) => s.events)
  const step = last(events, 'phase1_step')
  if (!step) return null
  const cands = (step.candidates as { node: number; role: string; score: number }[]) ?? []
  const selected = step.selected as number
  return (
    <div>
      <div className="mono mb-1 text-[10px] uppercase tracking-widest text-cyan-400">
        Phase 1 · greedy step {String(step.step)} · payload {String(step.payload)}/{String(step.cap)} kg
      </div>
      <div className="mono mb-2 rounded bg-black/40 p-2 text-[11px] text-emerald-300">
        f(i',j') = α·(d_min/dis) + (1−α)·(δ/w_max), α=0.7 → selected node {String(selected)} @ f={String(step.score)}
      </div>
      <table className="w-full text-left text-[11px]">
        <thead className="text-slate-500">
          <tr>
            <th className="py-0.5">node</th>
            <th>role</th>
            <th className="text-right">fitness f</th>
          </tr>
        </thead>
        <tbody className="mono">
          {cands.map((c) => (
            <tr key={c.node} className={c.node === selected ? 'text-amber-300' : 'text-slate-300'}>
              <td className="py-0.5">{c.node}</td>
              <td>{c.role}</td>
              <td className="text-right">{c.score.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Phase2Panel() {
  const events = useMission((s) => s.events)
  const attempts = events.filter((e) => e.type === 'phase2_subtrajectory_attempt').slice(-6)
  if (!attempts.length) return null
  return (
    <div>
      <div className="mono mb-1 text-[10px] uppercase tracking-widest text-cyan-400">
        Phase 2 · Algorithm 1 sub-trajectory TSP (MST-preorder)
      </div>
      <table className="w-full text-left text-[11px] mono">
        <thead className="text-slate-500">
          <tr>
            <th>s[i]→s[j]</th>
            <th className="text-right">d_old</th>
            <th className="text-right">d_new</th>
            <th className="text-right">✓</th>
          </tr>
        </thead>
        <tbody>
          {attempts.map((a, i) => (
            <tr key={i} className={a.accepted ? 'text-emerald-300' : 'text-slate-400'}>
              <td>
                {String(a.i)}→{String(a.j)}
              </td>
              <td className="text-right">{String(a.d_old)}</td>
              <td className="text-right">{String(a.d_new)}</td>
              <td className="text-right">{a.accepted ? 'replace' : 'stop'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function LLMPanel() {
  const events = useMission((s) => s.events)
  const prompt = last(events, 'llm_prompt_sent')
  const resp = last(events, 'llm_response_received')
  const psis = events.filter((e) => e.type === 'psi_synthesis_result').slice(-4)
  const verifies = events.filter((e) => e.type === 'smt_verify_result' && e.scope === 'psi')
  const routeV = last(events, 'smt_verify_result')
  const vFor = (req: number) => verifies.find((v) => v.req === req)
  return (
    <div className="space-y-2">
      <div className="mono text-[10px] uppercase tracking-widest text-cyan-400">Ψ synthesis · Ollama structured output</div>
      {prompt && (
        <div className="rounded bg-black/40 p-2 text-[10px] text-slate-400">
          <span className="text-slate-500">prompt→ </span>
          {String(prompt.text).slice(0, 140)}
        </div>
      )}
      {resp && (
        <div className="rounded bg-black/40 p-2 text-[10px] text-slate-300">
          <span className="text-slate-500">response[{String(resp.source)}]→ </span>
          {String(resp.response ?? '').slice(0, 160) || '(structured)'}
        </div>
      )}
      {psis.map((p, i) => {
        const v = vFor(p.req as number)
        const ok = v?.ok
        return (
          <div key={i} className="flex items-center justify-between rounded border border-slate-700 px-2 py-1 text-[11px] mono">
            <span className="text-slate-300">
              req {String(p.req)} · {String(p.kappa)} · τ{JSON.stringify(p.temp)} · P{String(p.priority)}
            </span>
            <span className={ok ? 'text-emerald-400' : 'text-red-400'}>{ok ? 'V=1 ✓' : 'V=0 ✗'}</span>
          </div>
        )
      })}
      {routeV && routeV.scope === 'route' && (
        <div className={`rounded border px-2 py-1 text-[11px] ${routeV.discrepancy ? 'border-red-600 text-red-300' : 'border-emerald-700 text-emerald-300'}`}>
          Z3 route re-check: {routeV.ok ? 'feasible' : 'infeasible'}
          {routeV.discrepancy ? ` · ${String(routeV.discrepancy)}` : ' · matches cost.evaluate'}
        </div>
      )}
    </div>
  )
}

export function AlgorithmInspector() {
  const events = useMission((s) => s.events)
  const phase = useMemo(() => {
    const t = events[events.length - 1]?.type ?? 'idle'
    if (t.startsWith('phase1')) return 'PHASE 1 · Greedy construction'
    if (t.startsWith('phase2')) return 'PHASE 2 · TSP refinement'
    if (t.startsWith('llm') || t.startsWith('psi')) return 'Ψ · LLM synthesis'
    if (t.startsWith('smt')) return 'V · SMT verification'
    if (t.startsWith('replan') || t === 'disruption_detected') return 'Δ · Replanning'
    if (t === 'route_finalized') return 'Route finalized'
    return 'Idle'
  }, [events])

  return (
    <div className="flex h-full flex-col gap-3 overflow-y-auto p-3 text-sm">
      <div className="rounded bg-cyan-500/10 px-2 py-1 text-xs font-semibold text-cyan-300">{phase}</div>
      <Phase1Table />
      <Phase2Panel />
      <LLMPanel />
      <div>
        <div className="mono mb-1 text-[10px] uppercase tracking-widest text-slate-500">event stream ({events.length})</div>
        <div className="max-h-40 space-y-0.5 overflow-y-auto rounded bg-black/30 p-2 mono text-[10px] text-slate-400">
          {events.slice(-40).map((e, i) => (
            <div key={i}>
              <span className="text-cyan-500">{e.type}</span>{' '}
              {Object.entries(e)
                .filter(([k]) => !['type', 't', 'candidates', 'order', 'route', 'response', 'prompt'].includes(k))
                .slice(0, 4)
                .map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`)
                .join(' ')}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
