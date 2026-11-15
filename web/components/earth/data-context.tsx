"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type SourceRecord = Record<string, unknown>;
export type Feature = { type: "Feature"; properties: { cell_id: string; [key: string]: unknown }; geometry: unknown };
export type Grid = { type: "FeatureCollection"; features: Feature[] };
export type Metric = "rainfall" | "rain12h" | "elevation" | "slope" | "riverDistance" | "riverLength" | "vulnerability" | "population" | "upstream" | "flood";

export const metricMeta: Record<Metric, { label: string; short: string; unit: string; colors: [number,string][]; source: string }> = {
  rainfall: { label: "August rainfall", short: "Monthly rainfall", unit: "mm", source: "NASA GPM IMERG Final V07", colors: [[0,"#183f62"],[100,"#3078ad"],[250,"#45a8bb"],[400,"#d0c66a"],[650,"#dd925e"],[1000,"#b9566b"]] },
  rain12h: { label: "12-hour rainfall", short: "12-hour rainfall", unit: "mm", source: "NASA GPM IMERG Final V07", colors: [[0,"#183f62"],[2,"#3078ad"],[10,"#45a8bb"],[25,"#d0c66a"],[50,"#dd925e"],[100,"#b9566b"]] },
  elevation: { label: "Mean elevation", short: "Elevation", unit: "m", source: "NASADEM", colors: [[-50,"#286d8e"],[0,"#58a4a5"],[100,"#a2be85"],[500,"#d2ba80"],[1500,"#a78873"],[3000,"#e1d6c5"]] },
  slope: { label: "Mean slope", short: "Slope", unit: "°", source: "NASADEM", colors: [[0,"#28677b"],[1,"#51a6a5"],[3,"#a9c18a"],[8,"#d4bf7d"],[15,"#ce9467"],[35,"#ae6475"]] },
  riverDistance: { label: "Nearest mapped river", short: "River distance", unit: "km", source: "HydroRIVERS / HydroSHEDS", colors: [[0,"#3ca6c1"],[1,"#65bac0"],[5,"#9fbd93"],[20,"#d8bd84"],[80,"#d09870"],[160,"#987184"]] },
  riverLength: { label: "Mapped river length", short: "River length", unit: "km", source: "HydroRIVERS / HydroSHEDS", colors: [[0,"#26465e"],[1,"#327c9d"],[5,"#56aeb2"],[15,"#b3bb83"],[30,"#d3a373"],[60,"#ab6575"]] },
  vulnerability: { label: "Retrospective vulnerability indicator", short: "Vulnerability", unit: "/100", source: "Preliminary Earth Detective indicator", colors: [[0,"#26566d"],[20,"#4b9a9e"],[40,"#92b598"],[60,"#cebb81"],[80,"#d38d66"],[100,"#ad6071"]] },
  population: { label: "Estimated population (2020)", short: "Population", unit: "people", source: "WorldPop 2020", colors: [[0,"#26465e"],[100,"#337b9d"],[1000,"#56a9ae"],[10000,"#c7b886"],[50000,"#cf966c"],[100000,"#a65c70"]] },
  upstream: { label: "Upstream contributing area", short: "Upstream area", unit: "ha", source: "HydroSHEDS", colors: [[0,"#26465e"],[1000,"#337b9d"],[10000,"#56a9ae"],[100000,"#c7b886"],[1000000,"#cf966c"],[10000000,"#a65c70"]] },
  flood: { label: "Mapped flood fraction", short: "Observed flood", unit: "% of cell", source: "UNOSAT (if verified and provided)", colors: [[0,"#26465e"],[1,"#337b9d"],[10,"#56a9ae"],[30,"#c7b886"],[60,"#cf966c"],[100,"#a65c70"]] },
};

type Frame = { url: string; label: string };
export type DataBundle = {
  grid: Grid;
  cellIds: string[];
  byId: Map<string, number>;
  rainfall: Map<string, number | null>;
  terrain: Map<string, SourceRecord>;
  hydrology: Map<string, SourceRecord>;
  advanced: Map<string, SourceRecord>;
  frames: Frame[];
  report: SourceRecord | null;
};

type State = {
  data: DataBundle | null;
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  setSelectedId: (v: string | null) => void;
  metric: Metric;
  setMetric: (v: Metric) => void;
  frameIndex: number;
  setFrameIndex: (v: number | ((previous: number) => number)) => void;
  frameValues: Map<string, number | null> | null;
  frameLoading: boolean;
  frameError: string | null;
  getValue: (cellId: string, m: Metric) => number | null;
  available: (m: Metric) => boolean;
};

