import { OrbitControls } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { MissionPayload, Zone } from '../api/types'
import { useMission } from '../store/missionStore'
import { Buildings } from './Buildings'
import { makeTransform, type WorldTransform } from './coords'
import { Drone } from './Drone'
import { FlightPath } from './FlightPath'
import { NodeMarkers } from './NodeMarkers'

function Zones({ zones, world, color, opacity }: { zones: Zone[]; world: WorldTransform; color: string; opacity: number }) {
  return (
    <group>
      {zones.map((z, i) => {
        const [x, zz] = world.toScene(z.x, z.y)
        const r = z.r * world.hscale
        return (
          <group key={i} position={[x, 0, zz]}>
            <mesh position={[0, 0.1, 0]} rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[r * 0.94, r, 48]} />
              <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
            </mesh>
            <mesh position={[0, 6, 0]}>
              <cylinderGeometry args={[r, r, 12, 40, 1, true]} />
              <meshBasicMaterial color={color} transparent opacity={opacity} side={THREE.DoubleSide} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

function FollowRig({ posRef }: { posRef: React.MutableRefObject<THREE.Vector3> }) {
  const follow = useMission((s) => s.followDrone)
  const { camera } = useThree()
  const controls = useThree((s) => s.controls) as unknown as { target: THREE.Vector3; update: () => void } | null
  useFrame(() => {
    if (!follow || !controls) return
    controls.target.lerp(posRef.current, 0.1)
    const want = posRef.current.clone().add(new THREE.Vector3(26, 20, 26))
    camera.position.lerp(want, 0.06)
    controls.update()
  })
  return null
}

function World({ mission }: { mission: MissionPayload }) {
  const buildings = useMission((s) => s.buildings)
  const activeAlt = useMission((s) => s.activeAlt)
  const activeFlight = useMission((s) => s.activeFlight)
  const extraZones = useMission((s) => s.extraZones)
  const posRef = useRef(new THREE.Vector3())

  const world = useMemo(() => makeTransform(mission.city), [mission])

  const curve = useMemo(() => {
    const pts: THREE.Vector3[] =
      activeAlt.length > 1
        ? activeAlt.map((p) => {
            const [x, z] = world.toScene(p.x, p.y)
            return new THREE.Vector3(x, world.alt(p.z), z)
          })
        : activeFlight.map((s) => {
            const [x, z] = world.toScene(s.x, s.y)
            return new THREE.Vector3(x, world.alt(s.alt), z)
          })
    if (pts.length < 2) return null
    return new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.5)
  }, [activeAlt, activeFlight, world])

  const gzones = [...mission.gzones, ...extraZones]
  const half = world.target / 2 + 30

  return (
    <>
      <ambientLight intensity={0.5} />
      <hemisphereLight args={['#334155', '#0b0f1a', 0.6]} />
      <directionalLight
        position={[80, 140, 60]}
        intensity={1.4}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-half}
        shadow-camera-right={half}
        shadow-camera-top={half}
        shadow-camera-bottom={-half}
      />
      {/* ground */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]} receiveShadow>
        <planeGeometry args={[half * 2.4, half * 2.4]} />
        <meshStandardMaterial color="#0a0e17" roughness={1} />
      </mesh>
      <gridHelper args={[half * 2.4, 48, '#1e293b', '#141c2b']} position={[0, 0, 0]} />

      <Buildings buildings={buildings} mission={mission} world={world} />
      <NodeMarkers mission={mission} world={world} />
      <Zones zones={gzones} world={world} color="#ef4444" opacity={0.14} />
      <Zones zones={mission.nzones} world={world} color="#f59e0b" opacity={0.08} />
      <FlightPath curve={curve} />
      <Drone curve={curve} steps={activeFlight} posRef={posRef} />
      <FollowRig posRef={posRef} />
    </>
  )
}

export function CityScene() {
  const mission = useMission((s) => s.mission)
  const half = mission ? makeTransform(mission.city).target : 120
  return (
    <Canvas shadows camera={{ position: [half * 0.9, half * 0.8, half * 0.9], fov: 45, near: 0.1, far: 5000 }}>
      <color attach="background" args={['#05070d']} />
      <fog attach="fog" args={['#05070d', half * 2, half * 4]} />
      {mission && <World mission={mission} />}
      <OrbitControls makeDefault enableDamping dampingFactor={0.08} maxPolarAngle={Math.PI / 2.05} />
    </Canvas>
  )
}
