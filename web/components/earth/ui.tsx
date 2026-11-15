"use client";
import { AlertCircle, ArrowUpRight, CheckCircle2, Database, Info, Layers3 } from "lucide-react";
import { useMemo } from "react";
import { formatNumber, Metric, metricMeta, useEarth } from "./data-context";

export function SectionTitle({eyebrow,title,description,action}:{eyebrow:string;title:string;description?:string;action?:React.ReactNode}) {
  return <div className="ed-section-heading" data-animate><div><span className="ed-eyebrow">{eyebrow}</span><h1>{title}</h1>{description&&<p>{description}</p>}</div>{action&&<div className="ed-heading-action">{action}</div>}</div>;
}
export function Card({children,className="",title,kicker,icon:Icon}:{children:React.ReactNode;className?:string;title?:string;kicker?:string;icon?:typeof Layers3}) {
  return <section className={`ed-card ${className}`} data-animate>{title&&<div className="ed-card-head"><div><span className="ed-eyebrow">{kicker}</span><h2>{title}</h2></div>{Icon&&<Icon size={18} strokeWidth={1.5}/>}</div>}{children}</section>;
}
export function MetricCard({label,value,unit,note,icon:Icon}:{label:string;value:string;unit?:string;note?:string;icon?:typeof Database}) {
  return <article className="ed-stat" data-animate><div className="ed-stat-header"><span>{label}</span>{Icon&&<Icon size={18} strokeWidth={1.6}/>}</div><div className="ed-stat-value">{value}<small>{unit}</small></div>{note&&<p>{note}</p>}</article>;
}
export function DataState({name="Data",variant="pending"}:{name?:string;variant?:"ready"|"pending"|"error"}) {
  return <span className={`ed-state ed-state--${variant}`}>{variant==="ready"?<CheckCircle2 size={13}/>:variant==="error"?<AlertCircle size={13}/>:<Info size={13}/>} {name}</span>;
}
export function MetricPicker({current,onChange,keys}:{current:Metric;onChange:(metric:Metric)=>void;keys:Metric[]}) {
  const {available}=useEarth();
  return <div className="ed-layer-picker" aria-label="Map metric">
    {keys.map(key=><button key={key} type="button" onClick={()=>onChange(key)} disabled={!available(key)} aria-pressed={current===key} className={`ed-layer-option ${current===key?"is-active":""}`} title={!available(key)?"Data not processed or unavailable":metricMeta[key].source}>{metricMeta[key].short}{!available(key)&&<span>—</span>}</button>)}
  </div>;
}
export function DetailRow({label,value,unit}:{label:string;value:number|null|undefined|string;unit?:string}){
  const display=typeof value==="string"?value:formatNumber(value,2);
  return <div className="ed-detail-row"><span>{label}</span><strong>{display}{display!=="Unavailable"&&unit?<small> {unit}</small>:null}</strong></div>;
}
export function CellDetails(){
  const {data,selectedId,getValue,setSelectedId}=useEarth();
  const selected=useMemo(()=>data?.grid.features.find(f=>f.properties.cell_id===selectedId)?.properties,[data,selectedId]);
  if (!selectedId||!selected) return <div className="ed-empty-selection"><Layers3 size={27} strokeWidth={1.1}/><strong>Inspect a grid cell</strong><p>Choose a polygon on the map or search an exact cell ID to explore its real measurements.</p></div>;
  const terrain=data?.terrain.get(selectedId);
  return <div className="ed-cell-panel"><div className="ed-cell-id"><div><small>SELECTED CELL</small><strong>{selectedId}</strong></div><button className="ed-icon-button" onClick={()=>setSelectedId(null)} aria-label="Clear selection">×</button></div>
    <DetailRow label="August rainfall" value={getValue(selectedId,"rainfall")} unit="mm"/>
    <DetailRow label="Mean elevation" value={getValue(selectedId,"elevation")} unit="m"/>
    <DetailRow label="Mean slope" value={getValue(selectedId,"slope")} unit="°"/>
    <DetailRow label="Nearest river" value={getValue(selectedId,"riverDistance")} unit="km"/>
    <DetailRow label="River length" value={getValue(selectedId,"riverLength")} unit="km"/>
    <DetailRow label="Preliminary indicator" value={getValue(selectedId,"vulnerability")} unit="/ 100"/>
    <DetailRow label="2020 estimated population" value={getValue(selectedId,"population")} unit="people"/>
    <DetailRow label="Observed flood fraction" value={getValue(selectedId,"flood")} unit="%"/>
    <DetailRow label="Cell footprint" value={typeof selected.clipped_area_km2==="number"?selected.clipped_area_km2:null} unit="km²"/>
    <div className="ed-cell-footnote">Terrain status: {String(terrain?.terrain_status ?? "unavailable")}. Missing values remain unavailable, never zero.</div>
  </div>;
}
export function SourceLink({href,children}:{href:string;children:React.ReactNode}) {return <a className="ed-text-link" href={href} target="_blank" rel="noopener noreferrer">{children}<ArrowUpRight size={13}/></a>}
