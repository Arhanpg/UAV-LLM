import { useState } from 'react';

interface PkgReq {
  pickup_name: string;
  delivery_name: string;
  kappa: string;
  weight: number;
  description: string;
}

export interface TestCase {
  id: number;
  title: string;
  difficulty: 'easy' | 'medium' | 'hard' | 'expert';
  description: string;
  loc_indices: number[];
  pkg_requests: PkgReq[];
  nl_instruction: string;
  seed: number;
  n_gfz: number;
  incompat_density: number;
  deadline_tight: number;
  hazard_mix: number;
  cap_ratio: number;
}

// All 18 test cases hardcoded — zero API dependency, instant load
const ALL_TEST_CASES: TestCase[] = [
  {
    id: 1, title: 'Single Pharma Delivery', difficulty: 'easy',
    description: 'Simple point-to-point insulin delivery from SDM Hospital to KIMS. No hazards, no no-fly zones, tight deadline.',
    loc_indices: [0, 1], seed: 1, n_gfz: 0, incompat_density: 0, deadline_tight: 0.8, hazard_mix: 0, cap_ratio: 0.5,
    pkg_requests: [{ pickup_name: 'SDM Hospital', delivery_name: 'KIMS Hospital', kappa: 'PHARMA', weight: 1.2, description: 'Insulin vials, fragile, urgent' }],
    nl_instruction: 'Deliver insulin from SDM Hospital to KIMS urgently',
  },
  {
    id: 2, title: 'Milk Pickup from KMF', difficulty: 'easy',
    description: 'Fetch 2 L fresh milk from KMF Hubli and deliver to Urban Oasis Mall.',
    loc_indices: [28, 7, 5], seed: 2, n_gfz: 0, incompat_density: 0, deadline_tight: 0.4, hazard_mix: 0, cap_ratio: 0.3,
    pkg_requests: [{ pickup_name: 'KMF Hubli', delivery_name: 'Urban Oasis Mall', kappa: 'FOOD', weight: 2, description: 'Fresh milk 2L' }],
    nl_instruction: 'Go to KMF Hubli and pick up 2 L milk, then deliver to Urban Oasis Mall',
  },
  {
    id: 3, title: 'Electronics Drop', difficulty: 'easy',
    description: 'Deliver a laptop charger from BVB College to IIT Dharwad. Single stop.',
    loc_indices: [12, 13], seed: 3, n_gfz: 0, incompat_density: 0, deadline_tight: 0.3, hazard_mix: 0, cap_ratio: 0.2,
    pkg_requests: [{ pickup_name: 'BVB College of Engg', delivery_name: 'IIT Dharwad', kappa: 'ELECTRONICS', weight: 0.8, description: 'Laptop charger' }],
    nl_instruction: 'Pick up the laptop charger from BVB and drop at IIT Dharwad',
  },
  {
    id: 4, title: 'Stationery to College', difficulty: 'easy',
    description: 'Deliver 3 notebooks to Sana Shaheen PU College. Pure GENERAL cargo.',
    loc_indices: [14, 14], seed: 4, n_gfz: 0, incompat_density: 0, deadline_tight: 0.2, hazard_mix: 0, cap_ratio: 0.2,
    pkg_requests: [{ pickup_name: 'Karnatak College Dharwad', delivery_name: 'Sana Shaheen Independent PU College', kappa: 'GENERAL', weight: 0.9, description: '3 notebooks' }],
    nl_instruction: 'Go through Sana Shaheen Independent PU College and give them 3 notebooks',
  },
  {
    id: 5, title: 'Hospital Circuit', difficulty: 'easy',
    description: 'Multi-hospital supply run: SDM → Suretech → Navodaya → KIMS. Basic route with no restrictions.',
    loc_indices: [0, 2, 3, 1], seed: 5, n_gfz: 0, incompat_density: 0.1, deadline_tight: 0.5, hazard_mix: 0, cap_ratio: 0.6,
    pkg_requests: [
      { pickup_name: 'SDM Hospital', delivery_name: 'Suretech Hospital', kappa: 'PHARMA', weight: 1.0, description: 'Saline bags' },
      { pickup_name: 'Suretech Hospital', delivery_name: 'Navodaya Medical College', kappa: 'GENERAL', weight: 0.5, description: 'Medical files' },
    ],
    nl_instruction: 'Do a full hospital supply run across Dharwad-Hubli starting from SDM',
  },
  {
    id: 6, title: 'Market Run with NFZ', difficulty: 'medium',
    description: 'Pick up vegetables from Big Bazaar and deliver to Dharwad Station. One restricted zone near university.',
    loc_indices: [7, 16, 11], seed: 6, n_gfz: 1, incompat_density: 0.1, deadline_tight: 0.5, hazard_mix: 0.1, cap_ratio: 0.5,
    pkg_requests: [{ pickup_name: 'Big Bazaar Dharwad', delivery_name: 'Dharwad Railway Station', kappa: 'FOOD', weight: 3.0, description: 'Vegetable basket' }],
    nl_instruction: 'Pick up vegetables from Big Bazaar and rush to Dharwad Railway Station',
  },
  {
    id: 7, title: 'Dairy Multi-Drop', difficulty: 'medium',
    description: 'Distribute dairy products: KMF → Govt Hospital → KIMS. Two incompatible cargo types.',
    loc_indices: [28, 4, 1], seed: 7, n_gfz: 1, incompat_density: 0.2, deadline_tight: 0.6, hazard_mix: 0, cap_ratio: 0.7,
    pkg_requests: [
      { pickup_name: 'KMF Hubli', delivery_name: 'Govt District Hospital', kappa: 'FOOD', weight: 5.0, description: 'Milk crates' },
      { pickup_name: 'Nandini Dairy Hubli', delivery_name: 'KIMS Hospital', kappa: 'FOOD', weight: 2.0, description: 'Yoghurt packs' },
    ],
    nl_instruction: 'Distribute dairy from KMF and Nandini Dairy to Govt Hospital and KIMS',
  },
  {
    id: 8, title: 'Airport Pharma Run', difficulty: 'medium',
    description: 'Time-critical vaccine transport from Hubli Airport to three hospitals with a cold-chain requirement.',
    loc_indices: [17, 1, 2, 3], seed: 8, n_gfz: 1, incompat_density: 0.2, deadline_tight: 0.8, hazard_mix: 0.2, cap_ratio: 0.6,
    pkg_requests: [
      { pickup_name: 'Hubli Airport', delivery_name: 'KIMS Hospital', kappa: 'PHARMA', weight: 2.5, description: 'COVID vaccines, cold-chain' },
      { pickup_name: 'Hubli Airport', delivery_name: 'Navodaya Medical College', kappa: 'PHARMA', weight: 1.5, description: 'Flu shots' },
    ],
    nl_instruction: 'Urgent: transport vaccines from Hubli Airport to all hospitals immediately',
  },
  {
    id: 9, title: 'Electronics + Food Mix', difficulty: 'medium',
    description: 'Incompatible cargo: deliver router (ELECTRONICS) and packed lunch (FOOD) separately across Hubli.',
    loc_indices: [12, 5, 7], seed: 9, n_gfz: 1, incompat_density: 0.3, deadline_tight: 0.5, hazard_mix: 0.1, cap_ratio: 0.7,
    pkg_requests: [
      { pickup_name: 'BVB College of Engg', delivery_name: 'Urban Oasis Mall', kappa: 'ELECTRONICS', weight: 1.2, description: 'WiFi router' },
      { pickup_name: 'Big Bazaar Dharwad', delivery_name: 'Urban Oasis Mall', kappa: 'FOOD', weight: 2.0, description: 'Packed lunch' },
    ],
    nl_instruction: 'Separate electronics and food deliveries to Urban Oasis Mall',
  },
  {
    id: 10, title: 'City-Wide Supply Grid', difficulty: 'medium',
    description: '6-node mission across both Dharwad and Hubli with mixed cargo and 2 restricted zones.',
    loc_indices: [0, 1, 5, 7, 12, 28], seed: 10, n_gfz: 2, incompat_density: 0.25, deadline_tight: 0.55, hazard_mix: 0.15, cap_ratio: 0.75,
    pkg_requests: [
      { pickup_name: 'SDM Hospital', delivery_name: 'KIMS Hospital', kappa: 'PHARMA', weight: 1.0, description: 'Medicines' },
      { pickup_name: 'KMF Hubli', delivery_name: 'Urban Oasis Mall', kappa: 'FOOD', weight: 3.0, description: 'Dairy goods' },
      { pickup_name: 'BVB College of Engg', delivery_name: 'Big Bazaar Dharwad', kappa: 'ELECTRONICS', weight: 0.5, description: 'Printer cartridge' },
    ],
    nl_instruction: 'Run a full cross-city supply loop covering hospitals, malls and colleges',
  },
  {
    id: 11, title: 'Flammable Cargo Routing', difficulty: 'hard',
    description: 'Transport acetone (FLAMMABLE) from Industrial Area to warehouse. Must avoid populated zones.',
    loc_indices: [25, 26, 28], seed: 11, n_gfz: 2, incompat_density: 0.3, deadline_tight: 0.6, hazard_mix: 0.6, cap_ratio: 0.4,
    pkg_requests: [{ pickup_name: 'Dharwad Industrial Area', delivery_name: 'Almatti Road Warehouse', kappa: 'FLAMMABLE', weight: 4.0, description: 'Acetone drum' }],
    nl_instruction: 'Route flammable cargo safely from industrial area to the warehouse',
  },
  {
    id: 12, title: 'Cryogenic Medical Emergency', difficulty: 'hard',
    description: 'Liquid nitrogen cryovials from KIMS to SDM under 90-second deadline. 3 NFZs, heavy restrictions.',
    loc_indices: [1, 0, 2], seed: 12, n_gfz: 3, incompat_density: 0.4, deadline_tight: 0.9, hazard_mix: 0.5, cap_ratio: 0.5,
    pkg_requests: [{ pickup_name: 'KIMS Hospital', delivery_name: 'SDM Hospital', kappa: 'CRYOGENIC', weight: 3.0, description: 'LN2 cryovials' }],
    nl_instruction: 'Emergency: ship cryogenic samples from KIMS to SDM before they degrade',
  },
  {
    id: 13, title: 'Oxidizer Transport', difficulty: 'hard',
    description: 'Hydrogen peroxide (OXIDIZER) pickup from Industrial Area with incompatibility constraints across 5 nodes.',
    loc_indices: [25, 0, 3, 26, 28], seed: 13, n_gfz: 2, incompat_density: 0.45, deadline_tight: 0.7, hazard_mix: 0.7, cap_ratio: 0.5,
    pkg_requests: [
      { pickup_name: 'Dharwad Industrial Area', delivery_name: 'Navodaya Medical College', kappa: 'OXIDIZER', weight: 2.5, description: 'H2O2 30% solution' },
      { pickup_name: 'Almatti Road Warehouse', delivery_name: 'SDM Hospital', kappa: 'PHARMA', weight: 1.0, description: 'Wound dressings' },
    ],
    nl_instruction: 'Transport oxidizer safely to medical college, avoid pharma incompatibility',
  },
  {
    id: 14, title: 'Night Shift Logistics', difficulty: 'hard',
    description: '8-node night delivery with 3 NFZs, tight deadlines, and multiple incompatible packages.',
    loc_indices: [0, 1, 2, 3, 4, 11, 12, 16], seed: 14, n_gfz: 3, incompat_density: 0.4, deadline_tight: 0.75, hazard_mix: 0.3, cap_ratio: 0.8,
    pkg_requests: [
      { pickup_name: 'SDM Hospital', delivery_name: 'KIMS Hospital', kappa: 'PHARMA', weight: 2.0, description: 'Night meds' },
      { pickup_name: 'KMF Hubli', delivery_name: 'Govt District Hospital', kappa: 'FOOD', weight: 4.0, description: 'Night meals' },
      { pickup_name: 'BVB College of Engg', delivery_name: 'Dharwad Railway Station', kappa: 'ELECTRONICS', weight: 1.5, description: 'Signal equipment' },
    ],
    nl_instruction: 'Run night-shift logistics across all hospitals and stations',
  },
  {
    id: 15, title: 'Disaster Relief Airlift', difficulty: 'hard',
    description: 'Post-earthquake supply drop: medicines, food, blankets to 5 sites from Hubli Airport.',
    loc_indices: [17, 0, 1, 2, 3, 4], seed: 15, n_gfz: 2, incompat_density: 0.2, deadline_tight: 0.85, hazard_mix: 0.2, cap_ratio: 0.9,
    pkg_requests: [
      { pickup_name: 'Hubli Airport', delivery_name: 'SDM Hospital', kappa: 'PHARMA', weight: 5.0, description: 'Disaster meds kit' },
      { pickup_name: 'Hubli Airport', delivery_name: 'KIMS Hospital', kappa: 'GENERAL', weight: 8.0, description: 'Emergency blankets' },
      { pickup_name: 'Hubli Airport', delivery_name: 'Govt District Hospital', kappa: 'FOOD', weight: 6.0, description: 'Food ration packs' },
    ],
    nl_instruction: 'Emergency airlift from airport: dispatch medicine, food and supplies to all hospitals now',
  },
  {
    id: 16, title: 'Multi-Hazard Full City', difficulty: 'expert',
    description: '10-node mission: FLAMMABLE + CRYOGENIC + PHARMA + FOOD all in one run. 4 NFZs, maximum incompat density.',
    loc_indices: [0, 1, 2, 3, 5, 12, 17, 25, 26, 28], seed: 16, n_gfz: 4, incompat_density: 0.6, deadline_tight: 0.8, hazard_mix: 0.8, cap_ratio: 0.85,
    pkg_requests: [
      { pickup_name: 'Hubli Airport', delivery_name: 'SDM Hospital', kappa: 'CRYOGENIC', weight: 3.0, description: 'Cell cultures' },
      { pickup_name: 'Dharwad Industrial Area', delivery_name: 'Almatti Road Warehouse', kappa: 'FLAMMABLE', weight: 5.0, description: 'Solvent' },
      { pickup_name: 'KMF Hubli', delivery_name: 'Urban Oasis Mall', kappa: 'FOOD', weight: 6.0, description: 'Dairy crate' },
      { pickup_name: 'BVB College of Engg', delivery_name: 'KIMS Hospital', kappa: 'ELECTRONICS', weight: 2.0, description: 'Lab sensors' },
    ],
    nl_instruction: 'Execute full hazardous multi-drop across entire Dharwad-Hubli region',
  },
  {
    id: 17, title: 'Capacity Stress Test', difficulty: 'expert',
    description: 'Push drone to 95% payload capacity with 6 packages across 12 nodes. Tests capacity constraint solver.',
    loc_indices: [0, 1, 2, 3, 4, 5, 11, 12, 17, 25, 28, 16], seed: 17, n_gfz: 3, incompat_density: 0.5, deadline_tight: 0.7, hazard_mix: 0.4, cap_ratio: 0.95,
    pkg_requests: [
      { pickup_name: 'Hubli Airport', delivery_name: 'KIMS Hospital', kappa: 'PHARMA', weight: 3.0, description: 'Bulk medicines' },
      { pickup_name: 'KMF Hubli', delivery_name: 'Urban Oasis Mall', kappa: 'FOOD', weight: 4.0, description: 'Milk bulk' },
      { pickup_name: 'BVB College of Engg', delivery_name: 'IIT Dharwad', kappa: 'ELECTRONICS', weight: 2.0, description: 'Lab equipment' },
      { pickup_name: 'SDM Hospital', delivery_name: 'Navodaya Medical College', kappa: 'PHARMA', weight: 2.5, description: 'Surgical kits' },
      { pickup_name: 'Dharwad Industrial Area', delivery_name: 'Almatti Road Warehouse', kappa: 'FLAMMABLE', weight: 3.5, description: 'Chemicals' },
    ],
    nl_instruction: 'Max capacity stress test: push all 6 packages as fast as possible',
  },
  {
    id: 18, title: 'Full Benchmark — All Constraints', difficulty: 'expert',
    description: 'The ultimate benchmark: 14 nodes, 5 NFZs, all hazard types, max incompat density, tight deadlines. Compare all 6 algorithms.',
    loc_indices: [0, 1, 2, 3, 4, 5, 11, 12, 13, 17, 25, 26, 28, 16], seed: 42, n_gfz: 5, incompat_density: 0.7, deadline_tight: 0.9, hazard_mix: 0.9, cap_ratio: 0.9,
    pkg_requests: [
      { pickup_name: 'Hubli Airport', delivery_name: 'SDM Hospital', kappa: 'CRYOGENIC', weight: 2.5, description: 'Stem cell cultures' },
      { pickup_name: 'Dharwad Industrial Area', delivery_name: 'Almatti Road Warehouse', kappa: 'OXIDIZER', weight: 4.0, description: 'Peroxide shipment' },
      { pickup_name: 'KMF Hubli', delivery_name: 'Govt District Hospital', kappa: 'FOOD', weight: 5.0, description: 'Medical diet meals' },
      { pickup_name: 'BVB College of Engg', delivery_name: 'KIMS Hospital', kappa: 'ELECTRONICS', weight: 1.5, description: 'ICU monitors' },
      { pickup_name: 'Nandini Dairy Hubli', delivery_name: 'Navodaya Medical College', kappa: 'FOOD', weight: 3.0, description: 'Nutritional supplements' },
    ],
    nl_instruction: 'Run the full benchmark with all 5 packages, all hazard types, maximum constraints active',
  },
];

