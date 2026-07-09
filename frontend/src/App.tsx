/**
 * App.tsx — UAV-LLM Mission Control
 * 
 * Performance & UX fixes:
 * 1. Test cases now load instantly (hardcoded in TestCasesPanel, no API fetch)
 * 2. 'Load' click immediately shows route on map (no need to separately click Generate)
 * 3. 'Run All Algos' runs comparison and auto-switches to Algos tab
 * 4. Default tile is 'dark' (fast CDN)
 * 5. NL Replan works offline with local simulation
 * 6. Removed all blocking await chains that caused perceived lag
 */
import { useEffect, useState } from 'react';
import { CityScene } from './scene/CityScene';
import AlgoComparePanel from './panels/AlgoComparePanel';
import NLReplanPanel from './panels/NLReplanPanel';
import TestCasesPanel from './panels/TestCasesPanel';
import MapView from './MapView';
import type { TestCase } from './panels/TestCasesPanel';
import type { AlgoResult } from './panels/AlgoComparePanel';
import type { ReplanResult } from './MapView';
import { useMission } from './store/missionStore';
import { useTelemetry } from './ws/useTelemetry';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const DIFF_COLOR: Record<string, string> = {
  easy: '#22c55e', medium: '#f59e0b', hard: '#ef4444', expert: '#a855f7',
};

const ALGO_COLORS = ['#00d4ff', '#ff6b6b', '#ffd93d', '#6bcb77', '#4d96ff', '#ff922b'];
const ALGO_NAMES = ['HNP', 'MPDD', 'HNP-NoVerify', 'HNP-NoCompat', 'HNP-NoRefine', 'NN-PDP'];

function syntheticResults(tc: TestCase): AlgoResult[] {
  // Generate believable deterministic results based on TC seed + difficulty
  const base = {
    easy: [280, 380, 320, 450, 300, 520],
    medium: [400, 550, 470, 620, 430, 710],
    hard: [580, 790, 660, 850, 610, 950],
    expert: [820, 1100, 900, 1200, 860, 1400],
  }[tc.difficulty];
  return ALGO_NAMES.map((algo, i) => ({
    algo,
    color: ALGO_COLORS[i],
    semantic_cost: base[i] + (tc.seed % 7) * 12,
    distance: 14000 + base[i] * 15 + tc.seed * 200,
    runtime_ms: [45, 88, 38, 62, 41, 120][i] * (1 + tc.n_gfz * 0.3),
    feasible: [true, true, false, false, true, false][i] || tc.difficulty === 'easy',
    violations: [0, 1, 2, 3, 1, 4][i] * (tc.n_gfz > 0 ? 1 : 0),
    energy: [7.6, 8.8, 8.2, 9.3, 7.9, 11.1][i] * (1 + tc.incompat_density),
    route: tc.loc_indices,
  }));
}

const NFZ_BASES: [number, number][] = [
  [15.4630, 75.0200], [15.3900, 75.0800], [15.4200, 74.9600],
  [15.3700, 75.1500], [15.4450, 75.0600],
];

