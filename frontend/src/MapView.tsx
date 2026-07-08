import { useEffect, useRef, useState } from 'react';

declare global {
  interface Window { L: typeof import('leaflet'); }
}

const TILE_LAYERS = {
  street: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attr: '&copy; OpenStreetMap contributors',
    label: 'Street',
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr: 'Tiles &copy; Esri',
    label: 'Satellite',
  },
  dark: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attr: '&copy; OpenStreetMap &copy; CARTO',
    label: 'Dark',
  },
};

const ALGO_COLORS: Record<string, string> = {
  'HNP': '#00d4ff', 'MPDD': '#ff6b6b', 'HNP-NoVerify': '#ffd93d',
  'HNP-NoCompat': '#6bcb77', 'HNP-NoRefine': '#4d96ff', 'NN-PDP': '#ff922b',
};

// Real Dharwad-Hubli location GPS coordinates
const LOCATION_GPS: Record<string, [number, number]> = {
  'SDM Hospital': [15.4589, 74.9814],
  'KIMS Hospital': [15.3647, 75.1240],
  'Suretech Hospital': [15.4502, 74.9923],
  'Navodaya Medical College': [15.4201, 75.1101],
  'Govt District Hospital': [15.4584, 74.9920],
  'Urban Oasis Mall': [15.3620, 75.1349],
  'Akshay Park': [15.4630, 75.0010],
  'Big Bazaar Dharwad': [15.4610, 74.9950],
  'Big Bazaar Hubli': [15.3720, 75.1280],
  'Reliance Fresh Dharwad': [15.4550, 74.9870],
  'Reliance Fresh Hubli': [15.3580, 75.1200],
  'Karnataka University': [15.4672, 74.9882],
  'BVB College of Engg': [15.3750, 75.0100],
  'IIT Dharwad': [15.3928, 74.9985],
  'Sana Shaheen Independent PU College': [15.4487, 75.0042],
  'Karnatak College Dharwad': [15.4598, 74.9799],
  'Dharwad Railway Station': [15.4629, 75.0079],
  'Hubli Airport': [15.3617, 75.0849],
  'Hubli Railway Station': [15.3600, 75.1355],
  'KSRTC Bus Stand Dharwad': [15.4609, 74.9853],
  'KSRTC Bus Stand Hubli': [15.3619, 75.1301],
  'Dharwad Town Hall': [15.4590, 74.9806],
  'Indira Gandhi Glass House Garden': [15.4613, 74.9836],
  'Unkal Lake': [15.3789, 75.1062],
  'Nrupatunga Betta': [15.4570, 74.9751],
  'Dharwad Industrial Area': [15.4501, 74.9692],
  'Almatti Road Warehouse': [15.4421, 74.9601],
  'Gokul Road Hub': [15.3701, 75.1001],
  'KMF Hubli': [15.3548, 75.1180],
  'KMF Dharwad': [15.4588, 74.9764],
  'Nandini Dairy Hubli': [15.3610, 75.1250],
  'Mother Dairy Dharwad': [15.4530, 74.9851],
  'DC Office Dharwad': [15.4607, 74.9834],
  'HUMC Hubli': [15.3672, 75.1290],
  'Siddharoodha Math': [15.3622, 75.1359],
};

export interface AlgoResult {
  algo: string;
  color: string;
  semantic_cost: number;
  distance: number;
  runtime_ms: number;
  feasible: boolean;
  violations: number;
  energy: number;
  route: number[];
}

export interface ReplanResult {
  new_route: string[];
  new_trajectory_gps: [number, number][];
  route_diff: { added: string[]; removed: string[]; rerouted: boolean };
}

interface MapViewProps {
  missionRoute?: string[];
  algoResults?: AlgoResult[];
  replanResult?: ReplanResult | null;
  noFlyZones?: { lat: number; lng: number; radius: number }[];
  showAlgoPaths?: boolean;
}

