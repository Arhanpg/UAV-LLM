import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import * as THREE from 'three'
import { useMission } from '../store/missionStore'
import type { FlightStep } from '../api/types'

// Procedural quadcopter that flies along the flight curve, banking into turns,
// with spinning rotors. Progress is driven by the store's play/speed state; the
// live altitude/payload/step are pushed to the HUD.
export function Drone({
  curve,
  steps,
  posRef,
}: {
  curve: THREE.CatmullRomCurve3 | null
  steps: FlightStep[]
  posRef: React.MutableRefObject<THREE.Vector3>
}) {
  const group = useRef<THREE.Group>(null)
  const rotors = useRef<THREE.Mesh[]>([])
  const progress = useRef(0)
  const frame = useRef(0)
  const epochRef = useRef(0)
  const playing = useMission((s) => s.playing)
  const speed = useMission((s) => s.speed)
  const setHUD = useMission((s) => s.setDroneHUD)
  const flightEpoch = useMission((s) => s.flightEpoch)

  useFrame((_, delta) => {
    if (!curve) return
    // Reset to the depot on a NEW mission; on a replan the epoch is unchanged so
    // the drone keeps its progress and continues from where it was (Eq. 8a).
    if (epochRef.current !== flightEpoch) {
      epochRef.current = flightEpoch
      progress.current = 0
    }
    const DURATION = 20 // seconds for a full traversal at speed 1
    if (playing) {
      progress.current = Math.min(1, progress.current + (delta * speed) / DURATION)
    }
    const t = progress.current
    const p = curve.getPointAt(t)
    const tan = curve.getTangentAt(t)
    if (group.current) {
      group.current.position.copy(p)
      const look = p.clone().add(tan)
      group.current.lookAt(look)
      // subtle bank into the turn
      group.current.rotation.z = -tan.x * 0.35
    }
    posRef.current.copy(p)
    for (const r of rotors.current) if (r) r.rotation.y += delta * 40 * (playing ? 1 : 0.15)

    // Throttled HUD update.
    frame.current++
    if (frame.current % 4 === 0 && steps.length) {
      const idx = Math.min(steps.length - 1, Math.round(t * (steps.length - 1)))
      const st = steps[idx]
      setHUD({
        step: st.step,
        alt: st.alt,
        payload: st.payload,
        progress: t,
        action: st.algo_info?.action ?? '',
      })
    }
  })

  const arm = (rx: number, rz: number, key: number) => (
    <group key={key} rotation={[0, (Math.PI / 4) * (key % 2 === 0 ? 1 : -1), 0]}>
      <mesh position={[rx, 0, rz]}>
        <boxGeometry args={[3.2, 0.25, 0.25]} />
        <meshStandardMaterial color="#0f172a" metalness={0.6} roughness={0.4} />
      </mesh>
      <mesh
        ref={(m) => m && (rotors.current[key] = m)}
        position={[rx > 0 ? 1.7 : -1.7, 0.25, rz]}
      >
        <cylinderGeometry args={[1.1, 1.1, 0.08, 20]} />
        <meshStandardMaterial color="#22d3ee" emissive="#0891b2" emissiveIntensity={0.5} transparent opacity={0.55} />
      </mesh>
    </group>
  )

  return (
    <group ref={group}>
      {/* body */}
      <mesh castShadow>
        <boxGeometry args={[1.6, 0.7, 1.6]} />
        <meshStandardMaterial color="#e2e8f0" metalness={0.5} roughness={0.35} />
      </mesh>
      <mesh position={[0, 0.5, 0]}>
        <sphereGeometry args={[0.5, 16, 16]} />
        <meshStandardMaterial color="#22d3ee" emissive="#22d3ee" emissiveIntensity={0.8} />
      </mesh>
      {[
        [1.4, 1.4],
        [1.4, -1.4],
        [-1.4, 1.4],
        [-1.4, -1.4],
      ].map(([a, b], i) => arm(a, b, i))}
      <pointLight color="#22d3ee" intensity={8} distance={30} />
    </group>
  )
}
