"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { gsap } from "gsap";
import {
  Activity, ArrowRight, BadgeInfo, Check, ChevronDown, CloudRain, Database,
  Droplets, Earth, ExternalLink, Layers3, MapPinned, Menu, Mountain,
  Play, Pause, Search, ShieldCheck, SlidersHorizontal, Waves, X,
} from "lucide-react";
import MissionMap from "./mission-map";
import { formatNumber, Metric, metricMeta, useEarth } from "./data-context";

type Group = "Rainfall" | "Terrain" | "Hydrology" | "Analysis";
const metricGroups: Record<Group, { metric: Metric; caption: string }[]> = {
  Rainfall: [
    { metric: "rainfall", caption: "Total accumulated rainfall · Aug 2022" },
    { metric: "rain12h", caption: "62 observed twelve-hour periods" },
  ],
  Terrain: [
    { metric: "elevation", caption: "NASADEM · mean land elevation" },
    { metric: "slope", caption: "NASADEM · mean slope" },
  ],
  Hydrology: [
    { metric: "riverDistance", caption: "Nearest mapped HydroRIVERS channel" },
    { metric: "riverLength", caption: "Mapped channel length within each cell" },
    { metric: "upstream", caption: "HydroSHEDS · if processed" },
  ],
  Analysis: [
    { metric: "vulnerability", caption: "Preliminary relative indicator · if processed" },
    { metric: "flood", caption: "Observed flood fraction · if verified" },
    { metric: "population", caption: "2020 estimated population · if processed" },
  ],
};
const tabs: { label: string; href: string }[] = [
  { label: "Dashboard", href: "/" },
  { label: "Detailed analysis", href: "/details" },
  { label: "Vulnerability", href: "/vulnerability" },
  { label: "Grid explorer", href: "/explore" },
  { label: "Sources", href: "/sources" },
];

function MetricReadout({ title, value, unit, icon: Icon }: { title: string; value: number | null | undefined; unit: string; icon: typeof CloudRain }) {
  return <div className="mc-readout"><span className="mc-readout-icon"><Icon size={16} strokeWidth={1.6}/></span><div className="mc-readout-main"><span>{title}</span><strong>{formatNumber(value, 2)} <small>{value == null ? "" : unit}</small></strong></div></div>;
}

function RegionalBars({ values }: { values: number[] }) {
  const bins = useMemo(() => {
    if (values.length === 0) return [];
    const min = Math.min(...values), max = Math.max(...values), step = (max - min) / 20 || 1;
    const bins = Array.from({ length: 20 }, () => 0);
    values.forEach(v => { const at = Math.min(19, Math.max(0, Math.floor((v - min) / step))); bins[at]++; });
    const peak = Math.max(...bins, 1);
    return bins.map((value, i) => ({ height: Math.max(4, value / peak * 100), count: value, index: i }));
  }, [values]);
  if (!bins.length) return <p className="mc-empty">Rainfall distribution unavailable until data loads.</p>;
  return <div className="mc-histogram" role="img" aria-label="Distribution of actual August rainfall values across study grid cells">
    {bins.map(b => <div key={b.index} title={`${b.count.toLocaleString()} cells`} className="mc-histogram-slot"><span style={{ height: `${b.height}%` }}/></div>)}
  </div>;
}

