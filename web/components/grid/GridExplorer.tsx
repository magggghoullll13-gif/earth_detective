
"use client";

import { useEffect, useRef, useState } from "react";

type Cell = {
  cell_id: string;
  row: number;
  col: number;
  cell_size_m: number;
  full_area_km2: number;
  clipped_area_km2: number;
  coverage_ratio: number;
  neighbors_4: string[] | string;
  neighbors_8: string[] | string;
};

type GridData = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    properties: Cell;
    geometry: any;
  }[];
};

const DATA_URL =
  "/data/grids/sindh_study_window_grid_5km.geojson";

function parseNeighbors(value: string[] | string): string[] {
  if (Array.isArray(value)) return value;

  try {
    return JSON.parse(value || "[]");
  } catch {
    return [];
  }
}

function getBounds(data: GridData) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;

  function visit(value: any) {
    if (
      Array.isArray(value) &&
      typeof value[0] === "number" &&
      typeof value[1] === "number"
    ) {
      west = Math.min(west, value[0]);
      south = Math.min(south, value[1]);
      east = Math.max(east, value[0]);
      north = Math.max(north, value[1]);
      return;
    }

    if (Array.isArray(value)) value.forEach(visit);
  }

  data.features.forEach((feature) =>
    visit(feature.geometry.coordinates)
  );

  return [[west, south], [east, north]];
}

