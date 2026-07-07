import { useMemo } from 'react'
import * as THREE from 'three'

// Glowing tube through the rate-limited 3D altitude profile. The vertical
// channel (y) comes straight from the corridor-clearance planner, so the tube
// visibly rises over tall buildings.
export function FlightPath({ curve }: { curve: THREE.CatmullRomCurve3 | null }) {
  const geom = useMemo(() => {
    if (!curve) return null
    const segs = Math.max(64, curve.points.length * 8)
    return new THREE.TubeGeometry(curve, segs, 0.5, 8, false)
  }, [curve])

  if (!geom) return null
  return (
    <mesh geometry={geom}>
      <meshStandardMaterial
        color="#22d3ee"
        emissive="#22d3ee"
        emissiveIntensity={0.7}
        transparent
        opacity={0.55}
      />
    </mesh>
  )
}
