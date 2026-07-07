import { describe, expect, it } from 'vitest'
import type { CityNode } from '../api/types'
import { llToXY, makeTransform } from './coords'

function node(idx: number, x: number, y: number): CityNode {
  return {
    idx, lat: 0, lon: 0, x, y, bh: 10, label: `n${idx}`, category: 'test',
    description: '', depot: idx === 0, pickups: [], drops: [],
  }
}

describe('projection', () => {
  it('maps the origin to (0,0)', () => {
    const [x, y] = llToXY(15.46, 75.01, 15.46, 75.01)
    expect(Math.hypot(x, y)).toBeLessThan(1e-6)
  })

  it('east/north displacement has the right sign', () => {
    const [x, y] = llToXY(15.47, 75.02, 15.46, 75.01)
    expect(x).toBeGreaterThan(0) // east
    expect(y).toBeGreaterThan(0) // north
  })
})

describe('world transform', () => {
  const city = [node(0, 0, 0), node(1, 1000, 0), node(2, 0, 1000)]
  const world = makeTransform(city)

  it('fits the horizontal span to the target size', () => {
    const [ax] = world.toScene(0, 0)
    const [bx] = world.toScene(1000, 0)
    expect(Math.abs(bx - ax)).toBeCloseTo(world.hscale * 1000, 5)
  })

  it('exaggerates altitude vertically and clamps to >= 0', () => {
    expect(world.alt(100)).toBeGreaterThan(0)
    expect(world.alt(-5)).toBe(0)
    expect(world.vscale).toBeGreaterThan(world.hscale) // vertical exaggeration
  })
})