export default function GridExplorer() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const selectedRef = useRef<Cell | null>(null);
  const gridRef = useRef<GridData | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [grid, setGrid] = useState<GridData | null>(null);
  const [selected, setSelected] = useState<Cell | null>(null);

  const [showGrid, setShowGrid] = useState(true);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [showNeighbors, setShowNeighbors] = useState(true);
  const [neighborMode, setNeighborMode] = useState<4 | 8>(8);
  const [gridOpacity, setGridOpacity] = useState(65);

  const [mapReady, setMapReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let map: any;

    async function initializeMap() {
      try {
        const response = await fetch(DATA_URL);

        if (!response.ok) {
          throw new Error("Unable to load the grid GeoJSON.");
        }

        const data: GridData = await response.json();

        if (!data.features?.length) {
          throw new Error("The GeoJSON contains no cells.");
        }

        if (cancelled || !mapContainer.current) return;

        setGrid(data);
        gridRef.current = data;

        const maplibregl = await import("maplibre-gl");
        maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");

        if (cancelled || !mapContainer.current) return;

        const mapStyle = {
          version: 8,
          sources: {
            satellite: {
              type: "raster",
              tiles: [
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              ],
              tileSize: 256,
              attribution:
                "Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community"
            }
          },
          layers: [
            {
              id: "satellite-layer",
              type: "raster",
              source: "satellite",
              minzoom: 0,
              maxzoom: 19
            }
          ]
        } as any;

        map = new maplibregl.Map({
          container: mapContainer.current,
          style: mapStyle,
          center: [68.75, 26],
          zoom: 6,
          maxZoom: 18,
          renderWorldCopies: false,
        });

        // MAPLIBRE DEBUG
        map.on("error", (event: any) => {
          console.error("MAPLIBRE ERROR:", event.error);
        });

        console.log("MAPLIBRE DEBUG: Map initialized");
        console.log("GRID FEATURES:", data.features.length);
        console.log("GRID BOUNDS:", getBounds(data));

        mapRef.current = map;

        map.addControl(
          new maplibregl.NavigationControl(),
          "top-right"
        );

        map.addControl(
          new maplibregl.ScaleControl({
            unit: "metric"
          }),
          "bottom-left"
        );

        map.on("load", () => {
          if (cancelled) return;

          map.addSource("grid-data", {
            type: "geojson",
            data
          });

          map.addLayer({
            id: "grid-fill",
            type: "fill",
            source: "grid-data",
            paint: {
              "fill-color": "#25bde8",
              "fill-opacity": gridOpacity / 100
            }
          });

          map.addLayer({
            id: "grid-outline",
            type: "line",
            source: "grid-data",
            paint: {
              "line-color": "#a5eaff",
              "line-width": 0.55,
              "line-opacity": 0.65
            }
          });

          map.addLayer({
            id: "grid-neighbors",
            type: "fill",
            source: "grid-data",
            filter: ["==", ["get", "cell_id"], "__none__"],
            paint: {
              "fill-color": "#f5c451",
              "fill-opacity": 0.75
            }
          });

          map.addLayer({
            id: "grid-selected",
            type: "line",
            source: "grid-data",
            filter: ["==", ["get", "cell_id"], "__none__"],
            paint: {
              "line-color": "#ffffff",
              "line-width": 3
            }
          });

          const bounds = getBounds(data);

          map.fitBounds(bounds, {
            padding: 65,
            duration: 0
          });
          map.once("idle", () => {
            console.log("========== GRID DIAGNOSTICS ==========");
            console.log("Features:", data.features.length);
            console.log("Source exists:", !!map.getSource("grid-data"));
            console.log("Fill layer:", !!map.getLayer("grid-fill"));
            console.log("Outline layer:", !!map.getLayer("grid-outline"));
            console.log(
              "Rendered features:",
              map.queryRenderedFeatures({
                layers: ["grid-fill"]
              }).length
            );
            console.log("Map bounds:", map.getBounds());
            console.log("======================================");
          });

          map.on("click", "grid-fill", (event: any) => {
            const feature = event.features?.[0];

            if (!feature?.properties) return;

            const cell = feature.properties as Cell;

            selectedRef.current = cell;
            setSelected(cell);
          });

          map.on("mouseenter", "grid-fill", () => {
            map.getCanvas().style.cursor = "pointer";
          });

          map.on("mouseleave", "grid-fill", () => {
            map.getCanvas().style.cursor = "";
          });

          setMapReady(true);
        });
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Map initialization failed."
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    initializeMap();

    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
    };
  }, []);

  // Update selected cell and its neighbors
  useEffect(() => {
    const map = mapRef.current;

    if (!map || !mapReady || !map.getLayer("grid-selected")) {
      return;
    }

    if (!selected) {
      map.setFilter("grid-neighbors", [
        "==", ["get", "cell_id"], "__none__"
      ]);

      map.setFilter("grid-selected", [
        "==", ["get", "cell_id"], "__none__"
      ]);

      return;
    }

    const neighbors = parseNeighbors(
      neighborMode === 4
        ? selected.neighbors_4
        : selected.neighbors_8
    );

    map.setFilter("grid-neighbors", [
      "in",
      ["get", "cell_id"],
      ["literal", neighbors]
    ]);

    map.setFilter("grid-selected", [
      "==",
      ["get", "cell_id"],
      selected.cell_id
    ]);
  }, [selected, neighborMode, mapReady]);

  // Grid visibility and opacity
  useEffect(() => {
    const map = mapRef.current;

    if (!map || !mapReady) return;

    const visibility = showGrid ? "visible" : "none";

    ["grid-fill", "grid-outline", "grid-neighbors", "grid-selected"]
      .forEach((layer) => {
        if (map.getLayer(layer)) {
          map.setLayoutProperty(
            layer,
            "visibility",
            visibility
          );
        }
      });

    if (map.getLayer("grid-fill")) {
      map.setPaintProperty(
        "grid-fill",
        "fill-opacity",
        gridOpacity / 100
      );
    }
  }, [showGrid, gridOpacity, mapReady]);

  const features = grid?.features ?? [];

  const boundaryCount = features.filter(
    (f) => f.properties.coverage_ratio < 0.9999
  ).length;

  function resetMap() {
    const map = mapRef.current;
    if (!map || !grid) return;

    map.fitBounds(getBounds(grid), {
      padding: 65,
      duration: 800
    });

    setSelected(null);
    selectedRef.current = null;
  }

  const selectedNeighborCount = selected
    ? parseNeighbors(
        neighborMode === 4
          ? selected.neighbors_4
          : selected.neighbors_8
      ).length
    : 0;

  return (
    <main className="min-h-screen bg-[#07111e] p-4 text-white md:p-6">

      <div className="mx-auto max-w-[1800px] space-y-5">

        {/* HEADER */}
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-cyan-400">
              Earth Detective / Spatial Intelligence
            </p>

            <h1 className="mt-2 text-3xl font-bold">
              Universal Grid Explorer
            </h1>

            <p className="mt-1 text-sm text-slate-400">
              Sindh study window · 5 km fixed geographic grid
            </p>
          </div>

          <button
            onClick={resetMap}
            className="rounded-lg border border-white/15 px-4 py-2 text-sm hover:bg-white/10"
          >
            Fit study area
          </button>
        </header>

        {/* STATISTICS */}
        <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {[
            ["Total cells", features.length.toLocaleString()],
            ["Boundary cells", boundaryCount.toLocaleString()],
            ["Resolution", "5 × 5 km"],
            ["Selected cell", selected?.cell_id ?? "None"]
          ].map(([label, value]) => (
            <div
              key={label}
              className="rounded-xl border border-white/10 bg-[#111e2d] p-4"
            >
              <p className="text-xs text-slate-400">{label}</p>
              <p className="mt-2 truncate text-xl font-bold text-cyan-300">
                {value}
              </p>
            </div>
          ))}
        </section>

        {/* MAP + PANEL */}
        <section className="grid gap-4 xl:grid-cols-[1fr_330px]">

          {/* MAP */}
          <div className="overflow-hidden rounded-xl border border-white/10 bg-[#101b29]">

            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 p-4">
              <div>
                <h2 className="font-semibold">Satellite map</h2>
                <p className="text-xs text-slate-400">
                  Click a grid cell to inspect its neighborhood
                </p>
              </div>

              <span className="rounded-md bg-cyan-400/10 px-3 py-1 text-xs text-cyan-300">
                MAPLIBRE · SATELLITE
              </span>
            </div>

            <div className="relative">
              <div
                ref={mapContainer}
                className="h-[600px] w-full"
              />

              {loading && (
                <div className="absolute inset-0 flex items-center justify-center bg-[#07111e]">
                  Loading geographic data...
                </div>
              )}

              {error && (
                <div className="absolute inset-0 flex items-center justify-center bg-[#07111e] p-6 text-center text-red-300">
                  {error}
                </div>
              )}

              <div className="absolute bottom-4 right-4 rounded-lg border border-white/10 bg-[#07111e]/90 p-3 text-xs backdrop-blur">
                <p className="mb-2 font-semibold">Map legend</p>
                <p className="mb-1 text-cyan-300">■ Grid cells</p>
                <p className="mb-1 text-amber-300">■ Neighbors</p>
                <p className="text-white">■ Selected cell</p>
              </div>
            </div>
          </div>

          {/* SIDE PANEL */}
          <aside className="space-y-4">

            {/* LAYERS */}
            <div className="rounded-xl border border-white/10 bg-[#111e2d] p-4">
              <h3 className="font-semibold">Map layers</h3>

              <label className="mt-5 flex items-center justify-between text-sm">
                <span>5 km geographic grid</span>
                <input
                  type="checkbox"
                  checked={showGrid}
                  onChange={(e) => setShowGrid(e.target.checked)}
                  className="accent-cyan-400"
                />
              </label>

              <div className="mt-4">
                <label className="text-xs text-slate-400">
                  Grid opacity: {gridOpacity}%
                </label>

                <input
                  type="range"
                  min="10"
                  max="100"
                  value={gridOpacity}
                  onChange={(e) =>
                    setGridOpacity(Number(e.target.value))
                  }
                  className="mt-2 w-full accent-cyan-400"
                />
              </div>

              <div className="mt-5 border-t border-white/10 pt-4">
                <label className="flex items-center justify-between text-sm text-slate-500">
                  Environmental heatmap
                  <input
                    type="checkbox"
                    checked={showHeatmap}
                    disabled
                    onChange={(e) => setShowHeatmap(e.target.checked)}
                  />
                </label>

                <p className="mt-2 text-xs text-amber-300">
                  Waiting for real gridded environmental data.
                </p>
              </div>
            </div>

            {/* NEIGHBORS */}
            <div className="rounded-xl border border-white/10 bg-[#111e2d] p-4">
              <h3 className="font-semibold">Neighborhood analysis</h3>

              <label className="mt-4 flex items-center justify-between text-sm">
                Highlight neighbors
                <input
                  type="checkbox"
                  checked={showNeighbors}
                  onChange={(e) => {
                    const enabled = e.target.checked;
                    setShowNeighbors(enabled);

                    if (!enabled && mapRef.current) {
                      mapRef.current.setFilter("grid-neighbors", [
                        "==", ["get", "cell_id"], "__none__"
                      ]);
                    }
                  }}
                  className="accent-cyan-400"
                />
              </label>

              <div className="mt-4 grid grid-cols-2 gap-2">
                {([4, 8] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setNeighborMode(mode)}
                    className={`rounded-lg p-2 text-sm ${
                      neighborMode === mode
                        ? "bg-cyan-500 text-slate-950"
                        : "bg-white/5"
                    }`}
                  >
                    {mode} neighbors
                  </button>
                ))}
              </div>

              <p className="mt-3 text-xs text-slate-400">
                Selected neighboring cells: {showNeighbors ? selectedNeighborCount : 0}
              </p>
            </div>

            {/* CELL DETAILS */}
            <div className="rounded-xl border border-white/10 bg-[#111e2d] p-4">
              <h3 className="font-semibold">Selected cell</h3>

              {selected ? (
                <div className="mt-4 space-y-3 text-sm">

                  <div>
                    <p className="text-xs text-slate-400">Cell ID</p>
                    <p className="mt-1 break-all font-mono text-cyan-300">
                      {selected.cell_id}
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-xs text-slate-400">Row</p>
                      <p className="font-semibold">{selected.row}</p>
                    </div>

                    <div>
                      <p className="text-xs text-slate-400">Column</p>
                      <p className="font-semibold">{selected.col}</p>
                    </div>
                  </div>

                  <div>
                    <p className="text-xs text-slate-400">Area</p>
                    <p className="font-semibold">
                      {selected.clipped_area_km2.toFixed(3)} km²
                    </p>
                  </div>

                  <div>
                    <p className="text-xs text-slate-400">Coverage</p>
                    <p className="font-semibold">
                      {(selected.coverage_ratio * 100).toFixed(1)}%
                    </p>
                  </div>

                  <div className="rounded-lg bg-black/20 p-3">
                    <p className="text-xs text-amber-300">
                      No environmental data mapped yet.
                    </p>
                  </div>

                  <button
                    onClick={() => setSelected(null)}
                    className="w-full rounded-lg border border-white/10 p-2 hover:bg-white/5"
                  >
                    Clear selection
                  </button>
                </div>
              ) : (
                <p className="mt-3 text-sm leading-6 text-slate-400">
                  Click any grid cell on the satellite map to inspect it.
                </p>
              )}
            </div>

            <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4">
              <p className="text-xs font-semibold text-cyan-300">
                DATA INTEGRITY
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-300">
                This view currently contains geographic grid geometry only.
                No rainfall, elevation, or flood measurements have been
                assigned to individual cells.
              </p>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}
