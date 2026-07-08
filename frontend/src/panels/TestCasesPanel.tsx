import { useState, useEffect } from 'react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface PkgReq {
  pickup_name: string;
  delivery_name: string;
  kappa: string;
  weight: number;
  description: string;
}

interface TestCase {
  id: number;
  title: string;
  difficulty: 'easy' | 'medium' | 'hard' | 'expert';
  description: string;
  loc_indices: number[];
  pkg_requests: PkgReq[];
  nl_instruction: string;
  seed: number;
  n_gfz: number;
  incompat_density: number;
  deadline_tight: number;
  hazard_mix: number;
  cap_ratio: number;
}

const DIFF_COLOR: Record<string, string> = {
  easy: '#22c55e',
  medium: '#f59e0b',
  hard: '#ef4444',
  expert: '#a855f7',
};

const DIFF_BG: Record<string, string> = {
  easy: 'rgba(34,197,94,0.15)',
  medium: 'rgba(245,158,11,0.15)',
  hard: 'rgba(239,68,68,0.15)',
  expert: 'rgba(168,85,247,0.15)',
};

const KAPPA_COLOR: Record<string, string> = {
  PHARMA: '#60a5fa', FOOD: '#34d399', ELECTRONICS: '#fbbf24',
  FLAMMABLE: '#f97316', OXIDIZER: '#c084fc', CRYOGENIC: '#67e8f9',
  GENERAL: '#9ca3af',
};

interface Props {
  onLoadTestCase: (tc: TestCase) => void;
  onRunTestCase: (tc: TestCase) => void;
  selectedId: number | null;
  runningId: number | null;
}