export default function MissionControl() {
  const { data, loading, error, metric, setMetric, getValue, available, selectedId, setSelectedId, frameIndex, setFrameIndex, frameLoading, frameError } = useEarth();
  const container = useRef<HTMLDivElement>(null);
  const [group, setGroup] = useState<Group>("Rainfall");
  const [overlay, setOverlay] = useState(true);
  const [opacity, setOpacity] = useState(36);
  const [playing, setPlaying] = useState(false);
  const [search, setSearch] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [leftOpen, setLeftOpen] = useState(false);

  useEffect(() => {
    const node = container.current;
    if (!node || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const ctx = gsap.context(() => {
      gsap.fromTo("[data-mc-reveal]", { y: 14, opacity: 0 }, { y: 0, opacity: 1, duration: 0.56, stagger: 0.09, ease: "power2.out", clearProps: "transform,opacity" });
    }, node);
    return () => ctx.revert();
  }, []);

  const frameCount = data?.frames.length ?? 0;
  useEffect(() => {
    if (!playing || metric !== "rain12h" || frameCount === 0) return;
    const timer = window.setInterval(() => setFrameIndex(v => (v + 1) % frameCount), 1700);
    return () => window.clearInterval(timer);
  }, [playing, metric, frameCount, setFrameIndex]);

  useEffect(() => {
    if (metric === "rainfall" || metric === "rain12h") setGroup("Rainfall");
    else if (metric === "elevation" || metric === "slope") setGroup("Terrain");
    else if (metric === "riverDistance" || metric === "riverLength" || metric === "upstream") setGroup("Hydrology");
    else setGroup("Analysis");
  }, [metric]);

  const selected = useMemo(() => data?.grid.features.find(f => f.properties.cell_id === selectedId)?.properties, [data, selectedId]);
  const rainfallValues = useMemo(() => (data?.cellIds ?? []).map(id => getValue(id, "rainfall")).filter((v): v is number => v !== null), [data, getValue]);
  const rainfallMean = useMemo(() => {
    if (!data) return null;
    let weighted = 0, area = 0;
    for (const feature of data.grid.features) {
      const weight = feature.properties.clipped_area_km2;
      const val = getValue(feature.properties.cell_id, "rainfall");
      if (typeof weight === "number" && weight > 0 && val !== null) { weighted += val * weight; area += weight; }
    }
    return area > 0 ? weighted / area : null;
  }, [data, getValue]);
  const regionalMeans = useMemo(() => {
    const ids = data?.cellIds ?? [];
    const avg = (key: Metric) => {
      let sum = 0, count = 0;
      for (const id of ids) {
        const value = getValue(id, key);
        if (value !== null) { sum += value; count++; }
      }
      return count > 0 ? sum / count : null;
    };
    return { elevation: avg("elevation"), slope: avg("slope"), riverDistance: avg("riverDistance") };
  }, [data, getValue]);
  const riverCount = useMemo(() => {
    if (!data) return null;
    return data.cellIds.filter(id => (getValue(id, "riverLength") ?? 0) > 0).length;
  }, [data, getValue]);
  const measured = useMemo(() => (data?.cellIds ?? []).filter(id => getValue(id, metric) !== null).length, [data, getValue, metric]);
  const validSearch = !!data?.byId.has(search.trim());
  const pickCell = () => { if (!validSearch) return; setSelectedId(search.trim()); setSearch(""); setLeftOpen(true); };
  const isSelected = !!selectedId && !!selected;
  const classes = `mc-app ${layersOpen ? "mc-right-open" : ""} ${leftOpen ? "mc-left-open" : ""}`;

  return <div ref={container} className={classes}>
    <header className="mc-header">
      <Link href="/" className="mc-brand" aria-label="Earth Detective homepage"><span className="mc-symbol"><Earth size={23} strokeWidth={1.5}/></span><strong>EARTH <span>DETECTIVE</span></strong><small>SPATIAL INTELLIGENCE</small></Link>
      <nav className={`mc-nav ${menuOpen ? "is-open" : ""}`} aria-label="Main pages">
        {tabs.map(t => <Link key={t.href} href={t.href} onClick={() => setMenuOpen(false)} className={t.href === "/" ? "is-current" : ""} aria-current={t.href === "/" ? "page" : undefined}>{t.label}</Link>)}
      </nav>
      <div className="mc-header-actions"><span className="mc-live-indicator"><span className="mc-pulse"/> LIVE DATA VIEW</span><Link className="mc-method-link" href="/sources"><ShieldCheck size={15}/> Sources</Link><button type="button" className="mc-mobile-nav-trigger" onClick={() => setMenuOpen(v => !v)} aria-label={menuOpen ? "Close navigation" : "Open navigation"}>{menuOpen ? <X size={19}/> : <Menu size={19}/>}</button></div>
    </header>

    <div className="mc-body">
      <aside className="mc-left" aria-label="Environmental measurements" data-mc-reveal>
        <div className="mc-region"><div><span className="mc-region-icon"><MapPinned size={18}/></span><span><strong>Sindh study window</strong><small>Pakistan · August 2022</small></span></div><ChevronDown size={15} className="mc-dim"/></div>
        <div className="mc-left-scroll">
          <section className="mc-left-block mc-selected-context">
            <div className="mc-overline">CURRENT SELECTION</div>
            <h2>{isSelected ? "Selected grid cell" : "Study region"}</h2>
            <div className="mc-context-id">{isSelected ? selectedId : "12,412 cell analysis grid"}</div>
            <div className="mc-context-secondary">{isSelected ? `Row ${String(selected?.row ?? "—")} · Column ${String(selected?.col ?? "—")}` : "5 km grid · 66.0–71.5°E · 23.5–28.5°N"}</div>
          </section>
          <section className="mc-left-block">
            <div className="mc-section-row"><div className="mc-overline">OBSERVED MEASUREMENTS</div><BadgeInfo size={14} className="mc-dim"/></div>
            <MetricReadout title={isSelected ? "August rainfall" : "Region average rainfall"} value={isSelected && selectedId ? getValue(selectedId, "rainfall") : rainfallMean} unit="mm" icon={CloudRain}/>
            <MetricReadout title={isSelected ? "Mean cell elevation" : "Mean grid-cell elevation"} value={isSelected && selectedId ? getValue(selectedId, "elevation") : regionalMeans.elevation} unit="m" icon={Mountain}/>
            <MetricReadout title={isSelected ? "Mean cell slope" : "Mean grid-cell slope"} value={isSelected && selectedId ? getValue(selectedId, "slope") : regionalMeans.slope} unit="°" icon={Activity}/>
            <MetricReadout title={isSelected ? "Nearest mapped river" : "Mean river distance"} value={isSelected && selectedId ? getValue(selectedId, "riverDistance") : regionalMeans.riverDistance} unit="km" icon={Waves}/>
            {!selectedId && <p className="mc-hint">Select a cell on the map to inspect its local terrain and river measurements.</p>}
          </section>
          <section className="mc-left-block">
            <div className="mc-overline">AREA INSIGHTS</div>
            <div className="mc-mini-grid"><div><span>GRID CELLS</span><strong>{formatNumber(data?.grid.features.length, 0)}</strong></div><div><span>RIVER CELLS</span><strong>{formatNumber(riverCount, 0)}</strong></div><div><span>TIME FRAMES</span><strong>{formatNumber(frameCount, 0)}</strong></div><div><span>ACTIVE LAYER DATA</span><strong>{formatNumber(measured, 0)}</strong></div></div>
          </section>
          <section className="mc-left-block mc-hist-section">
            <div className="mc-section-row"><div><div className="mc-overline">RAINFALL DISTRIBUTION</div><p>Across measured August 2022 cells</p></div><Droplets size={15} className="mc-dim"/></div>
            <RegionalBars values={rainfallValues}/>
            <div className="mc-chart-scale"><span>LOWER TOTALS</span><span>HIGHER TOTALS</span></div>
            <p className="mc-chart-caption">Observed GPM IMERG totals aggregated to the 5 km analysis grid.</p>
          </section>
          <section className="mc-left-block mc-left-bottom">
            <div className="mc-section-row"><span className="mc-overline">DATA QUALITY</span><span className="mc-ok"><Check size={13}/> VERIFIED</span></div>
            <p>12,412 river distances spatially verified. Missing NASADEM land measurements remain null, not zero.</p>
            <Link href="/sources" className="mc-inline-link">Read scientific methods <ArrowRight size={14}/></Link>
          </section>
        </div>
      </aside>

      <section className="mc-center" aria-label="Interactive geographic map" data-mc-reveal>
        <MissionMap metric={metric} overlay={overlay} opacity={opacity}/>
        <div className="mc-center-top"><span><span className="mc-pulse"/> MAP EXPLORER</span><strong>{metricMeta[metric].label}</strong></div>
        <button type="button" className="mc-show-left" onClick={() => setLeftOpen(v => !v)}><Activity size={16}/> Measurements</button>
        <button type="button" className="mc-show-right" onClick={() => setLayersOpen(v => !v)}><Layers3 size={16}/> Map layers</button>
        {error && <div className="mc-data-error" role="alert"><BadgeInfo size={16}/>{error}</div>}
        {!error && loading && <span className="mc-data-loading" role="status">Reading processed sources…</span>}
      </section>

      <aside className="mc-right" aria-label="Map layers and sources" data-mc-reveal>
        <div className="mc-right-heading"><div><span className="mc-overline">SATELLITE ANALYSIS</span><h2>Map layers &amp; data</h2></div><button type="button" className="mc-close-right" aria-label="Close layers panel" onClick={() => setLayersOpen(false)}><X size={19}/></button></div>
        <div className="mc-layer-tabs" role="tablist" aria-label="Data categories">
          {(Object.keys(metricGroups) as Group[]).map(name => <button type="button" role="tab" aria-selected={group === name} key={name} title={name} onClick={() => setGroup(name)} className={group === name ? "is-active" : ""}>{name === "Rainfall" ? <CloudRain size={19}/> : name === "Terrain" ? <Mountain size={19}/> : name === "Hydrology" ? <Waves size={19}/> : <SlidersHorizontal size={19}/>}<span>{name}</span></button>)}
        </div>
        <div className="mc-right-scroll">
          <form className="mc-cell-search" onSubmit={(e: React.FormEvent<HTMLFormElement>) => { e.preventDefault(); pickCell(); }}><Search size={17}/><input aria-label="Find exact cell ID" placeholder="Find grid cell ID…" value={search} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}/><button type="submit" disabled={!validSearch} aria-label="Select cell"><ArrowRight size={16}/></button></form>
          <div className="mc-layer-group"><div className="mc-section-row"><div><div className="mc-overline">{group.toUpperCase()} DATA</div><p>{group === "Rainfall" ? "NASA GPM IMERG Final V07" : group === "Terrain" ? "NASADEM terrain products" : group === "Hydrology" ? "HydroRIVERS / HydroSHEDS" : "Validated outputs where available"}</p></div><span className="mc-list-count">{metricGroups[group].length} LAYERS</span></div>
            <div className="mc-layer-list">
              {metricGroups[group].map(item => {
                const enabled = available(item.metric);
                const active = metric === item.metric;
                return <button type="button" key={item.metric} disabled={!enabled} className={`mc-layer-item ${active ? "is-active" : ""}`} onClick={() => { setMetric(item.metric); setLayersOpen(false); }} aria-pressed={active}>
                  <span className={`mc-layer-state ${active ? "active" : enabled ? "ready" : "pending"}`}>{active ? <Check size={13}/> : enabled ? <span/> : <span className="mc-pending-dot"/>}</span>
                  <span className="mc-layer-copy"><strong>{metricMeta[item.metric].label}</strong><small>{item.caption}</small></span>
                  <span className="mc-layer-tag">{enabled ? metricMeta[item.metric].unit : "Pending"}</span>
                </button>;
              })}
            </div>
          </div>
          {metric === "rain12h" && frameCount > 0 && <div className="mc-options-block"><div className="mc-section-row"><span className="mc-overline">12-HOUR OBSERVATIONS</span><span className="mc-frame-num">{frameIndex + 1} / {frameCount}</span></div><div className="mc-player"><button type="button" onClick={() => setPlaying(v => !v)} aria-label={playing ? "Pause rainfall playback" : "Play rainfall playback"}>{playing ? <Pause size={16}/> : <Play size={16}/>}</button><input type="range" min="0" max={frameCount - 1} value={frameIndex} onChange={(e: React.ChangeEvent<HTMLInputElement>) => { setFrameIndex(Number(e.target.value)); setPlaying(false); }} aria-label="Rainfall observation frame"/></div><p className="mc-frame-time">{data?.frames[frameIndex]?.label ?? "Not available"}{frameLoading ? " · loading" : ""}</p>{frameError && <p className="mc-inline-error">{frameError}</p>}</div>}
          <div className="mc-options-block"><div className="mc-overline">DISPLAY OPTIONS</div><div className="mc-option-row"><label htmlFor="mc-overlay">Show measurement overlay</label><button id="mc-overlay" type="button" role="switch" aria-checked={overlay} onClick={() => setOverlay(v => !v)} className={`mc-switch ${overlay ? "is-on" : ""}`}><span/></button></div><label className="mc-opacity-label" htmlFor="mc-opacity">Overlay opacity <strong>{opacity}%</strong></label><input id="mc-opacity" className="mc-opacity-slider" type="range" min="10" max="90" value={opacity} disabled={!overlay} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpacity(Number(e.target.value))}/></div>
          <div className="mc-options-block"><div className="mc-overline">SELECTED VALUE</div>{selectedId ? <div className="mc-selected-readout"><div><span>{selectedId}</span><button type="button" onClick={() => setSelectedId(null)}>Clear</button></div><strong>{formatNumber(getValue(selectedId, metric), 2)} <small>{metricMeta[metric].unit}</small></strong><p>Cell-level value from the processed dataset</p></div> : <p className="mc-empty">Click any grid cell to view its actual measurement here.</p>}</div>
          <div className="mc-options-block mc-data-legend"><div className="mc-overline">DATA PROVENANCE</div><div><Database size={16}/><p><strong>{metricMeta[metric].source}</strong><span>Source-backed metric; not a flood forecast</span></p></div><Link href="/sources">Methods &amp; limitations <ExternalLink size={13}/></Link></div>
        </div>
      </aside>
    </div>
    <footer className="mc-bottom-bar"><span><span className="mc-pulse"/> Earth Detective · NASA Space Apps 2026</span><span>{selectedId ? `SELECTED ${selectedId}` : "CLICK A CELL TO INVESTIGATE"}</span><span>Historical environmental assessment · no forecast claim</span></footer>
  </div>;
}
