import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useMission } from '../store/missionStore'

const ORDER = ['MPDD', 'HNP', 'HNP-NoVerify', 'HNP-NoCompat', 'HNP-NoRefine', 'NN-PDP']
const COLOR: Record<string, string> = {
  HNP: '#22d3ee',
  MPDD: '#818cf8',
  'HNP-NoVerify': '#f472b6',
  'HNP-NoCompat': '#fb923c',
  'HNP-NoRefine': '#a78bfa',
  'NN-PDP': '#64748b',
}

function Metric({ title, unit, pick }: { title: string; unit: string; pick: (m: Record<string, number | boolean>) => number }) {
  const results = useMission((s) => s.mission?.results)
  if (!results) return null
  const data = ORDER.filter((k) => results[k]).map((k) => ({ name: k, value: pick(results[k].metrics) }))
  return (
    <div>
      <div className="mono mb-1 text-[10px] uppercase tracking-widest text-slate-400">
        {title} {unit && `(${unit})`}
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
          <XAxis dataKey="name" tick={{ fontSize: 8, fill: '#94a3b8' }} interval={0} angle={-25} textAnchor="end" height={38} />
          <YAxis tick={{ fontSize: 9, fill: '#64748b' }} />
          <Tooltip contentStyle={{ background: '#0d1117', border: '1px solid #334155', fontSize: 11 }} />
          <Bar dataKey="value" radius={[3, 3, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.name} fill={COLOR[d.name] ?? '#38bdf8'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ComparisonDashboard() {
  const mission = useMission((s) => s.mission)
  if (!mission) return <div className="p-3 text-sm text-slate-500">Generate a mission to compare algorithms.</div>
  return (
    <div className="space-y-3 overflow-y-auto p-3">
      <div className="text-xs text-slate-400">
        Six planners on the same instance — every number is a real computation from the backend.
      </div>
      <Metric title="Total flight distance" unit="m" pick={(m) => Number(m.dist)} />
      <Metric title="Objective J(π)" unit="cost" pick={(m) => Number(m.cost)} />
      <Metric title="Constraint violations" unit="" pick={(m) => Number(m.viol)} />
      <Metric title="Execution time" unit="s" pick={(m) => Number(m.runtime)} />
      <table className="w-full text-left text-[11px] mono">
        <thead className="text-slate-500">
          <tr>
            <th>algo</th>
            <th className="text-right">dist</th>
            <th className="text-right">cost</th>
            <th className="text-right">viol</th>
            <th className="text-right">feas</th>
          </tr>
        </thead>
        <tbody>
          {ORDER.filter((k) => mission.results[k]).map((k) => {
            const m = mission.results[k].metrics
            return (
              <tr key={k} className={k === 'HNP' ? 'text-cyan-300' : 'text-slate-300'}>
                <td>{k}</td>
                <td className="text-right">{Number(m.dist).toFixed(0)}</td>
                <td className="text-right">{Number(m.cost).toFixed(0)}</td>
                <td className="text-right">{Number(m.viol)}</td>
                <td className="text-right">{m.feasible ? '✓' : '✗'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
