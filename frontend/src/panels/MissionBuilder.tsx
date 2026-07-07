import { useState } from 'react'
import { useMission } from '../store/missionStore'
import { KAPPA_COLOR } from '../scene/coords'

const CLASSES = ['PHARMA', 'FOOD', 'ELECTRONICS', 'FLAMMABLE', 'OXIDIZER', 'CRYOGENIC', 'GENERAL']

export function MissionBuilder() {
  const mission = useMission((s) => s.mission)
  const selectedNode = useMission((s) => s.selectedNode)
  const builder = useMission((s) => s.builder)
  const addBuilder = useMission((s) => s.addBuilder)
  const removeBuilder = useMission((s) => s.removeBuilder)
  const clearBuilder = useMission((s) => s.clearBuilder)
  const generate = useMission((s) => s.generate)
  const selectNode = useMission((s) => s.selectNode)

  const [delivery, setDelivery] = useState<number | null>(null)
  const [kappa, setKappa] = useState('PHARMA')
  const [weight, setWeight] = useState(1.5)
  const [desc, setDesc] = useState('')

  if (!mission) return <div className="p-3 text-sm text-slate-500">Generate a mission first, then click nodes to build packages.</div>
  const node = mission.city.find((c) => c.idx === selectedNode)

  return (
    <div className="space-y-3 overflow-y-auto p-3 text-sm">
      <div className="text-xs text-slate-400">
        Click a 3D node to anchor a pickup, choose a destination + commodity, and add it. The free-text description feeds Ψ.
      </div>

      {node ? (
        <div className="rounded border border-cyan-700 bg-cyan-500/5 p-2">
          <div className="text-sm font-semibold text-cyan-300">{node.label}</div>
          <div className="mono text-[10px] text-slate-500">
            {node.category} · {node.lat.toFixed(4)},{node.lon.toFixed(4)} · {node.bh} m
          </div>
          <div className="mt-2 space-y-1">
            <label className="block text-[11px] text-slate-400">Deliver to</label>
            <select
              value={delivery ?? ''}
              onChange={(e) => setDelivery(e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded border border-slate-600 bg-mission-bg px-2 py-1 text-xs"
            >
              <option value="">— select destination —</option>
              {mission.city.filter((c) => c.idx !== node.idx).map((c) => (
                <option key={c.idx} value={c.idx}>
                  {c.label}
                </option>
              ))}
            </select>
            <div className="flex gap-2">
              <select value={kappa} onChange={(e) => setKappa(e.target.value)} className="flex-1 rounded border border-slate-600 bg-mission-bg px-2 py-1 text-xs">
                {CLASSES.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
              <input
                type="number"
                step="0.1"
                value={weight}
                onChange={(e) => setWeight(Number(e.target.value))}
                className="w-16 rounded border border-slate-600 bg-mission-bg px-2 py-1 text-xs"
              />
            </div>
            <input
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="e.g. urgent insulin, keep 2–8°C cold chain"
              className="w-full rounded border border-slate-600 bg-mission-bg px-2 py-1 text-xs"
            />
            <button
              onClick={() => {
                if (delivery === null) return
                addBuilder({ pickupNode: node.idx, deliveryNode: delivery, kappa, weight, deadline: null, desc })
                setDesc('')
              }}
              disabled={delivery === null}
              className="w-full rounded bg-cyan-500 py-1 text-xs font-medium text-slate-900 hover:bg-cyan-400 disabled:opacity-40"
            >
              + Add package
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded border border-slate-700 p-2 text-xs text-slate-500">No node selected — click a pin in the 3D scene.</div>
      )}

      <div>
        <div className="mono mb-1 flex items-center justify-between text-[10px] uppercase tracking-widest text-slate-400">
          <span>Draft packages ({builder.length})</span>
          {builder.length > 0 && (
            <button onClick={clearBuilder} className="text-red-400 hover:text-red-300">
              clear
            </button>
          )}
        </div>
        {builder.map((b) => {
          const p = mission.city.find((c) => c.idx === b.pickupNode)?.label
          const d = mission.city.find((c) => c.idx === b.deliveryNode)?.label
          return (
            <div key={b.id} className="mb-1 flex items-center justify-between rounded border border-slate-700 px-2 py-1 text-[11px]">
              <span>
                <span style={{ color: KAPPA_COLOR[b.kappa] }}>●</span> {b.kappa} {b.weight}kg · {p} → {d}
              </span>
              <button onClick={() => removeBuilder(b.id)} className="text-slate-500 hover:text-red-400">
                ✕
              </button>
            </div>
          )
        })}
        {builder.length > 0 && (
          <button
            onClick={() => {
              generate()
              selectNode(null)
            }}
            className="mt-1 w-full rounded bg-emerald-500 py-1 text-xs font-medium text-slate-900 hover:bg-emerald-400"
          >
            ▶ Plan mission with {builder.length} package{builder.length > 1 ? 's' : ''}
          </button>
        )}
      </div>
    </div>
  )
}
