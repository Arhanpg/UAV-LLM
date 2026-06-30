/** Phase 0 placeholder — 3D scene and panels land in Phases 5–6. */
export default function App() {
  return (
    <div className="min-h-screen bg-mission-bg p-6">
      <header className="mb-6 border-b border-slate-700 pb-4">
        <h1 className="text-xl font-bold text-cyan-400">UAV-LLM Mission Control</h1>
        <p className="text-sm text-slate-400">
          Dharwad–Hubli · Backend modularized · React frontend scaffold (Phase 0)
        </p>
      </header>
      <main className="rounded-lg border border-slate-700 bg-mission-panel p-4 text-sm text-slate-300">
        <p>
          Legacy UI remains at <code className="mono text-cyan-300">index.html</code> via{' '}
          <code className="mono">python app.py</code>. This Vite app will host the Three.js scene in Phase 5.
        </p>
      </main>
    </div>
  )
}