const Context = createContext<State | null>(null);
function record(v: unknown): SourceRecord | null { return v && typeof v === "object" && !Array.isArray(v) ? v as SourceRecord : null; }
function array(v: unknown): unknown[] | null { return Array.isArray(v) ? v : null; }
export function number(v: unknown): number | null { return typeof v === "number" && Number.isFinite(v) ? v : null; }
export function pick(r: SourceRecord | undefined | null, ...keys: string[]): unknown {
  for (const key of keys) if (r && Object.prototype.hasOwnProperty.call(r,key)) return r[key];
  return undefined;
}
export function formatNumber(value: number | null | undefined, decimals = 1): string {
  return value == null || !Number.isFinite(value) ? "Unavailable" : value.toLocaleString("en-US", { maximumFractionDigits: decimals });
}
export function getNeighbors(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value !== "string") return [];
  try { const result: unknown = JSON.parse(value); return Array.isArray(result) ? result.map(String) : []; } catch { return []; }
}
async function fetchRequired(path: string): Promise<unknown> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Required data missing: ${path} (${response.status}). Do not replace with mock data.`);
  return response.json();
}
async function fetchOptional(path: string): Promise<unknown | null> {
  try { const response = await fetch(path); return response.ok ? await response.json() : null; } catch { return null; }
}
function keyedRows(payload: unknown): Map<string, SourceRecord> {
  const obj = record(payload);
  const rows = array(payload) ?? array(pick(obj,"cells","records","data"));
  if (rows) {
    const out = new Map<string,SourceRecord>();
    for (const row of rows) { const r = record(row); if (r && r.cell_id != null) out.set(String(r.cell_id),r); }
    return out;
  }
  const out = new Map<string,SourceRecord>();
  if (obj) for (const [id,v] of Object.entries(obj)) { const r=record(v); if (r) out.set(id,{cell_id:id,...r}); }
  return out;
}
function indexedValues(payload: unknown, ids: string[], label: string): Map<string,number|null> {
  const obj = record(payload);
  const vals = array(payload) ?? array(pick(obj,"valuesMm","values_mm","values","monthly_total_mm"));
  if (vals) {
    if (vals.length !== ids.length) throw new Error(`${label}: expected ${ids.length} values; found ${vals.length}.`);
    if (vals.length && record(vals[0])?.cell_id != null) {
      const rows=keyedRows(vals);
      if (!ids.every(id=>rows.has(id))) throw new Error(`${label}: per-cell records do not match cell index.`);
      return new Map(ids.map(id=>[id,number(pick(rows.get(id),"rainfall_mm","monthly_total_mm","total_mm","value","rainfall_12h_mm"))]));
    }
    return new Map(ids.map((id,i)=>[id,number(vals[i])]));
  }
  const rows = keyedRows(payload);
  if (rows.size) return new Map(ids.map(id=>[id,number(pick(rows.get(id),"rainfall_mm","monthly_total_mm","total_mm","value"))]));
  throw new Error(`Cannot recognize ${label} schema. Source was not substituted.`);
}
function frameList(payload: unknown): Frame[] {
  const raw = array(pick(record(payload),"frames"));
  if (!raw) return [];
  return raw.flatMap((item,i) => {
    const r = record(item);
    const urlValue = pick(r,"url","data_url","path","filename","file");
    if (typeof urlValue !== "string" || !urlValue) return [];
    const url = urlValue.startsWith("/") ? urlValue : urlValue.startsWith("data/") ? `/${urlValue}` : `/data/rainfall/frames/${urlValue.split(/[\\/]/).pop()}`;
    const start = pick(r,"startUtc","start_utc","start","time_start");
    const end = pick(r,"endUtc","end_utc","end","time_end");
    return [{ url, label: start ? `${String(start)}${end ? ` – ${String(end)}` : ""}` : `Frame ${i+1}` }];
  });
}

export function EarthDataProvider({children}:{children:React.ReactNode}) {
  const [data,setData] = useState<DataBundle|null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState<string|null>(null);
  const [selectedId,setSelectedId] = useState<string|null>(null);
  const [metric,setMetric] = useState<Metric>("rainfall");
  const [frameIndex,setFrameIndex] = useState(0);
  const [frameValues,setFrameValues] = useState<Map<string,number|null>|null>(null);
  const [frameLoading,setFrameLoading] = useState(false);
  const [frameError,setFrameError] = useState<string|null>(null);

  useEffect(()=>{
    let cancelled=false;
    (async()=>{
      try {
        const [geoRaw,indexRaw,monthlyRaw,terrainRaw,hydroRaw,advancedRaw,manifestRaw,reportRaw]=await Promise.all([
          fetchRequired("/data/grids/sindh_study_window_grid_5km.geojson"),
          fetchRequired("/data/rainfall/cell_index.json"),
          fetchRequired("/data/rainfall/monthly_total_mm.json"),
          fetchRequired("/data/terrain/terrain_by_cell.json"),
          fetchRequired("/data/hydrology/river_by_cell.json"),
          fetchOptional("/data/analysis/advanced_by_cell.json"),
          fetchOptional("/data/rainfall/manifest.json"),
          fetchOptional("/data/analysis/status.json"),
        ]);
        const grid=geoRaw as Grid;
        if (grid?.type!=="FeatureCollection" || !Array.isArray(grid.features) || !grid.features.length) throw new Error("Invalid Universal Grid GeoJSON.");
        const idxObj=record(indexRaw);
        const rawIds=array(indexRaw) ?? array(pick(idxObj,"cellIds","cell_ids","ids"));
        if (!rawIds) throw new Error("Rainfall cell_index.json has an unrecognized schema.");
        const cellIds=rawIds.map(item=>String(record(item)?.cell_id ?? item));
        const gridIds=grid.features.map(f=>String(f.properties?.cell_id));
        const unique=new Set(gridIds);
        const sourceIds=new Set(cellIds);
        if (unique.size!==gridIds.length || cellIds.length!==gridIds.length || sourceIds.size!==cellIds.length || !gridIds.every(id=>sourceIds.has(id))) throw new Error("Grid / rainfall cell_id integrity check failed.");
        const rainfall=indexedValues(monthlyRaw,cellIds,"August rainfall");
        const terrain=keyedRows(terrainRaw),hydrology=keyedRows(hydroRaw),advanced=advancedRaw ? keyedRows(advancedRaw) : new Map<string,SourceRecord>();
        if (terrain.size!==gridIds.length || hydrology.size!==gridIds.length || !gridIds.every(id=>terrain.has(id)&&hydrology.has(id))) throw new Error(`Environmental data integrity mismatch. Grid ${gridIds.length}; terrain ${terrain.size}; hydrology ${hydrology.size}.`);
        if (advanced.size && (advanced.size!==gridIds.length || !gridIds.every(id=>advanced.has(id)))) throw new Error("Advanced cell IDs do not match the original grid.");
        if (!cancelled) setData({grid,cellIds,byId:new Map(cellIds.map((id,i)=>[id,i])),rainfall,terrain,hydrology,advanced,frames:frameList(manifestRaw),report:record(reportRaw)});
      } catch(e) {if (!cancelled) setError(e instanceof Error?e.message:String(e));}
      finally {if (!cancelled) setLoading(false);}
    })();
    return ()=>{cancelled=true;};
  },[]);

  useEffect(()=>{
    if (!data || metric!=="rain12h" || !data.frames.length) return;
    let cancelled=false;
    const entry=data.frames[frameIndex];
    if (!entry) return;
    setFrameLoading(true);setFrameError(null);setFrameValues(null);
    fetchRequired(entry.url).then(payload=>{
      const values=indexedValues(payload,data.cellIds,`Rainfall frame ${frameIndex+1}`);
      if (!cancelled) setFrameValues(values);
    }).catch(e=>{if (!cancelled) setFrameError(e instanceof Error?e.message:String(e));})
      .finally(()=>{if(!cancelled)setFrameLoading(false);});
    return ()=>{cancelled=true;};
  },[data,metric,frameIndex]);

  const getValue=useCallback((id:string,m:Metric):number|null=>{
    if (!data) return null;
    const t=data.terrain.get(id),h=data.hydrology.get(id),a=data.advanced.get(id);
    switch(m) {
      case "rainfall": return data.rainfall.get(id) ?? null;
      case "rain12h": return frameValues?.get(id) ?? null;
      case "elevation": return number(pick(t,"mean_elevation_m","elevation_mean_m","elevation_m","elevation_mean"));
      case "slope": return number(pick(t,"mean_slope_deg","slope_mean_deg","slope_deg","slope_mean"));
      case "riverDistance": return number(pick(h,"nearest_river_distance_km","nearest_river_km"));
      case "riverLength": return number(pick(h,"river_length_km"));
      case "vulnerability": return number(pick(a,"preliminary_vulnerability_score"));
      case "population": return number(pick(a,"estimated_population_2020"));
      case "upstream": return number(pick(a,"upstream_area_ha"));
      case "flood": {const value=number(pick(a,"mapped_flood_fraction_of_cell"));return value===null?null:value*100;}
    }
  },[data,frameValues]);

  const available=useCallback((m:Metric)=>{
    if (!data) return false;
    if (m==="rain12h")return data.frames.length>0;
    if (["vulnerability","population","upstream","flood"].includes(m)) return [...data.advanced.keys()].some(id=>getValue(id,m)!==null);
    return true;
  },[data,getValue]);

  const value=useMemo<State>(()=>({data,loading,error,selectedId,setSelectedId,metric,setMetric,frameIndex,setFrameIndex,frameValues,frameLoading,frameError,getValue,available}),[data,loading,error,selectedId,metric,frameIndex,frameValues,frameLoading,frameError,getValue,available]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useEarth():State {const ctx=useContext(Context);if(!ctx)throw new Error("useEarth requires EarthDataProvider");return ctx;}