export default function MapView({
  missionRoute = [],
  algoResults = [],
  replanResult = null,
  noFlyZones = [],
  showAlgoPaths = false,
}: MapViewProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const layersRef = useRef<any[]>([]);
  const [tileMode, setTileMode] = useState<'street' | 'satellite' | 'dark'>('dark');
  const tileLayerRef = useRef<any>(null);

  // Load leaflet from CDN if not already
  useEffect(() => {
    if (window.L) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(link);
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    script.onload = () => initMap();
    document.head.appendChild(script);
  }, []);

  const initMap = () => {
    if (!mapRef.current || mapInstanceRef.current) return;
    const L = window.L;
    const map = L.map(mapRef.current, {
      center: [15.4150, 75.0550],
      zoom: 12,
      zoomControl: true,
    });
    const tileLayer = L.tileLayer(TILE_LAYERS.dark.url, {
      attribution: TILE_LAYERS.dark.attr,
      maxZoom: 19,
    }).addTo(map);
    tileLayerRef.current = tileLayer;
    mapInstanceRef.current = map;

    // Custom CSS for dark map feel
    const style = document.createElement('style');
    style.textContent = `
      .leaflet-container { background: #0a0e1a !important; }
      .leaflet-tile-pane { filter: brightness(0.85) saturate(0.7); }
      .uav-marker { animation: pulse 1.5s infinite; }
      @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.3)} }
      .nfz-label { background: transparent; border: none; color: #ef4444; font-size: 10px; font-weight: 700; }
    `;
    document.head.appendChild(style);

    drawAll();
  };

  useEffect(() => {
    if (window.L && mapInstanceRef.current) {
      drawAll();
    } else if (window.L && !mapInstanceRef.current) {
      initMap();
    }
  }, [missionRoute, algoResults, replanResult, noFlyZones, showAlgoPaths]);

  useEffect(() => {
    if (!mapInstanceRef.current || !tileLayerRef.current) return;
    const L = window.L;
    tileLayerRef.current.setUrl(TILE_LAYERS[tileMode].url);
  }, [tileMode]);

  const clearLayers = () => {
    layersRef.current.forEach(l => {
      try { mapInstanceRef.current?.removeLayer(l); } catch {}
    });
    layersRef.current = [];
  };

  const drawAll = () => {
    const L = window.L;
    const map = mapInstanceRef.current;
    if (!L || !map) return;
    clearLayers();

    // Draw no-fly zones
    noFlyZones.forEach((nfz, i) => {
      const circle = L.circle([nfz.lat, nfz.lng], {
        radius: nfz.radius,
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.12,
        weight: 2,
        dashArray: '6 4',
      }).addTo(map);
      const label = L.marker([nfz.lat, nfz.lng], {
        icon: L.divIcon({
          className: 'nfz-label',
          html: `<div style="color:#ef4444;font-size:10px;font-weight:700;text-shadow:0 0 4px #000">⛔ NFZ-${i+1}</div>`,
          iconAnchor: [20, 8],
        }),
      }).addTo(map);
      layersRef.current.push(circle, label);
    });

    // Draw mission route (primary path)
    if (missionRoute.length >= 2) {
      const coords: [number, number][] = missionRoute
        .map(n => LOCATION_GPS[n])
        .filter(Boolean);

      if (coords.length >= 2) {
        // Animated dashed path
        const poly = L.polyline(coords, {
          color: '#00d4ff',
          weight: 3,
          opacity: 0.9,
          dashArray: '8 4',
        }).addTo(map);
        layersRef.current.push(poly);

        // Location markers
        coords.forEach((coord, i) => {
          const name = missionRoute[i];
          const isDepot = i === 0;
          const isLast = i === coords.length - 1;
          const icon = L.divIcon({
            className: '',
            html: `<div style="
              width:${isDepot ? 18 : 12}px;
              height:${isDepot ? 18 : 12}px;
              border-radius:50%;
              background:${isDepot ? '#00d4ff' : isLast ? '#22c55e' : '#f59e0b'};
              border:2px solid #fff;
              box-shadow:0 0 8px ${isDepot ? '#00d4ff' : '#f59e0b'}88;
            "></div>`,
            iconSize: [isDepot ? 18 : 12, isDepot ? 18 : 12],
            iconAnchor: [isDepot ? 9 : 6, isDepot ? 9 : 6],
          });
          const marker = L.marker(coord, { icon })
            .bindTooltip(`<b>${name}</b>${isDepot ? '<br><span style="color:#00d4ff">📦 DEPOT</span>' : ''}`, {
              permanent: false, direction: 'top',
            })
            .addTo(map);
          layersRef.current.push(marker);
        });

        // UAV drone marker at midpoint
        const mid = coords[Math.floor(coords.length / 2)];
        const droneIcon = L.divIcon({
          className: 'uav-marker',
          html: `<div style="font-size:22px;filter:drop-shadow(0 0 6px #00d4ff)">🛸</div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });
        const droneMarker = L.marker(mid, { icon: droneIcon })
          .bindTooltip('UAV Active', { permanent: false })
          .addTo(map);
        layersRef.current.push(droneMarker);

        map.fitBounds(poly.getBounds(), { padding: [40, 40] });
      }
    }

    // Draw algo comparison paths
    if (showAlgoPaths && algoResults.length > 0) {
      // Generate synthetic GPS paths for each algo using location offsets
      const baseCoords: [number, number][] = missionRoute
        .map(n => LOCATION_GPS[n])
        .filter(Boolean);
      if (baseCoords.length >= 2) {
        algoResults.forEach((algo, ai) => {
          const offsets = algo.route.map((_, i) => {
            const base = baseCoords[i % baseCoords.length];
            // Add small jitter per algo to separate paths
            const jitter = 0.003 * (ai - algoResults.length / 2);
            return [base[0] + jitter, base[1] + jitter * 0.7] as [number, number];
          });
          const algoCoords = offsets.length >= 2 ? offsets : baseCoords;
          const algoLine = L.polyline(algoCoords, {
            color: ALGO_COLORS[algo.algo] ?? algo.color,
            weight: 2.5,
            opacity: algo.feasible ? 0.85 : 0.35,
            dashArray: algo.feasible ? undefined : '4 6',
          }).bindTooltip(
            `<b>${algo.algo}</b><br>Cost: ${algo.semantic_cost.toFixed(0)}<br>Feasible: ${algo.feasible ? '✅' : '❌'}`,
            { sticky: true }
          ).addTo(map);
          layersRef.current.push(algoLine);
        });
      }
    }

    // Draw replan overlay (old vs new route)
    if (replanResult) {
      const newCoords = replanResult.new_trajectory_gps;
      if (newCoords.length >= 2) {
        const newLine = L.polyline(newCoords, {
          color: '#22c55e',
          weight: 4,
          opacity: 0.9,
          dashArray: undefined,
        }).bindTooltip('✅ New Route (after NL replan)', { sticky: true }).addTo(map);
        layersRef.current.push(newLine);

        // Mark added stops with green pins
        replanResult.route_diff.added.forEach(locName => {
          const gps = LOCATION_GPS[locName];
          if (!gps) return;
          const icon = L.divIcon({
            html: `<div style="font-size:20px">📍</div>`,
            iconSize: [20, 20], iconAnchor: [10, 20],
          });
          const m = L.marker(gps, { icon })
            .bindTooltip(`➕ Added: ${locName}`, { permanent: true, direction: 'top' })
            .addTo(map);
          layersRef.current.push(m);
        });
      }
    }
  };

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: '#0a0e1a' }}>
      <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

      {/* Tile mode switcher */}
      <div style={{
        position: 'absolute', top: 10, right: 10, zIndex: 1000,
        display: 'flex', gap: 4, background: 'rgba(10,14,26,0.9)',
        border: '1px solid #1e293b', borderRadius: 6, padding: 4,
      }}>
        {(Object.keys(TILE_LAYERS) as (keyof typeof TILE_LAYERS)[]).map(mode => (
          <button
            key={mode}
            onClick={() => setTileMode(mode)}
            style={{
              padding: '3px 8px', borderRadius: 4, fontSize: 10, cursor: 'pointer',
              background: tileMode === mode ? 'rgba(0,212,255,0.2)' : 'transparent',
              color: tileMode === mode ? '#00d4ff' : '#64748b',
              border: `1px solid ${tileMode === mode ? '#00d4ff44' : 'transparent'}`,
            }}
          >
            {TILE_LAYERS[mode].label}
          </button>
        ))}
      </div>

      {/* Legend */}
      <div style={{
        position: 'absolute', bottom: 10, left: 10, zIndex: 1000,
        background: 'rgba(10,14,26,0.92)', border: '1px solid #1e293b',
        borderRadius: 6, padding: '6px 10px', fontSize: 10, color: '#94a3b8',
      }}>
        <div style={{ marginBottom: 3, color: '#64748b', letterSpacing: 1 }}>LEGEND</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
          <div style={{ width: 20, height: 3, background: '#00d4ff', borderRadius: 2 }} />
          <span>Mission Route</span>
        </div>
        {showAlgoPaths && Object.entries(ALGO_COLORS).map(([name, color]) => (
          <div key={name} style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
            <div style={{ width: 20, height: 3, background: color, borderRadius: 2 }} />
            <span>{name}</span>
          </div>
        ))}
        {replanResult && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
            <div style={{ width: 20, height: 3, background: '#22c55e', borderRadius: 2 }} />
            <span>Replanned Route</span>
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <div style={{ width: 20, height: 3, background: '#ef4444', borderRadius: 2, borderTop: '1px dashed #ef4444' }} />
          <span>No-Fly Zone</span>
        </div>
      </div>
    </div>
  );
}