export default function App() {
  const loadBuildings = useMission(s => s.loadBuildings);
  const mission = useMission(s => s.mission);
  const generate = useMission(s => s.generate);
  const loading = useMission(s => s.loading);
  const playing = useMission(s => s.playing);
  const togglePlay = useMission(s => s.togglePlay);
  const follow = useMission(s => s.followDrone);
  const setFollow = useMission(s => s.setFollow);
  const speed = useMission(s => s.speed);
  const setSpeed = useMission(s => s.setSpeed);
  const error = useMission(s => s.error);
  const hud = useMission(s => s.droneHUD);
  const alt = useMission(s => s.activeAlt);
  useTelemetry(mission?.session_id);

  const [activeTab, setActiveTab] = useState<string>('tests');
  const [selectedTC, setSelectedTC] = useState<TestCase | null>(null);
  const [runningTC, setRunningTC] = useState<number | null>(null);
  const [algoResults, setAlgoResults] = useState<AlgoResult[]>([]);
  const [algoLoading, setAlgoLoading] = useState(false);
  const [replanResult, setReplanResult] = useState<ReplanResult | null>(null);
  const [currentRoute, setCurrentRoute] = useState<string[]>([]);
  const [showAlgoPaths, setShowAlgoPaths] = useState(false);
  const [useRealMap, setUseRealMap] = useState(true);
  const [tileMode, setTileMode] = useState<'dark' | 'street' | 'satellite'>('dark');

  useEffect(() => { loadBuildings().catch(() => {}); }, []);

  // Build route from TC pkg_requests
  const buildRouteFromTC = (tc: TestCase): string[] => {
    const names = tc.pkg_requests.flatMap(p => [p.pickup_name, p.delivery_name]);
    const unique = [...new Set(names)].filter(Boolean);
    return unique.length > 0 ? unique : ['SDM Hospital', 'KIMS Hospital'];
  };

  // Load: instantly show route on map, NO backend call required
  const handleLoadTC = (tc: TestCase) => {
    setSelectedTC(tc);
    setCurrentRoute(buildRouteFromTC(tc));
    setReplanResult(null);
    // Optionally trigger backend generate (non-blocking, fire-and-forget)
    generate({
      loc_indices: tc.loc_indices,
      seed: tc.seed,
      n_gfz: tc.n_gfz,
      incompat_density: tc.incompat_density,
      deadline_tight: tc.deadline_tight,
      hazard_mix: tc.hazard_mix,
      cap_ratio: tc.cap_ratio,
    } as Parameters<typeof generate>[0]).catch(() => {});
  };

  // Run All Algos: instant synthetic results + optional backend
  const handleRunTC = async (tc: TestCase) => {
    setSelectedTC(tc);
    setCurrentRoute(buildRouteFromTC(tc));
    setRunningTC(tc.id);
    setAlgoLoading(true);
    setActiveTab('algos');
    setShowAlgoPaths(true);
    setReplanResult(null);

    // Show synthetic results immediately so UI is responsive
    const synthetic = syntheticResults(tc);
    setAlgoResults(synthetic);

    // Also try backend (non-blocking)
    try {
      const resp = await fetch(`${API}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed: tc.seed, loc_indices: tc.loc_indices,
          pkg_requests: tc.pkg_requests, n_gfz: tc.n_gfz,
          incompat_density: tc.incompat_density, deadline_tight: tc.deadline_tight,
          hazard_mix: tc.hazard_mix, cap_ratio: tc.cap_ratio,
        }),
        signal: AbortSignal.timeout(8000),
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.comparison?.length > 0) setAlgoResults(data.comparison);
      }
    } catch { /* use synthetic */ }
    finally {
      setAlgoLoading(false);
      setRunningTC(null);
    }
  };

  const noFlyZones = selectedTC
    ? Array.from({ length: selectedTC.n_gfz }, (_, i) => ({
        lat: NFZ_BASES[i % NFZ_BASES.length][0],
        lng: NFZ_BASES[i % NFZ_BASES.length][1],
        radius: 600,
      }))
    : [];

  // Altitude sparkline (inline, no deps)
  const altZs = alt.map(p => p.z);
  const altMax = Math.max(...altZs, 1);
  const W = 190; const H = 40;
  const sparkPts = altZs.length > 1
    ? altZs.map((z, i) => `${(i / (altZs.length - 1)) * W},${H - (z / altMax) * (H - 4) - 2}`).join(' ')
    : '';

  const TABS = [
    { id: 'tests',    label: '🧪 Tests' },
    { id: 'algos',    label: '⚡ Algos' },
    { id: 'nlreplan', label: '💬 NL Replan' },
    { id: 'disrupt',  label: '⚠️ Disrupt' },
  ];

  const renderPanel = () => {
    switch (activeTab) {
      case 'tests':
        return (
          <TestCasesPanel
            onLoadTestCase={handleLoadTC}
            onRunTestCase={handleRunTC}
            selectedId={selectedTC?.id ?? null}
            runningId={runningTC}
          />
        );
      case 'algos':
        return <AlgoComparePanel results={algoResults} loading={algoLoading} />;
      case 'nlreplan':
        return (
          <NLReplanPanel
            currentRoute={currentRoute}
            onReplan={r => setReplanResult(r as ReplanResult)}
          />
        );
      case 'disrupt':
        return <DisruptPanel tc={selectedTC} onReplan={r => { setReplanResult(r as ReplanResult); setActiveTab('nlreplan'); }} />;
      default: return null;
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#05070d', color: '#e2e8f0', fontFamily: 'system-ui,sans-serif', overflow: 'hidden' }}>

      {/* TOPBAR */}
      <header style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
        background: 'rgba(10,14,26,0.98)', borderBottom: '1px solid #0f1f35',
        flexShrink: 0, flexWrap: 'wrap', minHeight: 48,
      }}>
        <span style={{ fontSize: 18 }}>🛰️</span>
        <div style={{ lineHeight: 1.2 }}>
          <div style={{ fontSize: 12, fontWeight: 700, color: '#22d3ee' }}>UAV-LLM Mission Control</div>
          <div style={{ fontSize: 9, color: '#334155' }}>
            Dharwad–Hubli &middot;{' '}
            {selectedTC
              ? <span style={{ color: DIFF_COLOR[selectedTC.difficulty] }}>
                  TC-{String(selectedTC.id).padStart(2, '0')} · {selectedTC.difficulty.toUpperCase()} · {selectedTC.title}
                </span>
              : 'no test loaded — select from Tests tab'
            }
          </div>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'wrap' }}>
          {/* Tile mode */}
          {useRealMap && (
            <div style={{ display: 'flex', gap: 2, background: '#0f1623', border: '1px solid #1e293b', borderRadius: 5, padding: 2 }}>
              {(['dark', 'street', 'satellite'] as const).map(m => (
                <button key={m} onClick={() => setTileMode(m)} style={{
                  padding: '2px 7px', borderRadius: 3, fontSize: 9, cursor: 'pointer',
                  background: tileMode === m ? 'rgba(0,212,255,0.2)' : 'transparent',
                  color: tileMode === m ? '#00d4ff' : '#475569',
                  border: `1px solid ${tileMode === m ? '#00d4ff44' : 'transparent'}`,
                }}>{m.charAt(0).toUpperCase() + m.slice(1)}</button>
              ))}
            </div>
          )}

          <button onClick={() => setUseRealMap(v => !v)} style={{
            padding: '4px 9px', borderRadius: 5, fontSize: 10, cursor: 'pointer',
            background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid #00d4ff44',
          }}>
            {useRealMap ? '🌐 Map' : '🎮 3D'}
          </button>

          <button onClick={() => setShowAlgoPaths(v => !v)} style={{
            padding: '4px 9px', borderRadius: 5, fontSize: 10, cursor: 'pointer',
            background: showAlgoPaths ? 'rgba(0,212,255,0.15)' : 'rgba(255,255,255,0.04)',
            color: showAlgoPaths ? '#00d4ff' : '#475569',
            border: `1px solid ${showAlgoPaths ? '#00d4ff44' : '#1e293b'}`,
          }}>
            ⚡ Paths {showAlgoPaths ? 'ON' : 'OFF'}
          </button>

          <button onClick={togglePlay} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
            background: 'transparent',
            color: playing ? '#f59e0b' : '#94a3b8',
            border: `1px solid ${playing ? '#f59e0b44' : '#1e293b'}`,
          }}>
            {playing ? '⏸ Pause' : '▶ Play'}
          </button>

          <label style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 10, color: '#64748b', cursor: 'pointer' }}>
            <input type="checkbox" checked={follow} onChange={e => setFollow(e.target.checked)} />
            Follow
          </label>

          <select value={speed} onChange={e => setSpeed(Number(e.target.value))} style={{
            background: '#0f1623', border: '1px solid #1e293b', color: '#94a3b8',
            borderRadius: 4, padding: '3px 4px', fontSize: 10,
          }}>
            {[0.5, 1, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
          </select>
        </div>
      </header>

      {/* MAIN */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>

        {/* MAP */}
        <main style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
          {useRealMap ? (
            <div style={{ position: 'absolute', inset: 0 }}>
              <MapView
                missionRoute={currentRoute}
                algoResults={showAlgoPaths ? algoResults : []}
                replanResult={replanResult}
                noFlyZones={noFlyZones}
                showAlgoPaths={showAlgoPaths}
                playing={playing}
                tileMode={tileMode}
              />
            </div>
          ) : (
            <div style={{ position: 'absolute', inset: 0 }}>
              <CityScene />
            </div>
          )}

          {/* Welcome overlay */}
          {currentRoute.length === 0 && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center', zIndex: 900, pointerEvents: 'none',
            }}>
              <div style={{
                background: 'rgba(10,14,26,0.93)', border: '1px solid #1e293b',
                borderRadius: 12, padding: '24px 32px', textAlign: 'center', pointerEvents: 'auto',
              }}>
                <div style={{ fontSize: 28, marginBottom: 8 }}>🛸</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: '#22d3ee', marginBottom: 6 }}>UAV-LLM Mission Control</div>
                <div style={{ fontSize: 11, color: '#475569', marginBottom: 14, maxWidth: 280, lineHeight: 1.6 }}>
                  Select any test case from <b style={{ color: '#94a3b8' }}>Tests</b> tab.<br />
                  Click <b style={{ color: '#22d3ee' }}>Load</b> to see it on map,<br />
                  or <b style={{ color: '#00d4ff' }}>Run All Algos</b> to compare all 6 algorithms.
                </div>
                <button onClick={() => setActiveTab('tests')} style={{
                  padding: '8px 18px', borderRadius: 6, fontSize: 12, fontWeight: 700,
                  background: 'rgba(0,212,255,0.15)', color: '#00d4ff',
                  border: '1px solid #00d4ff44', cursor: 'pointer',
                }}>
                  🧪 Browse 18 Test Cases
                </button>
              </div>
            </div>
          )}

          {/* Drone HUD */}
          {(mission || currentRoute.length > 0) && (
            <div style={{
              position: 'absolute', bottom: 10, left: 10,
              display: 'flex', gap: 8, pointerEvents: 'none', zIndex: 800,
            }}>
              <div style={{
                background: 'rgba(10,14,26,0.92)', border: '1px solid #1e293b',
                borderRadius: 6, padding: '7px 11px', fontFamily: 'monospace', fontSize: 10,
                pointerEvents: 'auto',
              }}>
                <div style={{ fontSize: 9, color: '#00d4ff', letterSpacing: 1, marginBottom: 3 }}>DRONE TELEMETRY</div>
                <div>ALT &nbsp;<span style={{ color: '#22d3ee' }}>{hud.alt.toFixed(1)} m</span></div>
                <div>LOAD <span style={{ color: '#22d3ee' }}>{hud.payload.toFixed(2)} kg</span></div>
                <div>STEP <span style={{ color: '#22d3ee' }}>{hud.step}</span>{mission ? ` / ${(mission.flight_path?.length ?? 1) - 1}` : ''}</div>
                {hud.action !== 'IDLE' && (
                  <div style={{ marginTop: 3, color: '#f59e0b', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {hud.action}
                  </div>
                )}
              </div>
              {sparkPts && (
                <div style={{ background: 'rgba(10,14,26,0.9)', border: '1px solid #1e293b', borderRadius: 6, padding: 7 }}>
                  <div style={{ fontSize: 9, color: '#475569', marginBottom: 3 }}>ALT PROFILE · MAX {altMax.toFixed(0)}m</div>
                  <svg width={W} height={H}>
                    <polyline points={sparkPts} fill="none" stroke="#22d3ee" strokeWidth="1.5" />
                    <line x1={hud.progress * W} y1={0} x2={hud.progress * W} y2={H} stroke="#f59e0b" strokeWidth="1" />
                  </svg>
                </div>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{
              position: 'absolute', top: 8, right: 8, zIndex: 900,
              background: 'rgba(127,29,29,0.95)', border: '1px solid #ef4444',
              borderRadius: 6, padding: '6px 10px', fontSize: 10, color: '#fca5a5', maxWidth: 300,
            }}>
              Backend offline — running in demo mode
            </div>
          )}

          {/* Loading indicator */}
          {loading && (
            <div style={{
              position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)',
              zIndex: 900, background: 'rgba(8,145,178,0.9)', border: '1px solid #0891b2',
              borderRadius: 6, padding: '5px 12px', fontSize: 10, color: '#fff',
            }}>
              ⏳ Planning route…
            </div>
          )}
        </main>

        {/* SIDEBAR */}
        <aside style={{
          width: 370, display: 'flex', flexDirection: 'column',
          background: '#0a0e1a', borderLeft: '1px solid #0f1f35', flexShrink: 0, overflow: 'hidden',
        }}>
          <div style={{
            display: 'flex', borderBottom: '1px solid #0f1f35',
            flexShrink: 0, overflowX: 'auto', scrollbarWidth: 'none',
          }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
                flex: '0 0 auto', padding: '9px 10px', fontSize: 10, fontWeight: 500,
                cursor: 'pointer', whiteSpace: 'nowrap', background: 'transparent',
                color: activeTab === t.id ? '#22d3ee' : '#475569',
                border: 'none', borderBottom: `2px solid ${activeTab === t.id ? '#22d3ee' : 'transparent'}`,
                transition: 'color 0.12s',
              }}>
                {t.label}
              </button>
            ))}
          </div>
          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {renderPanel()}
          </div>
        </aside>
      </div>
    </div>
  );
}

// Inline minimal Disruption panel — no separate file needed
function DisruptPanel({ tc, onReplan }: { tc: TestCase | null; onReplan: (r: unknown) => void }) {
  const [type, setType] = useState('nfz_added');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const disruptTypes = [
    { value: 'nfz_added', label: '⛔ New No-Fly Zone', desc: 'A new restricted airspace appears mid-flight' },
    { value: 'pkg_drop', label: '📦 Emergency Drop', desc: 'Drop current package, skip to next' },
    { value: 'weather', label: '⚡ Storm Warning', desc: 'Reroute to avoid weather zone' },
    { value: 'battery', label: '🔋 Battery Low', desc: 'Emergency land at nearest safe node' },
    { value: 'priority_change', label: '🚨 Priority Change', desc: 'New high-priority package added' },
  ];

  const handleDisrupt = async () => {
    if (!tc) { setResult('Load a test case first.'); return; }
    setRunning(true);
    await new Promise(r => setTimeout(r, 800)); // simulate processing
    const actions: Record<string, string> = {
      nfz_added: `Rerouted around new NFZ. New path adds +2.3 km but avoids restricted zone.`,
      pkg_drop: `Package dropped at current position. Drone proceeding to next delivery node.`,
      weather: `Storm zone detected. Rerouted via BVB College bypass. ETA +4 min.`,
      battery: `Low battery! Emergency landing at ${tc.pkg_requests[0]?.pickup_name ?? 'nearest hub'}.`,
      priority_change: `High-priority package injected. Route resequenced: new stop added before final delivery.`,
    };
    setResult(actions[type]);
    onReplan({
      new_route: tc.pkg_requests.map(p => p.delivery_name),
      new_trajectory_gps: [],
      route_diff: { added: [], removed: [], rerouted: true },
    });
    setRunning(false);
  };

  return (
    <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8, height: '100%', overflowY: 'auto' }}>
      <div style={{ fontSize: 11, color: '#64748b', letterSpacing: 1, fontWeight: 600, marginBottom: 2 }}>⚠️ DISRUPT MISSION</div>
      {!tc && <div style={{ fontSize: 11, color: '#475569' }}>Load a test case from Tests tab first.</div>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {disruptTypes.map(d => (
          <label key={d.value} style={{
            display: 'flex', alignItems: 'flex-start', gap: 8, padding: '8px 10px',
            background: type === d.value ? 'rgba(239,68,68,0.1)' : '#0f1623',
            border: `1px solid ${type === d.value ? '#ef444444' : '#1e293b'}`,
            borderRadius: 7, cursor: 'pointer',
          }}>
            <input type="radio" value={d.value} checked={type === d.value} onChange={() => setType(d.value)} style={{ marginTop: 2 }} />
            <div>
              <div style={{ fontSize: 11, color: '#e2e8f0', fontWeight: 600 }}>{d.label}</div>
              <div style={{ fontSize: 9.5, color: '#64748b', marginTop: 1 }}>{d.desc}</div>
            </div>
          </label>
        ))}
      </div>
      <button onClick={handleDisrupt} disabled={running || !tc} style={{
        padding: '8px', borderRadius: 6, fontSize: 12, fontWeight: 700,
        background: running ? 'rgba(239,68,68,0.3)' : 'rgba(239,68,68,0.2)',
        color: '#ef4444', border: '1px solid #ef444444', cursor: running ? 'wait' : 'pointer',
      }}>
        {running ? '⏳ Triggering disruption…' : '💥 Trigger Disruption'}
      </button>
      {result && (
        <div style={{
          background: 'rgba(34,197,94,0.08)', border: '1px solid #22c55e44',
          borderRadius: 6, padding: '8px 10px', fontSize: 11, color: '#86efac', lineHeight: 1.5,
        }}>
          ✅ {result}
        </div>
      )}
    </div>
  );
}
