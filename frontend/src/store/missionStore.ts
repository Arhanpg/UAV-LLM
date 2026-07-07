import { create } from 'zustand'
import { api } from '../api/client'
import type { AltPoint, FlightStep, GenConfig, MissionPayload, TelemetryEvent, Zone } from '../api/types'

export interface BuilderPkg {
  id: number
  pickupNode: number | null
  deliveryNode: number | null
  kappa: string
  weight: number
  deadline: number | null
  desc: string
}

export interface NLMsg {
  role: 'user' | 'system'
  text: string
  source?: string
}

// A compact, geographically-tight Dharwad cluster makes the 3D scene legible.
const DEFAULT_LOCS = [0, 1, 2, 3, 4, 7, 8, 11, 15, 16]

interface MissionState {
  mission: MissionPayload | null
  buildings: { type: string; features: unknown[] } | null
  events: TelemetryEvent[]
  selectedAlgo: string
  playing: boolean
  speed: number
  followDrone: boolean
  selectedNode: number | null
  builder: BuilderPkg[]
  nl: NLMsg[]
  loading: boolean
  error: string | null
  activeFlight: FlightStep[]
  activeAlt: AltPoint[]
  extraZones: Zone[]
  droneHUD: { step: number; alt: number; payload: number; progress: number; action: string }

  setSelectedAlgo: (a: string) => void
  togglePlay: () => void
  setSpeed: (s: number) => void
  setFollow: (f: boolean) => void
  selectNode: (n: number | null) => void
  addBuilder: (p: Omit<BuilderPkg, 'id'>) => void
  removeBuilder: (id: number) => void
  clearBuilder: () => void
  pushEvent: (e: TelemetryEvent) => void
  clearEvents: () => void
  setDroneHUD: (h: MissionState['droneHUD']) => void
  loadBuildings: () => Promise<void>
  generate: (cfg?: GenConfig) => Promise<void>
  replan: (disruption: Record<string, unknown>, flownSteps: number, instruction?: string) => Promise<void>
  sendInstruction: (text: string, phase: string) => Promise<void>
}

export const useMission = create<MissionState>((set, get) => ({
  mission: null,
  buildings: null,
  events: [],
  selectedAlgo: 'HNP',
  playing: false,
  speed: 1,
  followDrone: false,
  selectedNode: null,
  builder: [],
  nl: [],
  loading: false,
  error: null,
  activeFlight: [],
  activeAlt: [],
  extraZones: [],
  droneHUD: { step: 0, alt: 0, payload: 0, progress: 0, action: 'IDLE' },

  setSelectedAlgo: (a) => set({ selectedAlgo: a }),
  togglePlay: () => set((s) => ({ playing: !s.playing })),
  setSpeed: (s) => set({ speed: s }),
  setFollow: (f) => set({ followDrone: f }),
  selectNode: (n) => set({ selectedNode: n }),
  addBuilder: (p) => set((s) => ({ builder: [...s.builder, { ...p, id: Date.now() + s.builder.length }] })),
  removeBuilder: (id) => set((s) => ({ builder: s.builder.filter((b) => b.id !== id) })),
  clearBuilder: () => set({ builder: [] }),
  pushEvent: (e) => set((s) => ({ events: [...s.events.slice(-600), e] })),
  clearEvents: () => set({ events: [] }),
  setDroneHUD: (h) => set({ droneHUD: h }),

  loadBuildings: async () => {
    try {
      set({ buildings: await api.buildings() })
    } catch (e) {
      set({ error: String(e) })
    }
  },

  generate: async (cfg) => {
    set({ loading: true, error: null, events: [], extraZones: [] })
    try {
      const builder = get().builder
      const mission = get().mission
      const pkg_requests =
        builder.length && mission
          ? builder
              .filter((b) => b.pickupNode !== null && b.deliveryNode !== null)
              .map((b) => ({
                pickup_name: mission.city.find((c) => c.idx === b.pickupNode)?.label ?? '',
                delivery_name: mission.city.find((c) => c.idx === b.deliveryNode)?.label ?? '',
                kappa: b.kappa,
                weight: b.weight,
                description: b.desc,
              }))
          : []
      const payload = await api.generate({ loc_indices: DEFAULT_LOCS, seed: 42, ...cfg, pkg_requests })
      set({
        mission: payload,
        activeFlight: payload.flight_path,
        activeAlt: payload.alt_profile,
        selectedAlgo: 'HNP',
        playing: true,
        loading: false,
        droneHUD: { step: 0, alt: 0, payload: 0, progress: 0, action: 'TAKEOFF' },
      })
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  replan: async (disruption, flownSteps, instruction) => {
    const m = get().mission
    if (!m) return
    set({ loading: true })
    try {
      const res = (await api.replan({ session_id: m.session_id, disruption, flown_steps: flownSteps, instruction })) as {
        new_route: number[]
        flight_path: FlightStep[]
        alt_profile: AltPoint[]
        new_gzones: Zone[]
      }
      set((s) => ({
        activeFlight: res.flight_path,
        activeAlt: res.alt_profile,
        extraZones: res.new_gzones ?? s.extraZones,
        playing: true,
        loading: false,
      }))
    } catch (e) {
      set({ error: String(e), loading: false })
    }
  },

  sendInstruction: async (text, phase) => {
    const m = get().mission
    set((s) => ({ nl: [...s.nl, { role: 'user', text }] }))
    try {
      const res = (await api.instruction({ session_id: m?.session_id ?? 'default', instruction: text, phase })) as {
        result: { summary?: string; source?: string; actions?: { type: string; location?: string }[] }
      }
      const r = res.result
      const summary = r.summary || (r.actions ?? []).map((a) => `${a.type}${a.location ? ' @ ' + a.location : ''}`).join(', ')
      set((s) => ({ nl: [...s.nl, { role: 'system', text: summary || '(no actions)', source: r.source }] }))
    } catch (e) {
      set((s) => ({ nl: [...s.nl, { role: 'system', text: `Error: ${e}` }] }))
    }
  },
}))
