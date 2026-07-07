// Project real ENU metres into the Three.js scene.
//
// Horizontal (x=east, y=north) is auto-fit to a target size; vertical (altitude,
// building height) uses an exaggerated scale so the corridor climb/descent is
// clearly visible — standard terrain exaggeration.
import type { CityNode } from '../api/types'

export const EARTH_R = 6371000

export function llToXY(lat: number, lon: number, olat: number, olon: number): [number, number] {
  const x = ((lon - olon) * Math.PI) / 180 * Math.cos((olat * Math.PI) / 180) * EARTH_R
  const y = ((lat - olat) * Math.PI) / 180 * EARTH_R
  return [x, y]
}

export interface WorldTransform {
  hscale: number
  vscale: number
  cx: number
  cy: number
  target: number
  toScene(x: number, y: number): [number, number] // metres -> [sceneX, sceneZ]
  alt(m: number): number // metres altitude -> scene Y
}

export function makeTransform(city: CityNode[]): WorldTransform {
  const xs = city.map((n) => n.x)
  const ys = city.map((n) => n.y)
  const minx = Math.min(...xs)
  const maxx = Math.max(...xs)
  const miny = Math.min(...ys)
  const maxy = Math.max(...ys)
  const span = Math.max(maxx - minx, maxy - miny, 1)
  const TARGET = 170
  const VEXAG = 5
  const hscale = TARGET / span
  const vscale = hscale * VEXAG
  const cx = (minx + maxx) / 2
  const cy = (miny + maxy) / 2
  return {
    hscale,
    vscale,
    cx,
    cy,
    target: TARGET,
    toScene(x, y) {
      // north (y) maps to -Z so "up the map" points away from the default camera
      return [(x - cx) * hscale, -(y - cy) * hscale]
    },
    alt(m) {
      return Math.max(0, m) * vscale
    },
  }
}

// Category → marker colour.
export const CATEGORY_COLOR: Record<string, string> = {
  hospital: '#f87171',
  mall: '#c084fc',
  education: '#60a5fa',
  transit: '#34d399',
  airbase: '#fbbf24',
  park: '#4ade80',
  industrial: '#94a3b8',
  warehouse: '#a3a3a3',
  commercial: '#f472b6',
  govt: '#22d3ee',
  religious: '#e879f9',
}

export const KAPPA_COLOR: Record<string, string> = {
  PHARMA: '#f43f5e',
  FOOD: '#f59e0b',
  ELECTRONICS: '#3b82f6',
  FLAMMABLE: '#ef4444',
  OXIDIZER: '#a855f7',
  CRYOGENIC: '#06b6d4',
  GENERAL: '#94a3b8',
}
