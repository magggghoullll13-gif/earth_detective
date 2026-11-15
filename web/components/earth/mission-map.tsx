"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Expand, Focus, Layers2, Minus, Plus } from "lucide-react";
import { Metric, formatNumber, metricMeta, useEarth } from "./data-context";

const BOUNDS: [[number, number], [number, number]] = [[66, 23.5], [71.5, 28.5]];

export default function MissionMap({ metric, overlay, opacity }: { metric: Metric; overlay: boolean; opacity: number }) {
  const { data, getValue, selectedId, setSelectedId } = useEarth();
  const root = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const geo = useMemo(() => data ? {
    type: "FeatureCollection" as const,
    features: data.grid.features.map(feature => ({
      ...feature,
      properties: { ...feature.properties, metric_value: getValue(feature.properties.cell_id, metric) },
    })),
  } : null, [data, getValue, metric]);

  useEffect(() => {
    if (!data || !root.current) return;
    let cancelled = false;
    let map: any;
    (async () => {
      try {
        const lib = await import("maplibre-gl");
        if (cancelled || !root.current) return;
        const worker = await fetch("/maplibre-gl-worker.mjs", { method: "HEAD" }).catch(() => null);
        if (worker?.ok) lib.setWorkerUrl("/maplibre-gl-worker.mjs");
        if (cancelled || !root.current) return;
        map = new lib.Map({
          container: root.current,
          center: [68.75, 26], zoom: 6.4,
          maxZoom: 17,
          renderWorldCopies: false,
          attributionControl: false,
          style: {
            version: 8,
            sources: {
              imagery: {
                type: "raster",
                tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
                tileSize: 256,
                attribution: "Satellite imagery © Esri and contributors",
              },
            },
            layers: [{ id: "imagery", source: "imagery", type: "raster" }],
          } as any,
        });
        mapRef.current = map;
        map.on("load", () => {
          if (cancelled) return;
          map.addSource("real-cells", { type: "geojson", data: data.grid as any });
          map.addLayer({ id: "real-values", type: "fill", source: "real-cells", paint: { "fill-color": "#4d6770", "fill-opacity": 0.32 } });
          map.addLayer({ id: "cell-lines", type: "line", source: "real-cells", paint: { "line-color": "#eee7d6", "line-opacity": 0.22, "line-width": 0.4 } });
          map.addLayer({ id: "selected-area", type: "line", source: "real-cells", filter: ["==", ["get", "cell_id"], "__none__"], paint: { "line-color": "#fff8e8", "line-width": 2.6, "line-opacity": 1 } });
          map.on("click", "real-values", (ev: any) => {
            const id = ev.features?.[0]?.properties?.cell_id;
            if (typeof id === "string") setSelectedId(id);
          });
          map.on("mouseenter", "real-values", () => { map.getCanvas().style.cursor = "crosshair"; });
          map.on("mouseleave", "real-values", () => { map.getCanvas().style.cursor = ""; });
          map.fitBounds(BOUNDS, { padding: 32, duration: 0 });
          setReady(true);
        });
        map.on("error", (e: any) => console.warn("Map tile / source error", e.error));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; map?.remove(); mapRef.current = null; setReady(false); };
  }, [data, setSelectedId]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !geo) return;
    void map.getSource("real-cells")?.setData(geo as any);
    map.setPaintProperty("real-values", "fill-color", [
      "case", ["==", ["get", "metric_value"], null], "#46515a",
      ["interpolate", ["linear"], ["get", "metric_value"], ...metricMeta[metric].colors.flatMap(([n, color]) => [n, color])],
    ]);
  }, [ready, geo, metric]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    // Keep an almost invisible fill so cells remain clickable when the color overlay is off.
    map.setPaintProperty("real-values", "fill-opacity", overlay ? opacity / 100 : 0.005);
    map.setPaintProperty("cell-lines", "line-opacity", overlay ? 0.28 : 0.08);
  }, [ready, overlay, opacity]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("selected-area", ["==", ["get", "cell_id"], selectedId ?? "__none__"]);
  }, [ready, selectedId]);

  const colors = metricMeta[metric].colors;
  return <div className="mc-map-frame">
    <div className="mc-map-canvas" ref={root} role="application" aria-label={`Satellite map of Sindh showing ${metricMeta[metric].label} in 5 km cells`} />
    {!ready && !error && <div className="mc-map-overlay" role="status">Loading the scientific grid and satellite imagery…</div>}
    {error && <div className="mc-map-overlay mc-map-error" role="alert">Map could not initialize: {error}</div>}
    <div className="mc-map-coordinate" aria-hidden="true"><span className="mc-pulse"/> SINDH · PAKISTAN <span className="mc-map-separator">/</span> 5 KM GRID</div>
    <div className="mc-map-zoom" aria-label="Map navigation">
      <button type="button" aria-label="Zoom in" onClick={() => mapRef.current?.zoomIn({ duration: 300 })}><Plus size={17}/></button>
      <button type="button" aria-label="Zoom out" onClick={() => mapRef.current?.zoomOut({ duration: 300 })}><Minus size={17}/></button>
      <button type="button" aria-label="Fit the study window" onClick={() => mapRef.current?.fitBounds(BOUNDS, { padding: 32, duration: 500 })}><Expand size={16}/></button>
      <button type="button" disabled={!selectedId} aria-label="Center selected cell" onClick={() => {
        const f = data?.grid.features.find(item => item.properties.cell_id === selectedId);
        const coords = (f?.geometry as { coordinates?: number[][][] })?.coordinates;
        const ring = coords?.[0];
        if (!ring?.length) return;
        const sum = ring.reduce(([x, y], [lon, lat]) => [x + lon, y + lat], [0, 0]);
        mapRef.current?.flyTo({ center: [sum[0] / ring.length, sum[1] / ring.length], zoom: 10, duration: 700 });
      }}><Focus size={16}/></button>
    </div>
    <div className="mc-map-key">
      <div className="mc-map-key-heading"><Layers2 size={14}/><span>{metricMeta[metric].label}</span><strong>{metricMeta[metric].unit}</strong></div>
      <div className="mc-map-key-gradient" style={{ background: `linear-gradient(to right, ${colors.map(([, color]) => color).join(", ")})` }}/>
      <div className="mc-map-key-scale"><span>{formatNumber(colors[0][0], 0)}</span><span>{formatNumber(colors[colors.length - 1][0], 0)}</span></div>
      <div className="mc-map-key-note">Gray = no measurement · color scale is descriptive</div>
    </div>
    <div className="mc-map-attribution">Imagery © Esri · NASA / HydroRIVERS overlays</div>
  </div>;
}
