import { useEffect } from 'react'
import { CityScene } from './scene/CityScene'
import { useMission } from './store/missionStore'
import { useTelemetry } from './ws/useTelemetry'

function AltSparkline() {
  const alt = useMission((s) => s.activeAlt)
  const hud = useMission((s) => s.droneHUD)
  if (alt.length < 2) return null
  const zs = alt.map((p) => p.z)
  const max = Math.max(...zs, 1)
  const W = 220
  const H = 46
  const pts = zs.map((z, i) => `${(i / (zs.length - 1)) * W},${H - (z / max) * (H - 4) - 2}`).join(' ')
  const px = hud.progress * W
  return (
    <div className="rounded-md border border-slate-700 bg-mission-panel/80 p-2">
      <div className="mono mb-1 text-[10px] uppercase tracking-widest text-slate-400">
        Altitude profile · max {max.toFixed(0)} m
      </div>
      <svg width={W} height={H} className="block">
        <polyline points={pts} fill="none" stroke="#22d3ee" strokeWidth="1.5" />
        <line x1={px} y1={0} x2={px} y2={H} stroke="#f59e0b" strokeWidth="1" />
      </svg>
    </div>
  )
}

function Hud() {
  const hud = useMission((s) => s.droneHUD)
  const mission = useMission((s) => s.mission)
  if (!mission) return null
  return (
    <div className="pointer-events-none absolute bottom-4 left-4 flex items-end gap-3">
      <div className="pointer-events-auto rounded-md border border-slate-700 bg-mission-panel/80 p-3 mono text-xs text-slate-200">
        <div className="mb-1 text-[10px] uppercase tracking-widest text-cyan-400">Drone telemetry</div>
        <div>ALT&nbsp;&nbsp;<span className="text-cyan-300">{hud.alt.toFixed(1)} m</span></div>
        <div>LOAD&nbsp;<span className="text-cyan-300">{hud.payload.toFixed(2)} kg</span></div>
        <div>STEP&nbsp;<span className="text-cyan-300">{hud.step}</span> / {mission.flight_path.length - 1}</div>
        <div className="mt-1 max-w-[220px] truncate text-amber-300">{hud.action}</div>
      </div>
      <AltSparkline />
    </div>
  )
}

function TopBar() {
  const generate = useMission((s) => s.generate)
  const loading = useMission((s) => s.loading)
  const playing = useMission((s) => s.playing)
  const togglePlay = useMission((s) => s.togglePlay)
  const follow = useMission((s) => s.followDrone)
  const setFollow = useMission((s) => s.setFollow)
  const speed = useMission((s) => s.speed)
  const setSpeed = useMission((s) => s.setSpeed)
  const mission = useMission((s) => s.mission)
  return (
    <header className="flex items-center gap-3 border-b border-slate-800 bg-mission-panel/90 px-4 py-2 backdrop-blur">
      <div className="flex items-center gap-2">
        <span className="text-lg">🛰️</span>
        <div>
          <div className="text-sm font-semibold text-cyan-300">UAV-LLM Mission Control</div>
          <div className="mono text-[10px] text-slate-500">
            Dharwad–Hubli · {mission ? mission.model : 'idle'} · {mission?.llm_mode ?? ''}
          </div>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={() => generate()}
          disabled={loading}
          className="rounded bg-cyan-500 px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-cyan-400 disabled:opacity-50"
        >
          {loading ? 'Planning…' : mission ? 'Regenerate' : 'Generate Mission'}
        </button>
        <button
          onClick={togglePlay}
          className="rounded border border-slate-600 px-3 py-1.5 text-sm text-slate-200 hover:border-cyan-400"
        >
          {playing ? '⏸ Pause' : '▶ Play'}
        </button>
        <label className="flex items-center gap-1 text-xs text-slate-300">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> Follow
        </label>
        <select
          value={speed}
          onChange={(e) => setSpeed(Number(e.target.value))}
          className="rounded border border-slate-600 bg-mission-bg px-2 py-1 text-xs text-slate-200"
        >
          {[0.5, 1, 2, 4].map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </div>
    </header>
  )
}

export default function App() {
  const loadBuildings = useMission((s) => s.loadBuildings)
  const mission = useMission((s) => s.mission)
  const error = useMission((s) => s.error)
  useTelemetry(mission?.session_id)
  useEffect(() => {
    loadBuildings()
  }, [loadBuildings])

  return (
    <div className="flex h-screen flex-col bg-mission-bg text-slate-100">
      <TopBar />
      <main className="relative flex-1">
        <CityScene />
        <Hud />
        {error && (
          <div className="absolute right-4 top-4 max-w-sm rounded border border-red-700 bg-red-950/80 p-3 text-xs text-red-200">
            {error}
          </div>
        )}
        {!mission && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <div className="rounded-lg border border-slate-700 bg-mission-panel/80 px-6 py-4 text-center text-slate-300">
              <div className="text-lg font-semibold text-cyan-300">Semantic Multi-Commodity UAV Delivery</div>
              <div className="mt-1 text-sm text-slate-400">
                Click “Generate Mission” to plan a real LLM-driven mission over Dharwad–Hubli.
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