const DIFF_COLOR: Record<string, string> = {
  easy: '#22c55e', medium: '#f59e0b', hard: '#ef4444', expert: '#a855f7',
};
const DIFF_BG: Record<string, string> = {
  easy: 'rgba(34,197,94,0.15)', medium: 'rgba(245,158,11,0.15)',
  hard: 'rgba(239,68,68,0.15)', expert: 'rgba(168,85,247,0.15)',
};
const KAPPA_COLOR: Record<string, string> = {
  PHARMA: '#60a5fa', FOOD: '#34d399', ELECTRONICS: '#fbbf24',
  FLAMMABLE: '#f97316', OXIDIZER: '#c084fc', CRYOGENIC: '#67e8f9', GENERAL: '#9ca3af',
};

interface Props {
  onLoadTestCase: (tc: TestCase) => void;
  onRunTestCase: (tc: TestCase) => void;
  selectedId: number | null;
  runningId: number | null;
}

export default function TestCasesPanel({ onLoadTestCase, onRunTestCase, selectedId, runningId }: Props) {
  const [filter, setFilter] = useState<string>('all');
  const [search, setSearch] = useState('');

  const filtered = ALL_TEST_CASES.filter(tc => {
    const matchDiff = filter === 'all' || tc.difficulty === filter;
    const matchSearch = !search ||
      tc.title.toLowerCase().includes(search.toLowerCase()) ||
      tc.description.toLowerCase().includes(search.toLowerCase()) ||
      tc.nl_instruction.toLowerCase().includes(search.toLowerCase());
    return matchDiff && matchSearch;
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '10px 12px 6px', flexShrink: 0, borderBottom: '1px solid #0f1f35' }}>
        <div style={{ fontSize: 11, color: '#64748b', letterSpacing: 1, marginBottom: 6, fontWeight: 600 }}>
          TEST CASES ({ALL_TEST_CASES.length})
        </div>
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search test cases..."
          style={{
            width: '100%', background: '#1e293b', border: '1px solid #334155',
            borderRadius: 6, padding: '5px 8px', color: '#e2e8f0', fontSize: 11,
            outline: 'none', boxSizing: 'border-box',
          }}
        />
        <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
          {['all', 'easy', 'medium', 'hard', 'expert'].map(d => (
            <button key={d} onClick={() => setFilter(d)} style={{
              padding: '2px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
              border: `1px solid ${d === 'all' ? '#475569' : DIFF_COLOR[d] ?? '#475569'}`,
              background: filter === d ? (DIFF_BG[d] ?? 'rgba(71,85,105,0.3)') : 'transparent',
              color: d === 'all' ? '#94a3b8' : DIFF_COLOR[d] ?? '#94a3b8',
            }}>
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Cards list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '6px 8px 12px' }}>
        {filtered.length === 0 && (
          <div style={{ color: '#64748b', textAlign: 'center', marginTop: 24, fontSize: 12 }}>
            No test cases match your search.
          </div>
        )}
        {filtered.map(tc => {
          const isSelected = tc.id === selectedId;
          const isRunning = tc.id === runningId;
          return (
            <div
              key={tc.id}
              onClick={() => onLoadTestCase(tc)}
              style={{
                background: isSelected ? 'rgba(0,212,255,0.08)' : '#0f1623',
                border: `1px solid ${isSelected ? '#00d4ff55' : '#1e293b'}`,
                borderRadius: 8, padding: '10px 10px 8px', marginBottom: 6,
                cursor: 'pointer', transition: 'border-color 0.15s',
              }}
            >
              {/* Title row */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                <span style={{
                  fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 3,
                  color: DIFF_COLOR[tc.difficulty], background: DIFF_BG[tc.difficulty],
                  border: `1px solid ${DIFF_COLOR[tc.difficulty]}44`,
                  textTransform: 'uppercase', letterSpacing: 0.5,
                }}>
                  {tc.difficulty}
                </span>
                <span style={{ fontSize: 10, color: '#94a3b8', fontFamily: 'monospace' }}>
                  TC-{String(tc.id).padStart(2, '0')}
                </span>
                <span style={{ fontSize: 11, color: '#e2e8f0', fontWeight: 600, flex: 1 }}>
                  {tc.title}
                </span>
              </div>

              {/* Description */}
              <div style={{ fontSize: 10, color: '#64748b', lineHeight: 1.4, marginBottom: 5 }}>
                {tc.description}
              </div>

              {/* Stats row */}
              <div style={{ display: 'flex', gap: 10, marginBottom: 5, fontSize: 10, color: '#475569' }}>
                <span>📍 {tc.loc_indices.length} nodes</span>
                <span>📦 {tc.pkg_requests.length} pkgs</span>
                <span>⛔ {tc.n_gfz} NFZ</span>
                <span>⏱ {Math.round(tc.deadline_tight * 100)}% tight</span>
              </div>

              {/* Kappa pills */}
              {tc.pkg_requests.length > 0 && (
                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 5 }}>
                  {tc.pkg_requests.map((p, i) => (
                    <span key={i} style={{
                      fontSize: 9, padding: '1px 5px', borderRadius: 3,
                      color: KAPPA_COLOR[p.kappa] ?? '#9ca3af',
                      background: `${KAPPA_COLOR[p.kappa] ?? '#9ca3af'}1a`,
                      border: `1px solid ${KAPPA_COLOR[p.kappa] ?? '#475569'}44`,
                    }}>
                      {p.kappa} {p.weight}kg
                    </span>
                  ))}
                </div>
              )}

              {/* NL instruction */}
              <div style={{
                fontSize: 9.5, color: '#38bdf8', fontStyle: 'italic',
                background: 'rgba(56,189,248,0.06)', borderLeft: '2px solid #0ea5e9',
                padding: '3px 7px', borderRadius: 2, marginBottom: 8, lineHeight: 1.4,
              }}>
                "{tc.nl_instruction}"
              </div>

              {/* Buttons */}
              <div style={{ display: 'flex', gap: 5 }}>
                <button
                  onClick={e => { e.stopPropagation(); onLoadTestCase(tc); }}
                  style={{
                    flex: 1, padding: '5px 0', borderRadius: 5, fontSize: 10, cursor: 'pointer',
                    background: isSelected ? 'rgba(0,212,255,0.18)' : 'rgba(255,255,255,0.04)',
                    color: isSelected ? '#00d4ff' : '#94a3b8',
                    border: `1px solid ${isSelected ? '#00d4ff55' : '#334155'}`,
                    fontWeight: isSelected ? 700 : 400,
                  }}
                >
                  {isSelected ? '✓ Loaded' : 'Load'}
                </button>
                <button
                  onClick={e => { e.stopPropagation(); onRunTestCase(tc); }}
                  disabled={isRunning}
                  style={{
                    flex: 2, padding: '5px 0', borderRadius: 5, fontSize: 10,
                    background: isRunning ? 'rgba(0,212,255,0.25)' : 'rgba(0,212,255,0.15)',
                    color: '#00d4ff', border: '1px solid #00d4ff44',
                    cursor: isRunning ? 'wait' : 'pointer', fontWeight: 600,
                  }}
                >
                  {isRunning ? '⏳ Running algos…' : '⚡ Run All Algos'}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Export for App.tsx typing
export type { TestCase };
