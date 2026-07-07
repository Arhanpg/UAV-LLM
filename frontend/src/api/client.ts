// Typed REST client. Requests are proxied to the FastAPI backend by Vite.
import type { GenConfig, MissionPayload } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}: ${await r.text()}`)
  return r.json() as Promise<T>
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`)
  if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  generate: (cfg: GenConfig) => post<MissionPayload>('/api/mission/generate', cfg),
  replan: (body: { session_id: string; disruption?: Record<string, unknown>; flown_steps?: number; instruction?: string }) =>
    post<Record<string, unknown>>('/api/mission/replan', body),
  instruction: (body: { session_id: string; instruction: string; phase: string }) =>
    post<Record<string, unknown>>('/api/llm/instruction', body),
  locations: () => get<{ locations: Record<string, unknown>[] }>('/api/locations'),
  buildings: () => get<{ type: string; features: unknown[] }>('/api/buildings'),
  compatGraph: () => get<{ classes: string[]; edges: { a: string; b: string; compatible: boolean }[]; incompatible_pairs: [string, string][] }>('/api/compat-graph'),
  health: () => get<Record<string, unknown>>('/health'),
}
