/**
 * MapView — Leaflet-based realistic map for UAV-LLM Mission Control.
 * Uses react-leaflet (npm, bundled). NO CDN script injection.
 * Black-screen fixes:
 *   1. Container has explicit height:100% + position:absolute inset:0
 *   2. Map is destroyed on unmount via useEffect cleanup
 *   3. Tile layer is swapped, not recreated (avoids re-init)
 */
import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix leaflet default icon paths broken by Vite bundler
import iconUrl from 'leaflet/dist/images/marker-icon.png';
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png';
import shadowUrl from 'leaflet/dist/images/marker-shadow.png';
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl });

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

const TILE_LAYERS = {
  dark: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attr: '&copy; OpenStreetMap &copy; CARTO',
  },
  street: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attr: '&copy; OpenStreetMap contributors',
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr: 'Tiles &copy; Esri',
  },
};

const ALGO_COLORS: Record<string, string> = {
  'HNP': '#00d4ff', 'MPDD': '#ff6b6b', 'HNP-NoVerify': '#ffd93d',
  'HNP-NoCompat': '#6bcb77', 'HNP-NoRefine': '#4d96ff', 'NN-PDP': '#ff922b',
};

// Real GPS for all 35 Dharwad-Hubli locations
export const LOCATION_GPS: Record<string, [number, number]> = {
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

interface MapViewProps {
  missionRoute?: string[];
  algoResults?: AlgoResult[];
  replanResult?: ReplanResult | null;
  noFlyZones?: { lat: number; lng: number; radius: number }[];
  showAlgoPaths?: boolean;
  playing?: boolean;
  tileMode?: 'dark' | 'street' | 'satellite';
}

export default function MapView({
  missionRoute = [],
  algoResults = [],
  replanResult = null,
  noFlyZones = [],
  showAlgoPaths = false,
  playing = false,
  tileMode = 'dark',
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileRef = useRef<L.TileLayer | null>(null);
  const layersRef = useRef<L.Layer[]>([]);
  const droneMarkerRef = useRef<L.Marker | null>(null);
  const animFrameRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const droneStepRef = useRef(0);

  // Init map once on mount
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, {
      center: [15.4150, 75.0550],
      zoom: 12,
      zoomControl: true,
      attributionControl: true,
    });

    const tile = L.tileLayer(TILE_LAYERS.dark.url, {
      attribution: TILE_LAYERS.dark.attr,
      maxZoom: 19,
    });
    tile.addTo(map);
    tileRef.current = tile;
    mapRef.current = map;

    // Force map to know its size (fixes blank tile / wrong center issues)
    setTimeout(() => map.invalidateSize(), 200);

    return () => {
      if (animFrameRef.current) clearInterval(animFrameRef.current);
      map.remove();
      mapRef.current = null;
      tileRef.current = null;
    };
  }, []);

  // Switch tile mode
  useEffect(() => {
    const map = mapRef.current;
    const tile = tileRef.current;
    if (!map || !tile) return;
    tile.setUrl(TILE_LAYERS[tileMode].url);
  }, [tileMode]);

  // Redraw overlays when data changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Clear old layers
    layersRef.current.forEach(l => { try { map.removeLayer(l); } catch {} });
    layersRef.current = [];
    if (droneMarkerRef.current) { try { map.removeLayer(droneMarkerRef.current); } catch {} droneMarkerRef.current = null; }
    if (animFrameRef.current) { clearInterval(animFrameRef.current); animFrameRef.current = null; }
    droneStepRef.current = 0;

    // Build GPS coords from route names
    const routeCoords: [number, number][] = missionRoute
      .map(n => LOCATION_GPS[n])
      .filter(Boolean) as [number, number][];

    // -- No-fly zones --
    noFlyZones.forEach((nfz, i) => {
      const circle = L.circle([nfz.lat, nfz.lng], {
        radius: nfz.radius,
        color: '#ef4444', fillColor: '#ef4444',
        fillOpacity: 0.10, weight: 2, dashArray: '6 4',
      });
      const label = L.marker([nfz.lat, nfz.lng], {
        icon: L.divIcon({
          className: '',
          html: `<div style="color:#ef4444;font-size:11px;font-weight:700;text-shadow:0 0 4px #000;white-space:nowrap">⛔ NFZ-${i + 1}</div>`,
          iconAnchor: [24, 8],
        }),
      });
      circle.addTo(map); label.addTo(map);
      layersRef.current.push(circle, label);
    });

    // -- Mission route polyline + markers --
    if (routeCoords.length >= 2) {
      const poly = L.polyline(routeCoords, {
        color: '#00d4ff', weight: 3, opacity: 0.85, dashArray: '10 5',
      });
      poly.addTo(map);
      layersRef.current.push(poly);

      // Location markers
      routeCoords.forEach((coord, i) => {
        const name = missionRoute[i];
        const isDepot = i === 0;
        const isLast = i === routeCoords.length - 1;
        const dot = L.circleMarker(coord, {
          radius: isDepot ? 10 : 7,
          color: '#fff',
          fillColor: isDepot ? '#00d4ff' : isLast ? '#22c55e' : '#f59e0b',
          fillOpacity: 1,
          weight: 2,
        });
        dot.bindTooltip(
          `<b>${name}</b>${isDepot ? '<br><span style="color:#00d4ff">📦 DEPOT / START</span>' : isLast ? '<br><span style="color:#22c55e">🏁 FINAL DELIVERY</span>' : ''}`,
          { permanent: false, direction: 'top', className: '' }
        );
        dot.addTo(map);
        layersRef.current.push(dot);

        // Permanent name label
        const labelM = L.marker(coord, {
          icon: L.divIcon({
            className: '',
            html: `<div style="background:rgba(10,14,26,0.85);border:1px solid ${isDepot ? '#00d4ff' : '#334155'};border-radius:4px;padding:2px 5px;color:${isDepot ? '#00d4ff' : '#94a3b8'};font-size:9px;white-space:nowrap;margin-top:14px">${name.length > 20 ? name.slice(0, 18) + '…' : name}</div>`,
            iconAnchor: [-2, 0],
          }),
        });
        labelM.addTo(map);
        layersRef.current.push(labelM);
      });

      // Fit map to route
      map.fitBounds(L.latLngBounds(routeCoords).pad(0.15));

      // -- Animated drone marker --
      const droneIcon = L.divIcon({
        className: '',
        html: `<div class="uav-drone-icon" style="font-size:26px;filter:drop-shadow(0 0 10px #00d4ff)">🛸</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
      });
      const droneMarker = L.marker(routeCoords[0], { icon: droneIcon, zIndexOffset: 1000 });
      droneMarker.bindTooltip('UAV', { permanent: true, direction: 'top', className: '' });
      droneMarker.addTo(map);
      droneMarkerRef.current = droneMarker;

      // Interpolate drone along route
      const totalSteps = routeCoords.length - 1;
      let progress = 0;
      const speed = 0.004;
      const anim = setInterval(() => {
        if (!droneMarkerRef.current) { clearInterval(anim); return; }
        progress += speed;
        if (progress > totalSteps) progress = 0; // loop
        const segIdx = Math.floor(progress);
        const t = progress - segIdx;
        const from = routeCoords[Math.min(segIdx, totalSteps - 1)];
        const to = routeCoords[Math.min(segIdx + 1, totalSteps)];
        const lat = from[0] + (to[0] - from[0]) * t;
        const lng = from[1] + (to[1] - from[1]) * t;
        droneMarkerRef.current.setLatLng([lat, lng]);
      }, 50);
      animFrameRef.current = anim;
    }

    // -- Algo comparison paths --
    if (showAlgoPaths && algoResults.length > 0 && routeCoords.length >= 2) {
      algoResults.forEach((algo, ai) => {
        const jitter = 0.0025 * (ai - algoResults.length / 2);
        const jittered: [number, number][] = routeCoords.map(
          ([lat, lng]) => [lat + jitter, lng + jitter * 0.8]
        );
        const line = L.polyline(jittered, {
          color: ALGO_COLORS[algo.algo] ?? algo.color,
          weight: 2.5,
          opacity: algo.feasible ? 0.8 : 0.3,
          dashArray: algo.feasible ? undefined : '5 7',
        });
        line.bindTooltip(
          `<b>${algo.algo}</b><br>Cost: ${algo.semantic_cost.toFixed(0)}<br>Feasible: ${algo.feasible ? '✅' : '❌'}<br>Violations: ${algo.violations}`,
          { sticky: true }
        );
        line.addTo(map);
        layersRef.current.push(line);
      });
    }

    // -- NL Replan overlay --
    if (replanResult && replanResult.new_trajectory_gps.length >= 2) {
      const newLine = L.polyline(replanResult.new_trajectory_gps, {
        color: '#22c55e', weight: 4, opacity: 0.9,
      });
      newLine.bindTooltip('✅ Replanned Route', { sticky: true });
      newLine.addTo(map);
      layersRef.current.push(newLine);

      replanResult.route_diff.added.forEach(locName => {
        const gps = LOCATION_GPS[locName];
        if (!gps) return;
        const pin = L.marker(gps, {
          icon: L.divIcon({
            className: '',
            html: `<div style="font-size:20px">📍</div>`,
            iconSize: [20, 20], iconAnchor: [10, 20],
          }),
        });
        pin.bindTooltip(`＋ Added: ${locName}`, { permanent: true, direction: 'top' });
        pin.addTo(map);
        layersRef.current.push(pin);
      });
    }

    map.invalidateSize();
  }, [missionRoute, algoResults, replanResult, noFlyZones, showAlgoPaths]);

  // Pause/resume drone animation
  useEffect(() => {
    if (!animFrameRef.current) return;
    // Animation runs always (loops); playing flag could throttle speed in future
  }, [playing]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 400, background: '#0a0e1a' }}>
      <div
        ref={containerRef}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      />
    </div>
  );
}
