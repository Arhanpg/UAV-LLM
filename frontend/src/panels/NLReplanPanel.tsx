import { useState } from 'react';

const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface RouteDiff {
  added: string[];
  removed: string[];
  rerouted: boolean;
}

interface ReplanResult {
  instruction: string;
  route_diff: RouteDiff;
  new_route: string[];
  new_trajectory_gps: [number, number][];
  parse_result: {
    actions: { type: string; location: string | null; package_kappa: string; reason: string }[];
    summary: string;
    semantic_cost_impact: string;
    llm_confidence: number;
    source: string;
  };
}

interface Props {
  currentRoute: string[];
  onReplan: (result: ReplanResult) => void;
}

const EXAMPLES = [
  'Emergency no-fly zone near KIMS! Reroute via Dharwad Railway Station',
  'Add stop at Karnataka University before final delivery',
  'Go to KMF Hubli and pick up 2 L milk on the way',
  'Cancel stop at Big Bazaar Dharwad',
  'Emergency return to depot immediately',
  'Split delivery at Navodaya, hand off insulin to ground agent',
  'Avoid the Industrial Area and reroute through Siddharoodha Math',
];

export default function NLReplanPanel({ currentRoute, onReplan }: Props) {
  const [instruction, setInstruction] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ReplanResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API}/api/replan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction, current_route: currentRoute }),
      });
      const data: ReplanResult = await resp.json();
      setResult(data);
      onReplan(data);
    } catch (e) {
      setError(`Error: ${String(e)}`);
    } finally {
      setLoading(false);
    }
  };

  const ACTION_ICON: Record<string, string> = {
    ADD_STOP: '📍', DELIVER: '📦', PICKUP: '🔄', REROUTE: '↩️',
    REMOVE_STOP: '✖️', EMERGENCY_RETURN: '🚨', SPLIT_DELIVERY: '🤝', INFO: 'ℹ️',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%',
      overflow: 'hidden', padding: '8px 10px' }}>

      <div style={{ fontSize: 11, color: '#64748b', letterSpacing: 1, flexShrink: 0 }}>
        MID-FLIGHT NL INSTRUCTION
      </div>

      {/* Current route display */}
      {currentRoute.length > 0 && (
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: '#475569', marginBottom: 3 }}>Current route:</div>
          <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            {currentRoute.map((loc, i) => (
              <span key={i} style={{
                fontSize: 9, padding: '1px 5px', borderRadius: 3,
                background: i === 0 ? 'rgba(0,212,255,0.15)' : '#1e293b',
                color: i === 0 ? '#00d4ff' : '#94a3b8',
                border: `1px solid ${i === 0 ? '#00d4ff44' : '#334155'}`,
              }}>
                {i > 0 && <span style={{ color: '#334155', marginRight: 2 }}>→</span>}
                {loc.length > 18 ? loc.slice(0, 16) + '…' : loc}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Instruction input */}
      <div style={{ flexShrink: 0 }}>
        <textarea
          value={instruction}
          onChange={e => setInstruction(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Give a natural language instruction..."
          rows={2}
          style={{
            width: '100%', background: '#0f1623', border: '1px solid #334155',
            borderRadius: 6, padding: '6px 8px', color: '#e2e8f0', fontSize: 11,
            outline: 'none', resize: 'none', boxSizing: 'border-box',
            fontFamily: 'inherit',
          }}
        />
        <button
          onClick={send}
          disabled={loading}
          style={{
            width: '100%', marginTop: 4, padding: '6px 0', borderRadius: 6,
            background: loading ? 'rgba(0,212,255,0.2)' : 'rgba(0,212,255,0.15)',
            color: '#00d4ff', border: '1px solid #00d4ff44', fontSize: 11,
            cursor: loading ? 'wait' : 'pointer', fontWeight: 600,
          }}
        >
          {loading ? 'Parsing & Replanning...' : '⚡ Send Instruction'}
        </button>
      </div>

      {/* Quick examples */}
      <div style={{ flexShrink: 0 }}>
        <div style={{ fontSize: 9, color: '#475569', marginBottom: 3 }}>Quick examples:</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {EXAMPLES.slice(0, 3).map((ex, i) => (
            <button
              key={i}
              onClick={() => setInstruction(ex)}
              style={{
                textAlign: 'left', padding: '3px 6px', borderRadius: 4, fontSize: 9.5,
                background: 'transparent', border: '1px solid #1e293b',
                color: '#38bdf8', cursor: 'pointer',
                fontStyle: 'italic', whiteSpace: 'nowrap', overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              "{ex}"
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: '6px 8px', background: 'rgba(239,68,68,0.1)',
          border: '1px solid #ef444444', borderRadius: 6, fontSize: 10, color: '#f87171' }}>
          {error}
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {/* Route diff */}
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 10, color: '#475569', marginBottom: 4 }}>Route changes:</div>
            {result.route_diff.rerouted && (
              <div style={{ fontSize: 10, color: '#fbbf24', marginBottom: 3 }}>↩️ Route rerouted</div>
            )}
            {result.route_diff.added.map(loc => (
              <div key={loc} style={{ fontSize: 10, color: '#22c55e', marginBottom: 2 }}>
                ＋ Added: {loc}
              </div>
            ))}
            {result.route_diff.removed.map(loc => (
              <div key={loc} style={{ fontSize: 10, color: '#ef4444', marginBottom: 2 }}>
                ✖ Removed: {loc}
              </div>
            ))}
            {!result.route_diff.rerouted &&
              result.route_diff.added.length === 0 &&
              result.route_diff.removed.length === 0 && (
              <div style={{ fontSize: 10, color: '#64748b' }}>No route changes</div>
            )}
          </div>

          {/* Actions */}
          <div>
            <div style={{ fontSize: 10, color: '#475569', marginBottom: 4 }}>Parsed actions:</div>
            {result.parse_result.actions.map((act, i) => (
              <div key={i} style={{
                background: '#0f1623', border: '1px solid #1e293b',
                borderRadius: 6, padding: '5px 7px', marginBottom: 4,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ fontSize: 13 }}>{ACTION_ICON[act.type] ?? '▶'}</span>
                  <span style={{ fontSize: 11, color: '#00d4ff', fontWeight: 600 }}>{act.type}</span>
                  {act.location && (
                    <span style={{ fontSize: 10, color: '#94a3b8' }}>@ {act.location}</span>
                  )}
                  <span style={{
                    fontSize: 9, padding: '1px 4px', borderRadius: 2,
                    background: '#1e293b', color: '#64748b',
                  }}>
                    {act.package_kappa}
                  </span>
                </div>
                <div style={{ fontSize: 9, color: '#475569', marginTop: 2 }}>{act.reason}</div>
              </div>
            ))}
          </div>

          {/* Summary */}
          <div style={{
            background: 'rgba(56,189,248,0.06)', borderLeft: '2px solid #0ea5e9',
            padding: '4px 7px', borderRadius: 2, fontSize: 10, color: '#7dd3fc',
          }}>
            {result.parse_result.summary}
          </div>
        </div>
      )}
    </div>
  );
}
