// Shared API types mirroring the FastAPI response payloads.

export interface CityNode {
  idx: number
  lat: number
  lon: number
  x: number
  y: number
  bh: number
  label: string
  category: string
  description: string
  depot: boolean
  pickups: PackageRef[]
  drops: PackageRef[]
}

export interface PackageRef {
  req: number
  kappa: string
  w: number
  label: string
}

export interface Package {
  idx: number
  pickup: number
  delivery: number
  weight: number
  kappa: string
  deadline: number
  priority: number
  temp: boolean
  desc: string
}

export interface Zone {
  lat: number
  lon: number
  x: number
  y: number
  r: number
  kind: string
  label: string
}

export interface FlightStep {
  step: number
  node: number
  x: number
  y: number
  lat: number
  lon: number
  alt: number
  role: string
  req: number
  label: string
  dist: number
  payload: number
  time: number
  algo_info: { action: string; payload: number; altitude: number }
}

export interface AltPoint {
  x: number
  y: number
  z: number
  seg: number
}

export interface AlgoResult {
  route: number[]
  metrics: Record<string, number | boolean>
  log: Record<string, unknown>[]
  verif_log: VerifEntry[]
}

export interface VerifEntry {
  req: number
  true_kappa: string
  synth_kappa: string
  accepted?: string
  verified: boolean
  recovered: boolean
  source?: string
  reasons?: string[]
  psi?: Record<string, unknown>
  prompt?: string
  response?: string
}

export interface MissionPayload {
  session_id: string
  origin: { lat: number; lon: number; label: string }
  llm_mode: string
  model: string
  city: CityNode[]
  packages: Package[]
  gzones: Zone[]
  nzones: Zone[]
  W_cap: number
  traj_xy: [number, number][]
  traj_gps: [number, number][]
  results: Record<string, AlgoResult>
  flight_path: FlightStep[]
  alt_profile: AltPoint[]
  verifier: { route: Record<string, unknown>; discrepancy: string | null }
  incompat_pairs: [string, string][]
  classes: string[]
  all_locations: { idx: number; name: string; lat: number; lon: number; bh: number; cat: string; desc: string }[]
}

export interface TelemetryEvent {
  type: string
  t: number
  [key: string]: unknown
}

export interface GenConfig {
  loc_indices?: number[]
  pkg_requests?: Record<string, unknown>[]
  seed?: number
  incompat_density?: number
  n_gfz?: number
  deadline_tight?: number
  hazard_mix?: number
  cap_ratio?: number
  wind_dir?: number
  llm_error?: number
}
