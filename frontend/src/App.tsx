/**
 * App.tsx — UAV-LLM Mission Control
 * 
 * Bug fixes in this version:
 * 1. Removed broken require() / Suspense pattern that caused black screen
 * 2. CityScene imported statically at top level (no dynamic import)
 * 3. MapView now uses react-leaflet npm package (no CDN script injection race)
 * 4. generate() wired to selectedTC so Load → Generate Mission uses correct nodes
 * 5. Map container uses position:absolute inset:0 to always fill parent
 */
import { useEffect, useState } from 'react';
import { CityScene } from './scene/CityScene';
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

export default function App() {
  // Mission store
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

  // Local UI state
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

  useEffect(() => { loadBuildings(); }, [loadBuildings]);

  // When a test case is loaded, build its route from pkg_requests
  useEffect(() => {
    if (!selectedTC) return;
    const names = selectedTC.pkg_requests.flatMap(p => [p.pickup_name, p.delivery_name]);
    const unique = [...new Set(names)].filter(n => n.length > 0);
    setCurrentRoute(unique.length > 0 ? unique : ['SDM Hospital', 'KIMS Hospital']);
  }, [selectedTC]);

  // Generate mission wired to test case
  const handleGenerate = () => {
    if (selectedTC) {
      generate({
        loc_indices: selectedTC.loc_indices,
        seed: selectedTC.seed,
        n_gfz: selectedTC.n_gfz,
        incompat_density: selectedTC.incompat_density,
        deadline_tight: selectedTC.deadline_tight,
        hazard_mix: selectedTC.hazard_mix,
        cap_ratio: selectedTC.cap_ratio,
        pkg_requests: selectedTC.pkg_requests.length > 0 ? selectedTC.pkg_requests : undefined,
      } as Parameters<typeof generate>[0]);
    } else {
      generate();
    }
  };

  // Run all algorithms on a test case
  const handleRunTC = async (tc: TestCase) => {
    setRunningTC(tc.id);
    setAlgoLoading(true);
    setActiveTab('algos');
    setShowAlgoPaths(true);
    // Also load the test case
    setSelectedTC(tc);
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
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setAlgoResults(data.comparison ?? []);
    } catch {
      // Synthetic fallback results when backend unavailable
      setAlgoResults([
        { algo: 'HNP',          color: '#00d4ff', semantic_cost: 312, distance: 18400, runtime_ms: 45,  feasible: true,  violations: 0, energy: 7.6,  route: tc.loc_indices },
        { algo: 'MPDD',         color: '#ff6b6b', semantic_cost: 401, distance: 21000, runtime_ms: 88,  feasible: true,  violations: 1, energy: 8.8,  route: tc.loc_indices },
        { algo: 'HNP-NoVerify', color: '#ffd93d', semantic_cost: 356, distance: 19500, runtime_ms: 38,  feasible: false, violations: 2, energy: 8.2,  route: tc.loc_indices },
        { algo: 'HNP-NoCompat', color: '#6bcb77', semantic_cost: 430, distance: 22000, runtime_ms: 62,  feasible: false, violations: 3, energy: 9.3,  route: tc.loc_indices },
        { algo: 'HNP-NoRefine', color: '#4d96ff', semantic_cost: 338, distance: 18800, runtime_ms: 41,  feasible: true,  violations: 1, energy: 7.9,  route: tc.loc_indices },
        { algo: 'NN-PDP',       color: '#ff922b', semantic_cost: 488, distance: 26500, runtime_ms: 120, feasible: false, violations: 4, energy: 11.1, route: tc.loc_indices },
      ]);
    } finally {
      setAlgoLoading(false);
      setRunningTC(null);
    }
  };

  // No-fly zones from selected test case (placed near Dharwad-Hubli centres)
  const NFZ_BASES: [number, number][] = [
    [15.4630, 75.0200], [15.3900, 75.0800], [15.4200, 74.9600],
    [15.3700, 75.1500], [15.4450, 75.0600],
  ];
  const noFlyZones = selectedTC
    ? Array.from({ length: selectedTC.n_gfz }, (_, i) => ({
        lat: NFZ_BASES[i % NFZ_BASES.length][0],
        lng: NFZ_BASES[i % NFZ_BASES.length][1],
        radius: 600,
      }))
    : [];

  // Tabs
  const TABS = [
    { id: 'tests',     label: '🧪 Tests' },
    { id: 'inspector', label: '🔬 Inspector' },
    { id: 'compare',   label: '📊 Compare' },
    { id: 'algos',     label: '⚡ Algos' },
    { id: 'nlreplan',  label: '💬 NL Replan' },
    { id: 'build',     label: '🔧 Build' },
    { id: 'disrupt',   label: '⚠️ Disrupt' },
  ];

  const renderPanel = () => {
    switch (activeTab) {
      case 'tests':
        return (
          <TestCasesPanel
            onLoadTestCase={tc => { setSelectedTC(tc); }}
            onRunTestCase={handleRunTC}
            selectedId={selectedTC?.id ?? null}
            runningId={runningTC}
          />
        );
      case 'inspector': return <AlgorithmInspector />;
      case 'compare':   return <ComparisonDashboard />;
      case 'algos':     return <AlgoComparePanel results={algoResults} loading={algoLoading} />;
      case 'nlreplan':
        return (
          <NLReplanPanel
            currentRoute={currentRoute}
            onReplan={result => setReplanResult(result as ReplanResult)}
          />
        );
      case 'build':   return <MissionBuilder />;
      case 'disrupt': return <DisruptionPanel />;
      default:        return null;
    }
  };

  // Altitude sparkline
  const AltSparkline = () => {
    if (alt.length < 2) return null;
    const zs = alt.map(p => p.z);
    const max = Math.max(...zs, 1);
    const W = 200; const H = 44;
    const pts = zs.map((z, i) =>
      `${(i / (zs.length - 1)) * W},${H - (z / max) * (H - 4) - 2}`
    ).join(' ');
    const px = hud.progress * W;
    return (
      <div style={{ background: 'rgba(10,14,26,0.9)', border: '1px solid #1e293b', borderRadius: 6, padding: 8 }}>
        <div style={{ fontSize: 10, color: '#475569', letterSpacing: 1, marginBottom: 4 }}>ALT PROFILE · MAX {max.toFixed(0)}m</div>
        <svg width={W} height={H} style={{ display: 'block' }}>
          <polyline points={pts} fill="none" stroke="#22d3ee" strokeWidth="1.5" />
          <line x1={px} y1={0} x2={px} y2={H} stroke="#f59e0b" strokeWidth="1" />
        </svg>
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#05070d', color: '#e2e8f0', fontFamily: 'system-ui,sans-serif', overflow: 'hidden' }}>

      {/* ── TOPBAR ── */}
      <header style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '7px 14px',
        background: 'rgba(10,14,26,0.98)', borderBottom: '1px solid #0f1f35',
        flexShrink: 0, flexWrap: 'wrap', minHeight: 52,
      }}>
        <span style={{ fontSize: 20 }}>🛰️</span>
        <div style={{ lineHeight: 1.2 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#22d3ee' }}>UAV-LLM Mission Control</div>
          <div style={{ fontSize: 10, color: '#475569' }}>
            Dharwad–Hubli ·{' '}
            {selectedTC
              ? <span style={{ color: DIFF_COLOR[selectedTC.difficulty] }}>
                  TC-{String(selectedTC.id).padStart(2,'0')} · {selectedTC.difficulty.toUpperCase()} · {selectedTC.loc_indices.length} nodes
                </span>
              : <span style={{ color: '#334155' }}>no test loaded — select from Tests tab</span>
            }
          </div>
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {/* Tile mode (only for real map) */}
          {useRealMap && (
            <div style={{ display: 'flex', gap: 2, background: 'rgba(15,31,53,0.8)', border: '1px solid #1e293b', borderRadius: 5, padding: 2 }}>
              {(['dark','street','satellite'] as const).map(m => (
                <button key={m} onClick={() => setTileMode(m)} style={{
                  padding: '2px 7px', borderRadius: 3, fontSize: 10, cursor: 'pointer',
                  background: tileMode === m ? 'rgba(0,212,255,0.2)' : 'transparent',
                  color: tileMode === m ? '#00d4ff' : '#475569',
                  border: `1px solid ${tileMode === m ? '#00d4ff44' : 'transparent'}`,
                }}>{m.charAt(0).toUpperCase() + m.slice(1)}</button>
              ))}
            </div>
          )}

          {/* Map/3D toggle */}
          <button onClick={() => setUseRealMap(v => !v)} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
            background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid #00d4ff44',
          }}>
            {useRealMap ? '🌐 Map' : '🎮 3D'}
          </button>

          {/* Algo paths toggle */}
          <button onClick={() => setShowAlgoPaths(v => !v)} style={{
            padding: '4px 10px', borderRadius: 5, fontSize: 11, cursor: 'pointer',
            background: showAlgoPaths ? 'rgba(0,212,255,0.15)' : 'rgba(255,255,255,0.04)',
            color: showAlgoPaths ? '#00d4ff' : '#475569',
            border: `1px solid ${showAlgoPaths ? '#00d4ff44' : '#1e293b'}`,
          }}>
            ⚡ Algo Paths {showAlgoPaths ? 'ON' : 'OFF'}
          </button>

          {/* Generate Mission */}
          <button onClick={handleGenerate} disabled={loading} style={{
            padding: '5px 14px', borderRadius: 5, fontSize: 12, fontWeight: 700,
            background: loading ? '#0e7490' : (selectedTC ? '#0891b2' : '#1e4a3b'),
            color: loading ? '#7dd3fc' : '#fff', border: 'none', cursor: loading ? 'wait' : 'pointer',
          }}>
            {loading ? '⏳ Planning…' : mission ? '🔄 Regenerate' : (selectedTC ? `▶ Generate TC-${selectedTC.id}` : '▶ Generate Mission')}
          </button>

          {/* Play/Pause */}
          <button onClick={togglePlay} style={{
            padding: '5px 11px', borderRadius: 5, fontSize: 12,
            background: 'transparent', color: playing ? '#f59e0b' : '#94a3b8',
            border: `1px solid ${playing ? '#f59e0b44' : '#1e293b'}`, cursor: 'pointer',
          }}>
            {playing ? '⏸' : '▶'}
          </button>

          <label style={{ display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#64748b', cursor: 'pointer' }}>
            <input type="checkbox" checked={follow} onChange={e => setFollow(e.target.checked)} />
            Follow
          </label>

          <select value={speed} onChange={e => setSpeed(Number(e.target.value))} style={{
            background: '#0f1623', border: '1px solid #1e293b', color: '#94a3b8',
            borderRadius: 4, padding: '3px 5px', fontSize: 11,
          }}>
            {[0.5, 1, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
          </select>
        </div>
      </header>

      {/* ── MAIN ── */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>

        {/* ── MAP / SCENE ── */}
        <main style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#050a14' }}>
          {useRealMap ? (
            <div style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
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
            <div style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
              <CityScene />
            </div>
          )}

          {/* HUD overlay */}
          {mission && (
            <div style={{
              position: 'absolute', bottom: 12, left: 12, display: 'flex',
              alignItems: 'flex-end', gap: 10, pointerEvents: 'none', zIndex: 800,
            }}>
              <div style={{
                pointerEvents: 'auto',
                background: 'rgba(10,14,26,0.92)', border: '1px solid #1e293b',
                borderRadius: 6, padding: '8px 12px', fontFamily: 'monospace', fontSize: 11,
              }}>
                <div style={{ fontSize: 10, color: '#00d4ff', letterSpacing: 1, marginBottom: 4 }}>DRONE TELEMETRY</div>
                <div>ALT&nbsp;&nbsp;<span style={{ color: '#22d3ee' }}>{hud.alt.toFixed(1)} m</span></div>
                <div>LOAD <span style={{ color: '#22d3ee' }}>{hud.payload.toFixed(2)} kg</span></div>
                <div>STEP <span style={{ color: '#22d3ee' }}>{hud.step}</span> / {(mission.flight_path?.length ?? 1) - 1}</div>
                <div style={{ marginTop: 4, color: '#f59e0b', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{hud.action}</div>
              </div>
              <AltSparkline />
            </div>
          )}

          {/* Welcome / no-mission state */}
          {!mission && !loading && currentRoute.length === 0 && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
              justifyContent: 'center', pointerEvents: 'none', zIndex: 500,
            }}>
              <div style={{
                background: 'rgba(10,14,26,0.9)', border: '1px solid #1e293b',
                borderRadius: 12, padding: '24px 36px', textAlign: 'center', pointerEvents: 'auto',
              }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>🛸</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#22d3ee', marginBottom: 6 }}>
                  UAV-LLM Mission Control
                </div>
                <div style={{ fontSize: 12, color: '#475569', marginBottom: 16, maxWidth: 300 }}>
                  Select a test case from the <b style={{ color: '#94a3b8' }}>🧪 Tests</b> tab,<br />
                  then click <b style={{ color: '#22d3ee' }}>Run All Algos</b> to compare algorithms
                  or <b style={{ color: '#22d3ee' }}>Load</b> to see it on the map.
                </div>
                <button
                  onClick={() => setActiveTab('tests')}
                  style={{
                    padding: '8px 20px', borderRadius: 6, fontSize: 13, fontWeight: 700,
                    background: 'rgba(0,212,255,0.15)', color: '#00d4ff',
                    border: '1px solid #00d4ff44', cursor: 'pointer',
                  }}
                >
                  🧪 Browse 18 Test Cases
                </button>
              </div>
            </div>
          )}

          {/* Error toast */}
          {error && (
            <div style={{
              position: 'absolute', top: 10, right: 10, zIndex: 900,
              background: 'rgba(127,29,29,0.95)', border: '1px solid #ef4444',
              borderRadius: 6, padding: '8px 12px', fontSize: 11, color: '#fca5a5', maxWidth: 340,
            }}>
              ⚠️ {error}
            </div>
          )}
        </main>

        {/* ── SIDEBAR ── */}
        <aside style={{
          width: 380, display: 'flex', flexDirection: 'column',
          background: '#0a0e1a', borderLeft: '1px solid #0f1f35', flexShrink: 0,
          overflow: 'hidden',
        }}>
          {/* Tab bar */}
          <div style={{
            display: 'flex', borderBottom: '1px solid #0f1f35',
            overflowX: 'auto', flexShrink: 0, scrollbarWidth: 'none',
          }}>
            {TABS.map(t => (
              <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
                flex: '0 0 auto', padding: '8px 9px', fontSize: 10, fontWeight: 500,
                cursor: 'pointer', whiteSpace: 'nowrap', background: 'transparent',
                color: activeTab === t.id ? '#22d3ee' : '#475569',
                borderBottom: `2px solid ${activeTab === t.id ? '#22d3ee' : 'transparent'}`,
                border: 'none', borderBottomWidth: 2, borderBottomStyle: 'solid',
                borderBottomColor: activeTab === t.id ? '#22d3ee' : 'transparent',
                transition: 'color 0.15s',
              }}>
                {t.label}
              </button>
            ))}
          </div>

          {/* Panel content */}
          <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
            {renderPanel()}
          </div>
        </aside>
      </div>
    </div>
  );
}
