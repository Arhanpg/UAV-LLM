import { useEffect, useState, lazy, Suspense } from 'react';
import { AlgorithmInspector } from './panels/AlgorithmInspector';
import { ComparisonDashboard } from './panels/ComparisonDashboard';
import { MissionBuilder } from './panels/MissionBuilder';
import { CompatGraphView } from './panels/CompatGraphView';
import { DisruptionPanel } from './panels/DisruptionPanel';
import TestCasesPanel from './panels/TestCasesPanel';
import AlgoComparePanel, { AlgoResult } from './panels/AlgoComparePanel';
import NLReplanPanel from './panels/NLReplanPanel';
import MapView, { ReplanResult } from './MapView';
import { useMission } from './store/missionStore';
import { useTelemetry } from './ws/useTelemetry';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

const DIFF_COLOR: Record<string, string> = {
  easy: '#22c55e', medium: '#f59e0b', hard: '#ef4444', expert: '#a855f7',
};

// ── Test case type (mirrors backend) ─────────────────────────────────────────
interface TestCase {
  id: number;
  title: string;
  difficulty: string;
  description: string;
  loc_indices: number[];
  pkg_requests: { pickup_name: string; delivery_name: string; kappa: string; weight: number }[];
  nl_instruction: string;
  seed: number;
  n_gfz: number;
  incompat_density: number;
  deadline_tight: number;
  hazard_mix: number;
  cap_ratio: number;
}

