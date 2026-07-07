import { useMemo } from 'react'
import { useMission } from '../store/missionStore'
import { KAPPA_COLOR } from '../scene/coords'

// Fixed-layout graph of the commodity compatibility graph Gc. Green edges =
// compatible (may co-fly); red = incompatible (Eq. 2). The onboard active set A_i
// must induce a clique in Gc (Eq. 4).
const DEFAULT_CLASSES = ['PHARMA', 'FOOD', 'ELECTRONICS', 'FLAMMABLE', 'OXIDIZER', 'CRYOGENIC', 'GENERAL']

export function CompatGraphView() {
  const mission = useMission((s) => s.mission)
  const classes = mission?.classes ?? DEFAULT_CLASSES
  const incompat = mission?.incompat_pairs ?? []

  const nodes = useMemo(() => {
    const R = 120
    const cx = 150
    const cy = 140
    return classes.map((c, i) => {
      const a = (i / classes.length) * Math.PI * 2 - Math.PI / 2
      return { c, x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) }
    })
  }, [classes])

  const isIncompat = (a: string, b: string) => incompat.some(([x, y]) => (x === a && y === b) || (x === b && y === a))

  return (
    <div className="space-y-2 p-3">
      <div className="text-xs text-slate-400">
        Commodity compatibility graph Gc — the onboard active set must form a clique (Eq. 4). Red edges are co-transport
        conflicts (Eq. 2).
      </div>
      <svg viewBox="0 0 300 280" className="w-full">
        {nodes.map((n, i) =>
          nodes.slice(i + 1).map((m) => {
            const bad = isIncompat(n.c, m.c)
            return (
              <line
                key={`${n.c}-${m.c}`}
                x1={n.x}
                y1={n.y}
                x2={m.x}
                y2={m.y}
                stroke={bad ? '#ef4444' : '#1e3a4a'}
                strokeWidth={bad ? 1.6 : 0.6}
                strokeDasharray={bad ? '0' : '2 3'}
              />
            )
          }),
        )}
        {nodes.map((n) => (
          <g key={n.c}>
            <circle cx={n.x} cy={n.y} r={12} fill={KAPPA_COLOR[n.c] ?? '#64748b'} />
            <text x={n.x} y={n.y + 24} textAnchor="middle" fontSize="8" fill="#cbd5e1" className="mono">
              {n.c}
            </text>
          </g>
        ))}
      </svg>
      <div className="mono text-[10px] text-slate-500">
        <span className="text-red-400">━</span> incompatible ({incompat.length} pairs) &nbsp;
        <span className="text-slate-500">┄</span> compatible
      </div>
    </div>
  )
}
