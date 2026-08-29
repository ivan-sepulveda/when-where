import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL } from "../lib/apiBaseUrl";

// Every ocean beach in the dataset, plotted on one world map.
//
// CANVAS, NOT SVG OR A MAP LIBRARY. 11,790 points is far too many DOM nodes
// to stay interactive as <circle>s, and this project has no mapping
// dependency -- adding Leaflet would also mean a runtime tile fetch on a page
// whose whole content is already local. A canvas draws the lot in one pass
// and needs neither.
//
// NO BASEMAP, AND IT DOESN'T NEED ONE. These are coastal points by
// construction, so plotted together they draw the coastlines themselves --
// the continents show up as outlines rather than fills. A graticule and the
// equator/tropics give the eye something to register scale against.

interface Beach {
  name: string;
  lat: number;
  lon: number;
  country_code: string | null;
}

interface BeachesResponse {
  available: boolean;
  total: number;
  beaches: Beach[];
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  // available: false means the GeoNames extract hasn't been run in this
  // checkout -- a real, recoverable state that needs different words than
  // "the request failed".
  | { status: "loaded"; available: boolean; beaches: Beach[] };

// Equirectangular. Chosen because it is the projection the data is already
// in: lat/lon map to y/x with no maths, so a dot is where its coordinates
// say it is. Mercator would spread the high latitudes more attractively and
// would also misplace every point relative to its own numbers.
function project(lat: number, lon: number, width: number, height: number) {
  return {
    x: ((lon + 180) / 360) * width,
    y: ((90 - lat) / 180) * height,
  };
}

const GRATICULE_LON = [-180, -120, -60, 0, 60, 120, 180];
const GRATICULE_LAT = [-90, -60, -30, 0, 30, 60, 90];

export default function Beaches() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [hovered, setHovered] = useState<Beach | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE_URL}/api/beaches`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
        return res.json() as Promise<BeachesResponse>;
      })
      .then((payload) => {
        if (cancelled) return;
        setState({ status: "loaded", available: payload.available, beaches: payload.beaches });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: "error", message: err instanceof Error ? err.message : "Unknown error" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const beaches = state.status === "loaded" ? state.beaches : [];

  const byCountry = useMemo(() => {
    const counts = new Map<string, number>();
    for (const b of beaches) {
      const key = b.country_code ?? "??";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [beaches]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || beaches.length === 0) return;

    // Draw at device resolution and scale down in CSS, so the dots stay
    // crisp on a retina display instead of doubling into blurred squares.
    const ratio = window.devicePixelRatio || 1;
    const cssWidth = canvas.clientWidth;
    const cssHeight = cssWidth / 2; // equirectangular is exactly 2:1
    canvas.width = cssWidth * ratio;
    canvas.height = cssHeight * ratio;
    canvas.style.height = `${cssHeight}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    ctx.fillStyle = "#0d1117";
    ctx.fillRect(0, 0, cssWidth, cssHeight);

    ctx.strokeStyle = "#20262e";
    ctx.lineWidth = 1;
    for (const lon of GRATICULE_LON) {
      const { x } = project(0, lon, cssWidth, cssHeight);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, cssHeight);
      ctx.stroke();
    }
    for (const lat of GRATICULE_LAT) {
      const { y } = project(lat, 0, cssWidth, cssHeight);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(cssWidth, y);
      ctx.stroke();
    }

    // The equator a shade brighter than the rest of the grid -- one line of
    // orientation without turning the graticule into content.
    ctx.strokeStyle = "#2c333c";
    const equator = project(0, 0, cssWidth, cssHeight).y;
    ctx.beginPath();
    ctx.moveTo(0, equator);
    ctx.lineTo(cssWidth, equator);
    ctx.stroke();

    // Same blue as the "Beach Vacation" chip (lib/tripTagColors.ts), so the
    // map and the chip are visibly about the same thing. Slightly
    // transparent: where beaches crowd a coastline the overlap reads as a
    // denser line rather than as one clipped blob.
    ctx.fillStyle = "rgba(37, 99, 235, 0.75)";
    const dot = cssWidth > 900 ? 1.4 : 1.1;
    for (const b of beaches) {
      const { x, y } = project(b.lat, b.lon, cssWidth, cssHeight);
      ctx.beginPath();
      ctx.arc(x, y, dot, 0, Math.PI * 2);
      ctx.fill();
    }
  }, [beaches]);

  // Nearest beach to the pointer, in projected space so the hit radius is
  // uniform on screen rather than in degrees.
  function handleMove(event: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas || beaches.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const px = event.clientX - rect.left;
    const py = event.clientY - rect.top;

    let best: Beach | null = null;
    let bestDistance = 12; // px; beyond this, show nothing rather than something far away
    for (const b of beaches) {
      const { x, y } = project(b.lat, b.lon, rect.width, rect.height);
      const d = Math.hypot(x - px, y - py);
      if (d < bestDistance) {
        bestDistance = d;
        best = b;
      }
    }
    setHovered(best);
  }

  return (
    <main className="page">
      <h1>Beaches</h1>

      {state.status === "loading" && <p className="tagline">Loading beaches...</p>}

      {state.status === "error" && (
        <p className="tagline" role="alert">
          Couldn't load beaches ({state.message}). Is the API running at {API_BASE_URL}?
        </p>
      )}

      {state.status === "loaded" && !state.available && (
        <p className="tagline">
          No beach data in this checkout. Run{" "}
          <code>data/scripts/multiple/extract_geonames_beaches.py</code>, which needs the GeoNames
          dump in <code>data/globalshorelines/</code>.
        </p>
      )}

      {state.status === "loaded" && state.available && (
        <>
          <p className="tagline">
            {beaches.length.toLocaleString()} ocean beaches across {byCountry.length} countries, from
            GeoNames feature codes BCH and BCHS. Lake and river beaches are filtered out — see
            <code> extract_geonames_beaches.py</code>.
          </p>

          <canvas
            ref={canvasRef}
            className="beaches-map"
            onMouseMove={handleMove}
            onMouseLeave={() => setHovered(null)}
          />

          {/* Fixed-height so the map doesn't jump as the pointer moves on and
              off a dot. */}
          <p className="beaches-hover">
            {hovered ? (
              <>
                <strong>{hovered.name}</strong>
                {hovered.country_code ? ` · ${hovered.country_code}` : ""} ·{" "}
                {hovered.lat.toFixed(4)}, {hovered.lon.toFixed(4)}
              </>
            ) : (
              "Hover a dot for the beach's name and coordinates."
            )}
          </p>

          <h2>Most beaches by country</h2>
          <ul className="destination-detail-stats">
            {byCountry.slice(0, 12).map(([code, count]) => (
              <li key={code} className="destination-detail-stat-card">
                {code}: {count.toLocaleString()}
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