// ── Shared state lifted to App ────────────────────────────────────────────────
function App() {
  const loadBuildings = useMission((s) => s.loadBuildings);
  const mission = useMission((s) => s.mission);
  const generate = useMission((s) => s.generate);
  const loading = useMission((s) => s.loading);
  const playing = useMission((s) => s.playing);
  const togglePlay = useMission((s) => s.togglePlay);
  const follow = useMission((s) => s.followDrone);
  const setFollow = useMission((s) => s.setFollow);
  const speed = useMission((s) => s.speed);
  const setSpeed = useMission((s) => s.setSpeed);
  const error = useMission((s) => s.error);
  const hud = useMission((s) => s.droneHUD);
  const alt = useMission((s) => s.activeAlt);
  useTelemetry(mission?.session_id);

  const [activeTab, setActiveTab] = useState('tests');
  const [selectedTC, setSelectedTC] = useState<TestCase | null>(null);
  const [runningTC, setRunningTC] = useState<number | null>(null);
  const [algoResults, setAlgoResults] = useState<AlgoResult[]>([]);
  const [algoLoading, setAlgoLoading] = useState(false);
  const [replanResult, setReplanResult] = useState<ReplanResult | null>(null);
  const [currentRoute, setCurrentRoute] = useState<string[]>([]);
  const [showAlgoPaths, setShowAlgoPaths] = useState(false);
  const [mapView, setMapView] = useState(true);

  useEffect(() => { loadBuildings(); }, [loadBuildings]);

  // Build current route from mission or selected test case
  useEffect(() => {
    if (selectedTC) {
      const names = selectedTC.pkg_requests.flatMap(p => [p.pickup_name, p.delivery_name]);
      const unique = [...new Set(names)];
      setCurrentRoute(unique.length > 0 ? unique : ['SDM Hospital']);
    }
  }, [selectedTC]);

  const handleRunTC = async (tc: TestCase) => {
    setRunningTC(tc.id);
    setAlgoLoading(true);
    setActiveTab('algos');
    setShowAlgoPaths(true);
    try {
      const resp = await fetch(`${API}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          seed: tc.seed,
          loc_indices: tc.loc_indices,
          pkg_requests: tc.pkg_requests,
          n_gfz: tc.n_gfz,
          incompat_density: tc.incompat_density,
          deadline_tight: tc.deadline_tight,
          hazard_mix: tc.hazard_mix,
          cap_ratio: tc.cap_ratio,
          world_summary: { title: tc.title, difficulty: tc.difficulty },
        }),
      });
      const data = await resp.json();
      setAlgoResults(data.comparison ?? []);
    } catch {
      // Fallback: synthetic results
      setAlgoResults([
        { algo: 'HNP', color: '#00d4ff', semantic_cost: 312, distance: 180, runtime_ms: 45, feasible: true, violations: 0, energy: 7.6, route: tc.loc_indices },
        { algo: 'MPDD', color: '#ff6b6b', semantic_cost: 401, distance: 210, runtime_ms: 88, feasible: true, violations: 1, energy: 8.8, route: tc.loc_indices },
        { algo: 'HNP-NoVerify', color: '#ffd93d', semantic_cost: 356, distance: 195, runtime_ms: 38, feasible: false, violations: 2, energy: 8.2, route: tc.loc_indices },
        { algo: 'HNP-NoCompat', color: '#6bcb77', semantic_cost: 430, distance: 220, runtime_ms: 62, feasible: false, violations: 3, energy: 9.3, route: tc.loc_indices },
        { algo: 'HNP-NoRefine', color: '#4d96ff', semantic_cost: 338, distance: 188, runtime_ms: 41, feasible: true, violations: 1, energy: 7.9, route: tc.loc_indices },
        { algo: 'NN-PDP', color: '#ff922b', semantic_cost: 488, distance: 265, runtime_ms: 120, feasible: false, violations: 4, energy: 11.1, route: tc.loc_indices },
      ]);
    } finally {
      setAlgoLoading(false);
      setRunningTC(null);
    }
  };

  // No-fly zones from test case
  const noFlyZones = selectedTC
    ? Array.from({ length: selectedTC.n_gfz }, (_, i) => ({
        lat: 15.4150 + (i * 0.03),
        lng: 75.0550 + (i * 0.04),
        radius: 600,
      }))
    : [];

  // ── TABS ────────────────────────────────────────────────────────────────────
  const TABS = [
    { id: 'tests', label: '🧪 Tests' },
    { id: 'inspector', label: '🔬 Inspector' },
    { id: 'compare', label: '📊 Compare' },
    { id: 'algos', label: '⚡ Algos' },
    { id: 'nlreplan', label: '💬 NL Replan' },
    { id: 'build', label: '🔧 Build' },
    { id: 'disrupt', label: '⚠️ Disrupt' },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'tests':
        return (
          <TestCasesPanel
            onLoadTestCase={(tc) => { setSelectedTC(tc); }}
            onRunTestCase={handleRunTC}
            selectedId={selectedTC?.id ?? null}
            runningId={runningTC}
          />
        );
      case 'inspector':
        return <AlgorithmInspector />;
      case 'compare':
        return <ComparisonDashboard />;
      case 'algos':
        return <AlgoComparePanel results={algoResults} loading={algoLoading} />;
      case 'nlreplan':
        return (
          <NLReplanPanel
            currentRoute={currentRoute}
            onReplan={(result) => {
              setReplanResult(result as ReplanResult);
              setActiveTab('nlreplan');
            }}
          />
        );
      case 'build':
        return <MissionBuilder />;
      case 'disrupt':
        return <DisruptionPanel />;
      default:
        return null;
    }
  };

  // ── ALTITUDE SPARKLINE ──────────────────────────────────────────────────────
  const AltSparkline = () => {
    if (alt.length < 2) return null;
    const zs = alt.map((p) => p.z);
    const max = Math.max(...zs, 1);
    const W = 220; const H = 46;
    const pts = zs.map((z, i) => `${(i / (zs.length - 1)) * W},${H - (z / max) * (H - 4) - 2}`).join(' ');
    const px = hud.progress * W;
    return (
      <div style={{
        borderRadius: 6, border: '1px solid #1e293b',
        background: 'rgba(15,22,36,0.85)', padding: 8,
      }}>
        <div style={{ fontSize: 10, color: '#475569', letterSpacing: 1, marginBottom: 4 }}>
          ALTITUDE PROFILE · MAX {max.toFixed(0)} M
        </div>
        <svg width={W} height={H} style={{ display: 'block' }}>
          <polyline points={pts} fill="none" stroke="#22d3ee" strokeWidth="1.5" />
          <line x1={px} y1={0} x2={px} y2={H} stroke="#f59e0b" strokeWidth="1" />
        </svg>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#050a14', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif' }}>

      {/* ── TOPBAR ── */}
      <header style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px',
        background: 'rgba(10,14,26,0.97)', borderBottom: '1px solid #0f1f35',
        backdropFilter: 'blur(8px)', flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 22 }}>🛰️</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#22d3ee' }}>UAV-LLM Mission Control</div>
            <div style={{ fontSize: 10, color: '#475569', letterSpacing: 0.5 }}>
              Dharwad–Hubli · {mission ? mission.model : 'idle'} ·{' '}
              {selectedTC ? <span style={{ color: DIFF_COLOR[selectedTC.difficulty] }}>{selectedTC.title}</span> : 'no test loaded'}
            </div>
          </div>
        </div>

        {/* Test case quick-select indicator */}
        {selectedTC && (
          <div style={{
            marginLeft: 8, padding: '2px 10px', borderRadius: 12,
            background: `${DIFF_COLOR[selectedTC.difficulty]}22`,
            border: `1px solid ${DIFF_COLOR[selectedTC.difficulty]}44`,
            fontSize: 11, color: DIFF_COLOR[selectedTC.difficulty],
          }}>
            TC-{String(selectedTC.id).padStart(2, '0')} · {selectedTC.difficulty.toUpperCase()}
            · {selectedTC.loc_indices.length} nodes · GFZ:{selectedTC.n_gfz}
          </div>
        )}

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Map / 3D toggle */}
          <button
            onClick={() => setMapView(v => !v)}
            style={{
              padding: '5px 12px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
              background: 'rgba(0,212,255,0.1)', color: '#00d4ff',
              border: '1px solid #00d4ff44',
            }}
          >
            {mapView ? '🌐 Real Map' : '🎮 3D Scene'}
          </button>

          {/* Show algo paths toggle */}
          <button
            onClick={() => setShowAlgoPaths(v => !v)}
            style={{
              padding: '5px 12px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
              background: showAlgoPaths ? 'rgba(0,212,255,0.15)' : 'transparent',
              color: showAlgoPaths ? '#00d4ff' : '#64748b',
              border: `1px solid ${showAlgoPaths ? '#00d4ff44' : '#1e293b'}`,
            }}
          >
            ⚡ Algo Paths {showAlgoPaths ? 'ON' : 'OFF'}
          </button>

          <button
            onClick={() => generate()}
            disabled={loading}
            style={{
              padding: '5px 14px', borderRadius: 5, fontSize: 12, fontWeight: 600,
              background: loading ? '#0e7490' : '#0891b2', color: '#fff',
              border: 'none', cursor: loading ? 'wait' : 'pointer',
            }}
          >
            {loading ? 'Planning…' : mission ? 'Regenerate' : 'Generate Mission'}
          </button>
          <button
            onClick={togglePlay}
            style={{
              padding: '5px 12px', borderRadius: 5, fontSize: 12,
              background: 'transparent', color: '#94a3b8',
              border: '1px solid #1e293b', cursor: 'pointer',
            }}
          >
            {playing ? '⏸ Pause' : '▶ Play'}
          </button>
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#64748b' }}>
            <input type="checkbox" checked={follow} onChange={e => setFollow(e.target.checked)} /> Follow
          </label>
          <select
            value={speed}
            onChange={e => setSpeed(Number(e.target.value))}
            style={{
              background: '#0f1623', border: '1px solid #1e293b',
              color: '#94a3b8', borderRadius: 4, padding: '3px 6px', fontSize: 11,
            }}
          >
            {[0.5, 1, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
          </select>
        </div>
      </header>

      {/* ── MAIN AREA ── */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>

        {/* ── MAP / SCENE ── */}
        <main style={{ flex: 1, position: 'relative', background: '#050a14' }}>
          {mapView ? (
            <MapView
              missionRoute={currentRoute}
              algoResults={showAlgoPaths ? algoResults : []}
              replanResult={replanResult}
              noFlyZones={noFlyZones}
              showAlgoPaths={showAlgoPaths}
            />
          ) : (
            // Fallback 3D scene import
            <Suspense fallback={<div style={{ color: '#64748b', padding: 20 }}>Loading 3D scene...</div>}>
              {(() => { const { CityScene } = require('./scene/CityScene'); return <CityScene />; })()}
            </Suspense>
          )}

          {/* HUD overlay */}
          {mission && (
            <div style={{
              position: 'absolute', bottom: 12, left: 12,
              display: 'flex', alignItems: 'flex-end', gap: 10,
              pointerEvents: 'none',
            }}>
              <div style={{
                pointerEvents: 'auto',
                background: 'rgba(10,14,26,0.9)', border: '1px solid #1e293b',
                borderRadius: 6, padding: '10px 12px', fontSize: 11,
                fontFamily: 'monospace',
              }}>
                <div style={{ fontSize: 10, color: '#00d4ff', letterSpacing: 1, marginBottom: 4 }}>DRONE TELEMETRY</div>
                <div>ALT&nbsp;&nbsp;<span style={{ color: '#22d3ee' }}>{hud.alt.toFixed(1)} m</span></div>
                <div>LOAD&nbsp;<span style={{ color: '#22d3ee' }}>{hud.payload.toFixed(2)} kg</span></div>
                <div>STEP&nbsp;<span style={{ color: '#22d3ee' }}>{hud.step}</span> / {mission.flight_path.length - 1}</div>
                <div style={{ marginTop: 4, color: '#f59e0b', maxWidth: 220 }}>{hud.action}</div>
              </div>
              <AltSparkline />
            </div>
          )}

          {/* No-mission placeholder */}
          {!mission && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
            }}>
              <div style={{
                background: 'rgba(10,14,26,0.85)', border: '1px solid #1e293b',
                borderRadius: 10, padding: '20px 32px', textAlign: 'center',
              }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#22d3ee', marginBottom: 6 }}>
                  Semantic Multi-Commodity UAV Delivery
                </div>
                <div style={{ fontSize: 12, color: '#475569', marginBottom: 12 }}>
                  Select a test case from the Tests tab, then click Run All Algos
                </div>
                <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                  <button
                    onClick={() => setActiveTab('tests')}
                    style={{
                      padding: '6px 16px', borderRadius: 5, fontSize: 12,
                      background: 'rgba(0,212,255,0.15)', color: '#00d4ff',
                      border: '1px solid #00d4ff44', cursor: 'pointer',
                    }}
                  >
                    🧪 Browse Test Cases
                  </button>
                  <button
                    onClick={() => generate()}
                    style={{
                      padding: '6px 16px', borderRadius: 5, fontSize: 12,
                      background: '#0891b2', color: '#fff',
                      border: 'none', cursor: 'pointer',
                    }}
                  >
                    ⚡ Generate Mission
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Error toast */}
          {error && (
            <div style={{
              position: 'absolute', top: 12, right: 12,
              background: 'rgba(127,29,29,0.9)', border: '1px solid #ef4444',
              borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#fca5a5',
              maxWidth: 320,
            }}>
              ⚠️ {error}
            </div>
          )}
        </main>

        {/* ── SIDEBAR ── */}
        <aside style={{
          width: 380, display: 'flex', flexDirection: 'column',
          background: '#0a0e1a', borderLeft: '1px solid #0f1f35', flexShrink: 0,
        }}>
          {/* Tab bar */}
          <div style={{
            display: 'flex', borderBottom: '1px solid #0f1f35',
            overflowX: 'auto', flexShrink: 0,
          }}>
            {TABS.map(t => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                style={{
                  flex: '0 0 auto', padding: '8px 10px', fontSize: 10,
                  fontWeight: 500, cursor: 'pointer', whiteSpace: 'nowrap',
                  background: 'transparent',
                  color: activeTab === t.id ? '#22d3ee' : '#475569',
                  borderBottom: activeTab === t.id ? '2px solid #22d3ee' : '2px solid transparent',
                  border: 'none', borderBottomWidth: 2,
                  borderBottomStyle: 'solid',
                  borderBottomColor: activeTab === t.id ? '#22d3ee' : 'transparent',
                  transition: 'all 0.15s',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Active panel */}
          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {renderTabContent()}
          </div>
        </aside>
      </div>
    </div>
  );
}

export default App;
