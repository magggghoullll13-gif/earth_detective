"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Crosshair, Layers3, LocateFixed, MapPinned, RotateCcw } from "lucide-react";
import { formatNumber, getNeighbors, Metric, metricMeta, useEarth } from "./data-context";

const BOUNDS:[[number,number],[number,number]]=[[66,23.5],[71.5,28.5]];
function styleFor(metric:Metric):any[] {
  return ["case",["==",["get","metric_value"],null],"#394c5b",["interpolate",["linear"],["get","metric_value"],...metricMeta[metric].colors.flatMap(([v,c])=>[v,c])]];
}
function fitToFeature(geometry:unknown):[[number,number],[number,number]]|null {
  const coordinates=(geometry as {coordinates?:unknown})?.coordinates;
  let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
  function visit(v:unknown):void {
    if (!Array.isArray(v))return;
    if (v.length>=2 && typeof v[0]==="number" && typeof v[1]==="number") {minX=Math.min(minX,v[0]);maxX=Math.max(maxX,v[0]);minY=Math.min(minY,v[1]);maxY=Math.max(maxY,v[1]);}
    else v.forEach(visit);
  }
  visit(coordinates);
  return Number.isFinite(minX)?[[minX,minY],[maxX,maxY]]:null;
}
export default function EnvironmentalMap({metric,compact=false,showNeighborControl=true}:{metric:Metric;compact?:boolean;showNeighborControl?:boolean}) {
  const {data,selectedId,setSelectedId,getValue}=useEarth();
  const rootRef=useRef<HTMLDivElement|null>(null);
  const mapRef=useRef<any>(null);
  const [ready,setReady]=useState(false);
  const [mapError,setMapError]=useState<string|null>(null);
  const [opacity,setOpacity]=useState(76);
  const [borders,setBorders]=useState(true);
  const [showNeighbors,setShowNeighbors]=useState(true);
  const [neighborMode,setNeighborMode]=useState<4|8>(8);
  const [visible,setVisible]=useState(true);

  const colored=useMemo(()=>{
    if (!data)return null;
    return {type:"FeatureCollection" as const,features:data.grid.features.map(f=>({...f,properties:{...f.properties,metric_value:getValue(f.properties.cell_id,metric)}}))};
  },[data,getValue,metric]);
  const chosen=useMemo(()=>data?.grid.features.find(f=>f.properties.cell_id===selectedId),[data,selectedId]);

  useEffect(()=>{
    if (!data||!rootRef.current)return;
    let cancelled=false;
    let map:any;
    (async()=>{
      try {
        const maplibre=await import("maplibre-gl");
        if (cancelled||!rootRef.current)return;
        // Preserve the pre-existing worker file only when installed with the original map project.
        const worker=await fetch("/maplibre-gl-worker.mjs",{method:"HEAD"}).catch(()=>null);
        if(worker?.ok)maplibre.setWorkerUrl("/maplibre-gl-worker.mjs");
        if(cancelled||!rootRef.current)return;
        map=new maplibre.Map({
          container:rootRef.current,
          center:[68.75,26],zoom:6,renderWorldCopies:false,maxZoom:16,
          style:{version:8,sources:{satellite:{type:"raster",tileSize:256,tiles:["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],attribution:"Imagery © Esri and contributors"}},layers:[{id:"imagery",type:"raster",source:"satellite"}]} as any,
        });
        mapRef.current=map;
        map.addControl(new maplibre.NavigationControl({showCompass:false}),"top-right");
        map.on("load",()=>{
          if(cancelled)return;
          map.addSource("cells",{type:"geojson",data:data.grid as any});
          map.addLayer({id:"metric",type:"fill",source:"cells",paint:{"fill-color":"#406e88","fill-opacity":opacity/100}});
          map.addLayer({id:"borders",type:"line",source:"cells",paint:{"line-color":"#c8e1e8","line-width":0.35,"line-opacity":0.54}});
          map.addLayer({id:"neighbors",type:"fill",source:"cells",filter:["==",["get","cell_id"],"__none__"],paint:{"fill-color":"#d6ba77","fill-opacity":0.72}});
          map.addLayer({id:"selection",type:"line",source:"cells",filter:["==",["get","cell_id"],"__none__"],paint:{"line-color":"#fff","line-width":2.5}});
          map.on("click","metric",(ev:any)=>{const id=ev.features?.[0]?.properties?.cell_id;if(typeof id==="string")setSelectedId(id);});
          map.on("mouseenter","metric",()=>{map.getCanvas().style.cursor="pointer";});
          map.on("mouseleave","metric",()=>{map.getCanvas().style.cursor="";});
          map.fitBounds(BOUNDS,{padding:compact?32:42,duration:0});
          setReady(true);
        });
        map.on("error",(event:any)=>{console.warn("Map tile/source warning:",event?.error);});
      }catch(e){if(!cancelled)setMapError(e instanceof Error?e.message:String(e));}
    })();
    return ()=>{cancelled=true;map?.remove();mapRef.current=null;setReady(false);};
    // Never remount the expensive base map just because a frame changes.
  },[data,setSelectedId,compact]);

  useEffect(()=>{
    const map=mapRef.current;
    if(!map||!ready||!colored)return;
    const source=map.getSource("cells");
    if(source)void source.setData(colored as any);
    if(map.getLayer("metric"))map.setPaintProperty("metric","fill-color",styleFor(metric));
  },[colored,metric,ready]);
  useEffect(()=>{
    const map=mapRef.current;if(!map||!ready)return;
    map.setPaintProperty("metric","fill-opacity",visible?opacity/100:0);
    map.setLayoutProperty("borders","visibility",borders?"visible":"none");
  },[ready,opacity,borders,visible]);
  useEffect(()=>{
    const map=mapRef.current;if(!map||!ready)return;
    map.setFilter("selection",["==",["get","cell_id"],selectedId??"__none__"]);
    const near=chosen&&showNeighbors?getNeighbors(chosen.properties[neighborMode===4?"neighbors_4":"neighbors_8"]):[];
    map.setFilter("neighbors",["in",["get","cell_id"],["literal",near]]);
  },[ready,selectedId,chosen,neighborMode,showNeighbors]);

  return <div className={`ed-map-panel ${compact?"is-compact":""}`}>
    <div className="ed-map-toolbar"><div className="ed-map-toolbar-title"><MapPinned size={16}/><span>Geospatial layers</span><span className="ed-map-subtitle">5 km grid · satellite basemap</span></div><div className="ed-map-tools">
      <button onClick={()=>mapRef.current?.fitBounds(BOUNDS,{padding:40,duration:650})} aria-label="Fit study area" title="Fit study area"><RotateCcw size={16}/></button>
      <button onClick={()=>{const b=chosen&&fitToFeature(chosen.geometry);if(b)mapRef.current?.fitBounds(b,{padding:100,maxZoom:11,duration:650});}} disabled={!chosen} aria-label="Zoom to selected cell" title="Zoom to selected cell"><LocateFixed size={16}/></button>
      <button onClick={()=>setVisible(v=>!v)} aria-pressed={visible} aria-label="Toggle colored layer" title="Toggle colored layer"><Layers3 size={16}/></button>
    </div></div>
    <div className="ed-map-space" ref={rootRef} role="application" aria-label={`Interactive map showing ${metricMeta[metric].label} by grid cell`}/>
    {!ready&&!mapError&&<div className="ed-map-loading"><div className="ed-spinner"/> Preparing 12,412-cell map...</div>}
    {mapError&&<div className="ed-map-loading ed-map-error">Map unavailable: {mapError}</div>}
    <div className="ed-map-bottom">
      <div className="ed-map-legend"><div className="ed-legend-title"><span>{metricMeta[metric].label}</span><small>{metricMeta[metric].unit}</small></div><div className="ed-legend-bar" style={{background:`linear-gradient(90deg,${metricMeta[metric].colors.map(([,c])=>c).join(",")})`}}/><div className="ed-legend-labels"><span>{formatNumber(metricMeta[metric].colors[0][0],0)}</span><span>{formatNumber(metricMeta[metric].colors[metricMeta[metric].colors.length-1][0],0)}</span></div><span className="ed-legend-muted">Gray = unavailable · colors describe indicators, not predicted risk.</span></div>
      {!compact&&<div className="ed-map-options"><label><input type="checkbox" checked={borders} onChange={(e:React.ChangeEvent<HTMLInputElement>)=>setBorders(e.target.checked)}/> Grid boundaries</label>{showNeighborControl&&<label><input type="checkbox" checked={showNeighbors} onChange={(e:React.ChangeEvent<HTMLInputElement>)=>setShowNeighbors(e.target.checked)}/> Neighbors</label>}<label className="ed-opacity-control"><span>Opacity {opacity}%</span><input type="range" min="25" max="100" value={opacity} onChange={(e:React.ChangeEvent<HTMLInputElement>)=>setOpacity(Number(e.target.value))}/></label>{showNeighborControl&&<div className="ed-map-neighbor-modes"><button className={neighborMode===4?"is-active":""} onClick={()=>setNeighborMode(4)}>4</button><button className={neighborMode===8?"is-active":""} onClick={()=>setNeighborMode(8)}>8</button><span>neighbors</span></div>}</div>}
    </div>
    {chosen&&<span className="ed-map-selected"><Crosshair size={13}/> {selectedId}</span>}
  </div>;
}
