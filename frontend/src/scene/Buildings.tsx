import { useMemo } from 'react'
import * as THREE from 'three'
import type { MissionPayload } from '../api/types'
import { llToXY, type WorldTransform } from './coords'

interface Feature {
  geometry: { type: string; coordinates: number[][][] }
  properties: { height?: number; name?: string }
}

// Extrude committed OSM building footprints to their real heights. Footprints
// are projected into the same local metric frame as the mission, then scaled.
export function Buildings({
  buildings,
  mission,
  world,
}: {
  buildings: { features: unknown[] } | null
  mission: MissionPayload
  world: WorldTransform
}) {
  const geom = useMemo(() => {
    if (!buildings) return null
    const olat = mission.origin.lat
    const olon = mission.origin.lon
    const merged: THREE.BufferGeometry[] = []
    for (const raw of buildings.features as Feature[]) {
      if (raw.geometry?.type !== 'Polygon') continue
      const ring = raw.geometry.coordinates[0]
      const shape = new THREE.Shape()
      ring.forEach(([lon, lat], i) => {
        const [mx, my] = llToXY(lat, lon, olat, olon)
        const [sx, sz] = world.toScene(mx, my)
        // Shape is authored in XY then rotated -90° about X (Y→Z, Z→height);
        // authoring with -sz keeps the footprint aligned with node markers.
        if (i === 0) shape.moveTo(sx, -sz)
        else shape.lineTo(sx, -sz)
      })
      const h = world.alt(raw.properties?.height ?? 9)
      const g = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false })
      g.rotateX(-Math.PI / 2) // lay the footprint on the ground (XZ) with height +Y
      merged.push(g)
    }
    return merged
  }, [buildings, mission, world])

  if (!geom) return null
  return (
    <group>
      {geom.map((g, i) => (
        <mesh key={i} geometry={g} castShadow receiveShadow>
          <meshStandardMaterial color="#1b2436" roughness={0.85} metalness={0.1} />
        </mesh>
      ))}
    </group>
  )
}
