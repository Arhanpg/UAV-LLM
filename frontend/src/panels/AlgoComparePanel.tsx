import { useEffect, useRef } from 'react';

const ALGO_COLORS: Record<string, string> = {
  'HNP': '#00d4ff', 'MPDD': '#ff6b6b', 'HNP-NoVerify': '#ffd93d',
  'HNP-NoCompat': '#6bcb77', 'HNP-NoRefine': '#4d96ff', 'NN-PDP': '#ff922b',
};

export interface AlgoResult {
  algo: string;
  color: string;
  semantic_cost: number;
  distance: number;
  runtime_ms: number;
  feasible: boolean;
  violations: number;
  energy: number;
  route: number[];
}

interface Props {
  results: AlgoResult[];
  loading: boolean;
}

export default function AlgoComparePanel({ results, loading }: Props) {
  const radarRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!radarRef.current || results.length === 0) return;
    const canvas = radarRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const W = canvas.width;
    const H = canvas.height;
    const cx = W / 2;
    const cy = H / 2;
    const R = Math.min(W, H) * 0.38;

    ctx.clearRect(0, 0, W, H);

    const AXES = ['Cost', 'Distance', 'Runtime', 'Energy', 'Violations'];
    const N = AXES.length;
    const angleStep = (2 * Math.PI) / N;

    // Normalize results to 0..1 (lower is better -> invert)
    const maxCost = Math.max(...results.map(r => r.semantic_cost), 1);
    const maxDist = Math.max(...results.map(r => r.distance), 1);
    const maxRT = Math.max(...results.map(r => r.runtime_ms), 1);
    const maxEn = Math.max(...results.map(r => r.energy), 1);
    const maxViol = Math.max(...results.map(r => r.violations), 1);

    const normalize = (r: AlgoResult) => [
      1 - r.semantic_cost / maxCost,
      1 - r.distance / maxDist,
      1 - r.runtime_ms / maxRT,
      1 - r.energy / maxEn,
      1 - r.violations / maxViol,
    ];

    // Draw grid rings
    for (let ring = 1; ring <= 5; ring++) {
      const ringR = (ring / 5) * R;
      ctx.beginPath();
      for (let i = 0; i < N; i++) {
        const angle = -Math.PI / 2 + i * angleStep;
        const x = cx + ringR * Math.cos(angle);
        const y = cy + ringR * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Draw axis lines and labels
    ctx.font = '10px monospace';
    ctx.fillStyle = '#64748b';
    ctx.textAlign = 'center';
    for (let i = 0; i < N; i++) {
      const angle = -Math.PI / 2 + i * angleStep;
      const x1 = cx;
      const y1 = cy;
      const x2 = cx + R * Math.cos(angle);
      const y2 = cy + R * Math.sin(angle);
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.strokeStyle = 'rgba(255,255,255,0.1)';
      ctx.stroke();
      // Labels
      const lx = cx + (R + 16) * Math.cos(angle);
      const ly = cy + (R + 16) * Math.sin(angle);
      ctx.fillText(AXES[i], lx, ly + 3);
    }

    // Draw each algorithm polygon
    results.forEach(r => {
      const vals = normalize(r);
      const color = ALGO_COLORS[r.algo] ?? '#888';
      ctx.beginPath();
      vals.forEach((v, i) => {
        const angle = -Math.PI / 2 + i * angleStep;
        const x = cx + v * R * Math.cos(angle);
        const y = cy + v * R * Math.sin(angle);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.fillStyle = color + '20';
      ctx.fill();
    });
  }, [results]);

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center',
        height: '100%', color: '#64748b', fontSize: 12 }}>
        <span style={{ marginRight: 8 }}>&#9654;</span> Running algorithms...
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', height: '100%', color: '#64748b', gap: 6 }}>
        <div style={{ fontSize: 24 }}>&#9654;</div>
        <div style={{ fontSize: 12 }}>Select a test case and click Run All Algos</div>
      </div>
    );
  }

  const best = results.reduce((a, b) => a.semantic_cost < b.semantic_cost ? a : b);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%',
      overflow: 'hidden', padding: '8px 10px' }}>

      {/* Radar chart */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <canvas ref={radarRef} width={220} height={200}
          style={{ borderRadius: 8, background: '#0a0e1a' }} />
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
        {results.map(r => (
          <div key={r.algo} style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2,
              background: ALGO_COLORS[r.algo] ?? '#888' }} />
            <span style={{ fontSize: 9, color: '#94a3b8' }}>{r.algo}</span>
          </div>
        ))}
      </div>

      {/* Best algo badge */}
      <div style={{
        background: 'rgba(0,212,255,0.08)', border: '1px solid #00d4ff44',
        borderRadius: 6, padding: '4px 8px', textAlign: 'center',
      }}>
        <span style={{ fontSize: 10, color: '#64748b' }}>Best: </span>
        <span style={{ fontSize: 11, color: '#00d4ff', fontWeight: 700 }}>{best.algo}</span>
        <span style={{ fontSize: 10, color: '#64748b' }}> — cost {best.semantic_cost.toFixed(0)}</span>
      </div>

      {/* Comparison table */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
          <thead>
            <tr>
              {['Algo', 'Cost', 'Dist', 'RT(ms)', 'Energy', 'OK'].map(h => (
                <th key={h} style={{
                  color: '#475569', padding: '3px 4px', textAlign: 'right',
                  borderBottom: '1px solid #1e293b', fontWeight: 500,
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...results].sort((a, b) => a.semantic_cost - b.semantic_cost).map(r => (
              <tr key={r.algo}
                style={{ background: r.algo === best.algo ? 'rgba(0,212,255,0.05)' : 'transparent' }}>
                <td style={{ color: ALGO_COLORS[r.algo] ?? '#9ca3af', padding: '3px 4px',
                  fontWeight: r.algo === best.algo ? 700 : 400 }}>
                  {r.algo === best.algo ? '★ ' : ''}{r.algo}
                </td>
                <td style={{ color: '#e2e8f0', textAlign: 'right', padding: '3px 4px' }}>
                  {r.semantic_cost.toFixed(0)}
                </td>
                <td style={{ color: '#94a3b8', textAlign: 'right', padding: '3px 4px' }}>
                  {r.distance.toFixed(0)}m
                </td>
                <td style={{ color: '#94a3b8', textAlign: 'right', padding: '3px 4px' }}>
                  {r.runtime_ms.toFixed(0)}
                </td>
                <td style={{ color: '#94a3b8', textAlign: 'right', padding: '3px 4px' }}>
                  {r.energy.toFixed(1)}
                </td>
                <td style={{ textAlign: 'right', padding: '3px 4px' }}>
                  <span style={{ color: r.feasible ? '#22c55e' : '#ef4444', fontSize: 12 }}>
                    {r.feasible ? '✓' : '✗'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
