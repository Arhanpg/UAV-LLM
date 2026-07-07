import { Billboard, Text } from '@react-three/drei'
import { useMission } from '../store/missionStore'
import type { CityNode, MissionPayload } from '../api/types'
import { CATEGORY_COLOR, type WorldTransform } from './coords'

function role(n: CityNode): { color: string; tag: string } {
  if (n.depot) return { color: '#22d3ee', tag: 'DEPOT' }
  const src = n.pickups.length > 0
  const dst = n.drops.length > 0
  if (src && dst) return { color: '#e879f9', tag: 'SRC+DST' }
  if (src) return { color: '#34d399', tag: 'SOURCE' }
  if (dst) return { color: '#f59e0b', tag: 'DEST' }
  return { color: CATEGORY_COLOR[n.category] ?? '#64748b', tag: n.category }
}

export function NodeMarkers({ mission, world }: { mission: MissionPayload; world: WorldTransform }) {
  const selectNode = useMission((s) => s.selectNode)
  const selected = useMission((s) => s.selectedNode)

  return (
    <group>
      {mission.city.map((n) => {
        const [x, z] = world.toScene(n.x, n.y)
        const { color, tag } = role(n)
        const poleH = world.alt(Math.max(12, n.bh))
        const isSel = selected === n.idx
        return (
          <group key={n.idx} position={[x, 0, z]}>
            {/* pole */}
            <mesh position={[0, poleH / 2, 0]}>
              <cylinderGeometry args={[0.15, 0.15, poleH, 8]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.3} />
            </mesh>
            {/* clickable marker */}
            <mesh
              position={[0, poleH + 1.4, 0]}
              onClick={(e) => {
                e.stopPropagation()
                selectNode(n.idx)
              }}
              onPointerOver={(e) => (e.stopPropagation(), (document.body.style.cursor = 'pointer'))}
              onPointerOut={() => (document.body.style.cursor = 'auto')}
            >
              <sphereGeometry args={[isSel ? 2 : 1.4, 20, 20]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={isSel ? 0.9 : 0.45} />
            </mesh>
            <Billboard position={[0, poleH + 4.6, 0]}>
              <Text fontSize={2.2} color="#e6edf3" anchorX="center" anchorY="middle" outlineWidth={0.06} outlineColor="#000">
                {n.depot ? '🏠 ' : ''}
                {n.label}
              </Text>
              <Text position={[0, -2.4, 0]} fontSize={1.5} color={color} anchorX="center" anchorY="middle">
                {tag}
              </Text>
            </Billboard>
          </group>
        )
      })}
    </group>
  )
}
