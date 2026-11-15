"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Activity, ArrowRight, ArrowUpRight, BarChart3, BookOpenText, Check,
  ChevronRight, CircleAlert, CloudRain, Database, Download, Droplets,
  Earth, FileCheck2, Grid2X2, Layers3, Map, Mountain, Play, Pause, Search,
  ShieldCheck, Signal, SlidersHorizontal, Waves,
} from "lucide-react";
import EnvironmentalMap from "./map";
import { Card, CellDetails, DataState, DetailRow, MetricCard, MetricPicker, SectionTitle, SourceLink } from "./ui";
import { formatNumber, getNeighbors, Metric, metricMeta, number, pick, useEarth } from "./data-context";

const BASIC:Metric[]=["rainfall","elevation","slope","riverDistance","riverLength"];
const EXTENDED:Metric[]=[...BASIC,"vulnerability","upstream","population","flood"];

function LoadingSection(){return <div className="ed-loading-card" role="status"><span className="ed-spinner"/> Reading processed environmental data...</div>}
function MissingAdvanced(){return <div className="ed-notice"><CircleAlert size={19}/><div><strong>Advanced analysis is not yet available.</strong><p>Run the existing <code>RUN_ALL.ps1</code> pipeline and check <code>web/public/data/analysis/status.json</code>. We will not invent a vulnerability score, flood observation, or population count.</p></div></div>}
function AreaHint(){return <div className="ed-small-note"><ShieldCheck size={15}/> Study area is the Sindh rectangular window (66.0–71.5°E, 23.5–28.5°N), not the full political province.</div>}
function MetricSynopsis({metric}:{metric:Metric}){
  const {data,getValue}=useEarth();
  const values=useMemo(()=>data?.cellIds.map(id=>getValue(id,metric)).filter((v):v is number=>v!==null)??[],[data,getValue,metric]);
  const sorted=useMemo(()=>[...values].sort((a,b)=>a-b),[values]);
  const mean=values.length?values.reduce((a,b)=>a+b,0)/values.length:null;
  return <div className="ed-metric-synopsis"><div><span>Available cell measurements</span><strong>{formatNumber(values.length,0)} / {formatNumber(data?.grid.features.length,0)}</strong></div><div><span>Cell mean</span><strong>{formatNumber(mean,2)} <small>{metricMeta[metric].unit}</small></strong></div><div><span>Observed range</span><strong>{formatNumber(sorted[0],2)} – {formatNumber(sorted[sorted.length-1],2)}</strong></div></div>;
}
function Distribution({values,unit="mm"}:{values:number[];unit?:string}){
  const bins=useMemo(()=>{
    if(!values.length)return [];
    const min=Math.min(...values),max=Math.max(...values);
    const width=max===min?1:(max-min)/10;
    const counts=Array.from({length:10},()=>0);
    values.forEach(v=>{const index=Math.min(9,Math.max(0,Math.floor((v-min)/width)));counts[index]+=1;});
    return counts.map((count,i)=>({count,label:min+i*width}));
  },[values]);
  const peak=Math.max(1,...bins.map(b=>b.count));
  return <div className="ed-chart"><div className="ed-chart-head"><span>Cell-value distribution</span><small>{formatNumber(values.length,0)} measurements</small></div>
    {bins.length?<><div className="ed-bar-chart" role="img" aria-label={`Histogram of ${values.length} observed cell values in ${unit}`}>
      {bins.map((b,i)=><div key={i} className="ed-bar-column" title={`${formatNumber(b.label,1)} ${unit} or above: ${b.count} cells`}><div className="ed-bar" style={{height:`${Math.max(3,b.count/peak*100)}%`}}/><span>{i%3===0?formatNumber(b.label,0):""}</span></div>)}
    </div><div className="ed-chart-axis"><span>Lower {unit}</span><span>Higher {unit}</span></div></>:<div className="ed-chart-empty">This source has no usable cell values yet.</div>}
  </div>;
}
function RainfallTopCells(){
  const {data,getValue,setSelectedId}=useEarth(),router=useRouter();
  const rows=useMemo(()=>data?.cellIds.map(id=>({id,rain:getValue(id,"rainfall")})).filter((x):x is {id:string;rain:number}=>x.rain!==null).sort((a,b)=>b.rain-a.rain).slice(0,5)??[],[data,getValue]);
  return <div className="ed-top-cell-list">{rows.map((row,i)=><button key={row.id} className="ed-top-cell" onClick={()=>{setSelectedId(row.id);router.push("/explore");}}><span className="ed-top-cell-rank">{String(i+1).padStart(2,"0")}</span><span className="ed-top-cell-name">{row.id}</span><strong>{formatNumber(row.rain,1)} mm</strong><ChevronRight size={15}/></button>)}{!rows.length&&<p className="ed-muted-copy">Rainfall data is still loading.</p>}</div>;
}
export function OverviewPage(){
  const {data,loading,getValue,available}=useEarth();
  const summary=useMemo(()=>{
    if(!data)return null;
    let rainSum=0,area=0,rivers=0,terrain=0;
    for(const feature of data.grid.features){const id=feature.properties.cell_id,rain=getValue(id,"rainfall"),weight=number(feature.properties.clipped_area_km2);
      if(rain!==null&&weight!==null&&weight>0){rainSum+=rain*weight;area+=weight;}
      if(getValue(id,"riverLength")!==null && (getValue(id,"riverLength")??0)>0)rivers++;
      if(getValue(id,"elevation")!==null)terrain++;
    }
    return {mean:area>0?rainSum/area:null,rivers,terrain,count:data.grid.features.length};
  },[data,getValue]);
  const monthlyValues=useMemo(()=>data?.cellIds.map(id=>getValue(id,"rainfall")).filter((v):v is number=>v!==null)??[],[data,getValue]);
  return <>
    <SectionTitle eyebrow="MISSION OVERVIEW" title="Environmental intelligence, grounded in evidence." description="Explore the August 2022 Sindh flood context through NASA rainfall and terrain data, mapped river networks, and transparently labeled analysis." action={<DataState variant={data?"ready":"pending"} name={data?"CORE SOURCES LOADED":loading?"LOADING":"AWAITING DATA"}/>}/>
    <section className="ed-kpi-grid">
      <MetricCard label="5 km analysis cells" value={formatNumber(summary?.count,0)} note="Equal-area processing grid" icon={Layers3}/>
      <MetricCard label="Mean August rainfall" value={formatNumber(summary?.mean,2)} unit="mm" note="Study-area weighted estimate" icon={CloudRain}/>
      <MetricCard label="Cells with mapped rivers" value={formatNumber(summary?.rivers,0)} note="HydroRIVERS segment intersections" icon={Waves}/>
      <MetricCard label="Cells with terrain readings" value={formatNumber(summary?.terrain,0)} note="Excludes water-only / source gaps" icon={Mountain}/>
    </section>
    <section className="ed-overview-grid">
      <Card className="ed-card-map"><div className="ed-card-head ed-card-head--inline"><div><span className="ed-eyebrow">SPATIAL OVERVIEW</span><h2>August 2022 rainfall</h2></div><Link className="ed-inline-action" href="/details">Explore layers <ArrowUpRight size={16}/></Link></div>{data?<EnvironmentalMap metric="rainfall" compact/>:<LoadingSection/>}</Card>
      <div className="ed-side-stack">
        <Card title="What we can demonstrate" kicker="RESEARCH STATUS" icon={FileCheck2}>
          <div className="ed-status-list"><div><span className="ed-status-icon"><Check size={15}/></span><div><strong>NASA GPM IMERG</strong><small>August accumulation & 12-hour observations</small></div></div><div><span className="ed-status-icon"><Check size={15}/></span><div><strong>NASADEM terrain</strong><small>Elevation and slope, source gaps labeled</small></div></div><div><span className="ed-status-icon"><Check size={15}/></span><div><strong>HydroRIVERS network</strong><small>Verified river distances for every cell</small></div></div><div><span className="ed-status-icon is-pending"><CircleAlert size={15}/></span><div><strong>Observed-flood validation</strong><small>{available("flood")?"Mapped flood layer available; verify footprint":"Pending verified flood polygons and assessment footprint"}</small></div></div></div>
          <Link href="/sources" className="ed-card-cta">Review science and limitations <ArrowRight size={15}/></Link>
        </Card>
        <Card title="Project definition" kicker="AOI / METHOD" icon={Earth}><div className="ed-project-fact"><span>Region</span><strong>Sindh study window, Pakistan</strong></div><div className="ed-project-fact"><span>Historical event</span><strong>August 2022</strong></div><div className="ed-project-fact"><span>Spatial unit</span><strong>5 km cells</strong></div><div className="ed-project-fact"><span>Interpretation</span><strong>Retrospective, not a forecast</strong></div></Card>
      </div>
    </section>
    <section className="ed-two-col">
      <Card title="Rainfall distribution" kicker="OBSERVATIONS" icon={BarChart3}><Distribution values={monthlyValues}/></Card>
      <Card title="Highest-rainfall cells" kicker="DATA EXPLORER" icon={Activity}><RainfallTopCells/></Card>
    </section><AreaHint/>
  </>;
}
export function DetailsPage(){
  const {data,loading,metric,setMetric,available}=useEarth();
  useEffect(()=>{if(metric==="rain12h"||!available(metric))setMetric("rainfall");},[]); // initial default for this route
  return <>
    <SectionTitle eyebrow="DETAILED ANALYSIS" title="Every layer. One spatial reference." description="Switch between real rainfall, terrain, river proximity, population, and other available scientific outputs. Click a cell to read its exact attributes."/>
    <div className="ed-workbench"><div className="ed-workbench-main">
      <Card className="ed-selector-card" title="Measurement layer" kicker="DATA CONTROLS" icon={SlidersHorizontal}><MetricPicker current={metric} onChange={setMetric} keys={EXTENDED}/></Card>
      {data?<EnvironmentalMap metric={metric}/>:<LoadingSection/>}
      <Card title="Layer statistics" kicker="CELL COVERAGE" icon={Signal}><MetricSynopsis metric={metric}/></Card>
    </div><aside className="ed-workbench-side"><Card title="Cell details" kicker="LIVE INSPECTOR" icon={Layers3}><CellDetails/></Card><Card title="Measurement provenance" kicker="SCIENTIFIC NOTES" icon={ShieldCheck}><div className="ed-source-note"><strong>{metricMeta[metric].source}</strong><p>{metric==="vulnerability"?"Preliminary event-conditioned relative indicator, not calibrated flood probability.":metric==="flood"?"Mapped flood fraction does not imply non-flood outside a verified assessed footprint.":"Aggregated to the 5 km study grid, preserving original source semantics."}</p></div><Link href="/sources" className="ed-card-cta">Data methods <ArrowRight size={15}/></Link></Card></aside></div>
  </>;
}
export function VulnerabilityPage(){
  const {data,available,metric,setMetric,getValue}=useEarth();
  const enabled=available("vulnerability");
  const scores=useMemo(()=>data?.cellIds.map(id=>getValue(id,"vulnerability")).filter((v):v is number=>v!==null)??[],[data,getValue]);
  useEffect(()=>{setMetric("vulnerability");},[setMetric]);
  return <>
    <SectionTitle eyebrow="FLOOD VULNERABILITY" title="Understand relative vulnerability. Not a prediction." description="A transparent, retrospective indicator that combines real environmental evidence. Historical validation and uncertainty remain explicit." action={<DataState variant={enabled?"ready":"pending"} name={enabled?"PRELIMINARY MODEL AVAILABLE":"MODEL PENDING"}/>}/>
    <div className="ed-notice ed-notice--science"><ShieldCheck size={19}/><div><strong>Interpret this view carefully.</strong><p>The score, if available, uses August 2022 conditions and is a relative, retrospective indicator—not a forecast, calibrated probability, or warning system. Satellite flood observations require an independently verified assessed-area footprint for negative labels.</p></div></div>
    {!enabled?<MissingAdvanced/>:<section className="ed-kpi-grid ed-kpi-grid--three"><MetricCard label="Scored grid cells" value={formatNumber(scores.length,0)} note="Cells with computed preliminary scores" icon={Database}/><MetricCard label="Median indicator" value={formatNumber(scores.length?[...scores].sort((a,b)=>a-b)[Math.floor(scores.length/2)]:null,1)} unit="/ 100" note="Relative within this study window" icon={Activity}/><MetricCard label="Mapped flood observations" value={available("flood")?"Available":"Pending"} note="Not interchangeable with modeled vulnerability" icon={Waves}/></section>}
    <section className="ed-workbench"><div className="ed-workbench-main"><Card title="Vulnerability and observed context" kicker="RETROSPECTIVE STUDY" icon={Map}><MetricPicker current={enabled?metric:"rainfall"} onChange={setMetric} keys={["vulnerability","flood","rainfall","slope","riverDistance"]}/></Card>{data?<EnvironmentalMap metric={enabled?metric:"rainfall"}/>:<LoadingSection/>}</div><aside className="ed-workbench-side"><Card title="Selected cell" kicker="EVIDENCE" icon={Layers3}><CellDetails/></Card><Card title="Validation status" kicker="METHOD CHECK" icon={CircleAlert}><p className="ed-muted-copy">For precision / recall, we need both observed flood polygons and a verified satellite assessment footprint. Outside assessed coverage means unknown, not negative.</p><div className="ed-status-bubbles"><DataState variant={available("flood")?"ready":"pending"} name="Observed extent"/><DataState variant="pending" name="External validation"/></div></Card></aside></section>
    {enabled&&<Card title="Distribution of preliminary scores" kicker="RELATIVE INDICATOR" icon={BarChart3}><Distribution values={scores} unit="score"/></Card>}
  </>;
}
export function ExplorerPage(){
  const {data,selectedId,setSelectedId,metric,setMetric,frameIndex,setFrameIndex,frameLoading,frameError}=useEarth();
  const [playing,setPlaying]=useState(false);const [query,setQuery]=useState("");
  const frames=data?.frames??[];
  useEffect(()=>{if(!playing||frames.length===0)return;const count=frames.length;const timer=window.setInterval(()=>setFrameIndex(i=>(i+1)%count),1600);return ()=>clearInterval(timer);},[playing,frames.length,setFrameIndex]);
  useEffect(()=>{setMetric("rainfall");},[setMetric]);
  const chosen=data?.grid.features.find(f=>f.properties.cell_id===selectedId)?.properties;
  const near=chosen?getNeighbors(chosen.neighbors_8):[];
  return <>
    <SectionTitle eyebrow="GRID EXPLORER" title="Investigate the geography behind every value." description="Search an exact cell ID, inspect its neighbors, and compare historical rainfall frames with terrain and mapped rivers."/>
    <section className="ed-explore-controls" data-animate>
      <form onSubmit={(e:React.FormEvent<HTMLFormElement>)=>{e.preventDefault();const id=query.trim();if(data?.byId.has(id)){setSelectedId(id);setQuery("");}}} className="ed-cell-search"><Search size={17}/><input value={query} onChange={(e:React.ChangeEvent<HTMLInputElement>)=>setQuery(e.target.value)} placeholder="Search a cell_id..." aria-label="Search cell ID"/><button disabled={!data?.byId.has(query.trim())} type="submit">Inspect <ArrowRight size={15}/></button></form>
      <div className="ed-explorer-tabs"><MetricPicker current={metric} onChange={m=>{setMetric(m);if(m!=="rain12h")setPlaying(false);}} keys={["rainfall","rain12h","elevation","slope","riverDistance"]}/></div>
    </section>
    {metric==="rain12h"&&<Card className="ed-timeline" title="GPM IMERG observation timeline" kicker="AUGUST 1–31, 2022" icon={CloudRain}>
      {frames.length?<><div className="ed-timeline-controls"><button className="ed-play-btn" onClick={()=>setPlaying(v=>!v)} aria-label={playing?"Pause rainfall playback":"Play rainfall playback"}>{playing?<Pause size={17}/>:<Play size={17}/>}</button><input type="range" min="0" max={frames.length-1} step="1" value={frameIndex} onChange={(e:React.ChangeEvent<HTMLInputElement>)=>{setPlaying(false);setFrameIndex(Number(e.target.value));}} aria-label="Rainfall frame"/><span>{frameIndex+1} / {frames.length}</span></div><div className="ed-timeline-caption"><span>{frames[frameIndex]?.label}</span><span>{frameLoading?"Reading source...":"Real observations"}</span></div>{frameError&&<p className="ed-inline-error">{frameError}</p>}</>:<p className="ed-muted-copy">No recognizable frame URLs in the local rainfall manifest. Monthly rainfall remains available.</p>}
    </Card>}
    <div className="ed-workbench"><div className="ed-workbench-main">{data?<EnvironmentalMap metric={metric}/>:<LoadingSection/>}</div><aside className="ed-workbench-side"><Card title="Cell inspector" kicker="SELECTED GEOMETRY" icon={Layers3}><CellDetails/></Card><Card title="Neighbor analysis" kicker="SPATIAL CONTEXT" icon={Grid2X2}><div className="ed-project-fact"><span>Selected cell</span><strong>{selectedId??"None"}</strong></div><div className="ed-project-fact"><span>8-connected neighbors</span><strong>{selectedId?near.length:"—"}</strong></div><p className="ed-muted-copy ed-margin-top">Neighbor highlights are geometric adjacency, not a confirmed downstream hydrological connection.</p></Card></aside></div>
  </>;
}
const sources=[
  {title:"NASA GPM IMERG Final V07",label:"PRECIPITATION",url:"https://gpm.nasa.gov/data/imerg",about:"August 2022; 1,488 half-hourly observations aggregated into 62 twelve-hour frames and monthly totals. Native data support is 0.1°; the web grid is not the native pixel footprint."},
  {title:"NASADEM (HGT / SC)",label:"ELEVATION & SLOPE",url:"https://lpdaac.usgs.gov/products/nasadem_hgtv001/",about:"Elevation, slope, and water-mask measurements integrated to the analysis grid. Source gaps, partial source footprints, and water-only cells are separately classified."},
  {title:"HydroRIVERS v1.0 / HydroSHEDS",label:"RIVER NETWORK",url:"https://www.hydrosheds.org/products/hydrorivers",about:"Mapped network proximity and segment length; non-NASA derived network. Nearest distance verified for all cells against an expanded regional network."},
  {title:"HydroSHEDS drainage",label:"OPTIONAL FLOW CONTEXT",url:"https://www.hydrosheds.org/hydrosheds-core-downloads",about:"Optional contributing-area / drainage-direction data, if present in the advanced pipeline. These do not establish flood occurrence."},
  {title:"WorldPop 2020 (Pakistan)",label:"OPTIONAL EXPOSURE",url:"https://hub.worldpop.org/",about:"Model-based population estimate for 2020, not a census of people confirmed affected by the August 2022 event."},
  {title:"UNOSAT historical flood products",label:"OPTIONAL VALIDATION",url:"https://unosat.org/products/3342",about:"Observed water polygons require verified attributes and assessed-area footprints. Unassessed cells cannot be marked flood-free."},
];
export function SourcesPage(){
  const {data,loading,available}=useEarth();
  const reportStages=(data?.report?.stages&&typeof data.report.stages==="object")?data.report.stages as Record<string,unknown>:null;
  return <>
    <SectionTitle eyebrow="SOURCES & METHODOLOGY" title="Trace every measurement back to its source." description="Scientific transparency, provenance, spatial methods, and quality flags are part of the interface—not hidden in the footnotes."/>
    <section className="ed-kpi-grid ed-kpi-grid--three"><MetricCard label="Mapped study cells" value={formatNumber(data?.grid.features.length,0)} note="Stable cell_id across all layers" icon={Layers3}/><MetricCard label="Rainfall time frames" value={formatNumber(data?.frames.length,0)} note="If recognized from the manifest" icon={CloudRain}/><MetricCard label="Advanced datasets" value={data?.advanced.size?"Integrated":"Optional"} note="Only published when real values exist" icon={FileCheck2}/></section>
    <section className="ed-sources-layout"><Card title="Data catalog" kicker="PROVENANCE" icon={Database}><div className="ed-source-list">{sources.map((source,i)=><article key={source.title} className="ed-source-item"><div className="ed-source-item-index">{String(i+1).padStart(2,"0")}</div><div className="ed-source-item-body"><span className="ed-eyebrow">{source.label}</span><h3>{source.title}</h3><p>{source.about}</p><SourceLink href={source.url}>Official source</SourceLink></div></article>)}</div></Card>
      <div className="ed-side-stack"><Card title="Data quality" kicker="VALIDATION" icon={ShieldCheck}><div className="ed-source-checks"><div><DataState name="Core grid, rain, terrain & rivers" variant={data?"ready":"pending"}/><p>Loaded together with cell-id and record-count validation.</p></div><div><DataState name="Preliminary vulnerability" variant={available("vulnerability")?"ready":"pending"}/><p>Retrospective indicator; interpretation is relative.</p></div><div><DataState name="Flood extent observations" variant={available("flood")?"ready":"pending"}/><p>Real flood polygons only, never assumed.</p></div><div><DataState name="Population estimates" variant={available("population")?"ready":"pending"}/><p>2020 population estimates, not confirmed impact.</p></div></div></Card><Card title="Known limitations" kicker="SCIENTIFIC HONESTY" icon={CircleAlert}><div className="ed-bullet-notes"><p>Original NASA pixels are not the same as the 5 km analysis cells.</p><p>HydroRIVERS may omit small channels and irrigation networks.</p><p>NASADEM source gaps are missing, never zero-valued terrain.</p><p>August 2022 rainfall plus August 2022 flooding supports retrospective evaluation—not proven forecasting skill.</p><p>Unknown satellite assessment coverage must not be interpreted as no flooding.</p></div></Card></div>
    </section>
    {reportStages&&<Card title="Pipeline stage report" kicker="LIVE LOCAL STATUS" icon={Activity}><div className="ed-stage-grid">{Object.entries(reportStages).map(([key,value])=><div className="ed-stage-item" key={key}><span>{key.replaceAll("_"," ")}</span><strong>{typeof value==="object"&&value!==null?String((value as Record<string,unknown>).status??"recorded"):String(value)}</strong></div>)}</div></Card>}
    <Card title="Reproducible implementation" kicker="ENGINEERING" icon={BookOpenText}><div className="ed-method-grid"><div><h3>Spatial joins</h3><p>All processed layers are joined by stable <code>cell_id</code>. Area calculations used an equal-area CRS; river distances use a meter-based UTM projection.</p></div><div><h3>Frontend data flow</h3><p>Next.js + MapLibre read local static JSON outputs. No frontend values are fabricated, and source errors stay visible.</p></div><div><h3>Validation</h3><p>Geometries, record counts, river-distance completeness, missing terrain, and optional analysis status can be inspected in the processed metadata files.</p></div></div></Card><div className="ed-small-note"><Earth size={15}/> Earth Detective uses NASA open Earth observations together with clearly attributed non-NASA geographic sources.</div>
  </>;
}