export default function TestCasesPanel({ onLoadTestCase, onRunTestCase, selectedId, runningId }: Props) {
  const [cases, setCases] = useState<TestCase[]>([]);
  const [filter, setFilter] = useState<string>('all');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/api/test-cases`)
      .then(r => r.json())
      .then(d => { setCases(d.test_cases ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filtered = cases.filter(tc => {
    const matchDiff = filter === 'all' || tc.difficulty === filter;
    const matchSearch = tc.title.toLowerCase().includes(search.toLowerCase()) ||
      tc.description.toLowerCase().includes(search.toLowerCase());
    return matchDiff && matchSearch;
  });

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 8,
      height: '100%', overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{ padding: '10px 12px 0', flexShrink: 0 }}>
        <div style={{ fontSize: 11, color: '#64748b', letterSpacing: 1, marginBottom: 6 }}>
          TEST CASES ({cases.length})
        </div>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search test cases..."
          style={{
            width: '100%', background: '#1e293b', border: '1px solid #334155',
            borderRadius: 6, padding: '5px 8px', color: '#e2e8f0', fontSize: 11,
            outline: 'none', boxSizing: 'border-box',
          }}
        />
        {/* Difficulty filter */}
        <div style={{ display: 'flex', gap: 4, marginTop: 6, flexWrap: 'wrap' }}>
          {['all', 'easy', 'medium', 'hard', 'expert'].map(d => (
            <button
              key={d}
              onClick={() => setFilter(d)}
              style={{
                padding: '2px 8px', borderRadius: 4, fontSize: 10,
                border: `1px solid ${d === 'all' ? '#475569' : DIFF_COLOR[d] ?? '#475569'}`,
                background: filter === d ? (DIFF_BG[d] ?? 'rgba(71,85,105,0.3)') : 'transparent',
                color: d === 'all' ? '#94a3b8' : DIFF_COLOR[d] ?? '#94a3b8',
                cursor: 'pointer',
              }}
            >
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Cards */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 8px 8px' }}>
        {loading && (
          <div style={{ color: '#64748b', textAlign: 'center', marginTop: 20, fontSize: 12 }}>
            Loading test cases...
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div style={{ color: '#64748b', textAlign: 'center', marginTop: 20, fontSize: 12 }}>
            No test cases match.
          </div>
        )}
        {filtered.map(tc => {
          const isSelected = tc.id === selectedId;
          const isRunning = tc.id === runningId;
          return (
            <div
              key={tc.id}
              onClick={() => onLoadTestCase(tc)}
              style={{
                background: isSelected ? 'rgba(0,212,255,0.08)' : '#0f1623',
                border: `1px solid ${isSelected ? '#00d4ff' : '#1e293b'}`,
                borderRadius: 8, padding: '10px 10px 8px',
                marginBottom: 6, cursor: 'pointer',
                transition: 'all 0.15s',
              }}
            >
              {/* Title row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                <span style={{
                  fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
                  color: DIFF_COLOR[tc.difficulty] ?? '#9ca3af',
                  background: DIFF_BG[tc.difficulty] ?? 'transparent',
                  border: `1px solid ${DIFF_COLOR[tc.difficulty] ?? '#475569'}`,
                  textTransform: 'uppercase', letterSpacing: 0.5,
                }}>
                  {tc.difficulty}
                </span>
                <span style={{ fontSize: 11, color: '#e2e8f0', fontWeight: 600, flex: 1 }}>
                  {tc.title}
                </span>
              </div>

              {/* Description */}
              <div style={{ fontSize: 10, color: '#64748b', lineHeight: 1.4, marginBottom: 6 }}>
                {tc.description}
              </div>

              {/* Stats row */}
              <div style={{ display: 'flex', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                <Stat label="Nodes" value={tc.loc_indices.length} />
                <Stat label="Pkgs" value={tc.pkg_requests.length || 'auto'} />
                <Stat label="GFZ" value={tc.n_gfz} />
                <Stat label="Incompat" value={`${Math.round(tc.incompat_density * 100)}%`} />
                <Stat label="Deadline" value={`${Math.round(tc.deadline_tight * 100)}%`} />
              </div>

              {/* Package kappa pills */}
              {tc.pkg_requests.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
                  {tc.pkg_requests.map((p, i) => (
                    <span key={i} style={{
                      fontSize: 9, padding: '1px 5px', borderRadius: 3,
                      color: KAPPA_COLOR[p.kappa] ?? '#9ca3af',
                      background: `${KAPPA_COLOR[p.kappa] ?? '#9ca3af'}18`,
                      border: `1px solid ${KAPPA_COLOR[p.kappa] ?? '#475569'}44`,
                    }}>
                      {p.kappa} {p.weight}kg
                    </span>
                  ))}
                </div>
              )}

              {/* NL instruction preview */}
              <div style={{
                fontSize: 9.5, color: '#38bdf8', fontStyle: 'italic',
                background: 'rgba(56,189,248,0.06)', borderLeft: '2px solid #0ea5e9',
                padding: '3px 6px', borderRadius: 2, marginBottom: 8,
              }}>
                "{tc.nl_instruction}"
              </div>

              {/* Action buttons */}
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={e => { e.stopPropagation(); onLoadTestCase(tc); }}
                  style={{
                    flex: 1, padding: '4px 0', borderRadius: 5, fontSize: 10,
                    background: isSelected ? 'rgba(0,212,255,0.15)' : '#1e293b',
                    color: isSelected ? '#00d4ff' : '#94a3b8',
                    border: `1px solid ${isSelected ? '#00d4ff44' : '#334155'}`,
                    cursor: 'pointer',
                  }}
                >
                  Load
                </button>
                <button
                  onClick={e => { e.stopPropagation(); onRunTestCase(tc); }}
                  disabled={isRunning}
                  style={{
                    flex: 1, padding: '4px 0', borderRadius: 5, fontSize: 10,
                    background: isRunning ? 'rgba(0,212,255,0.3)' : 'rgba(0,212,255,0.15)',
                    color: '#00d4ff',
                    border: '1px solid #00d4ff44',
                    cursor: isRunning ? 'wait' : 'pointer',
                  }}
                >
                  {isRunning ? 'Running...' : 'Run All Algos'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <span style={{ fontSize: 9, color: '#475569' }}>{label}</span>
      <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600 }}>{value}</span>
    </div>
  );
}
