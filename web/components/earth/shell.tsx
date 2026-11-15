"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { gsap } from "gsap";
import {
  Activity, ArrowRight, BookOpenText, ChartNoAxesCombined, ChevronRight,
  DatabaseZap, Earth, Grid2X2, LayoutDashboard, Menu, PanelLeftClose,
  PanelLeftOpen, Search, ShieldCheck, Waves, X,
} from "lucide-react";
import { EarthDataProvider, useEarth } from "./data-context";

type Icon = typeof LayoutDashboard;
const links: { label:string; href:string; icon:Icon; detail:string }[]=[
  { label:"Overview", href:"/",icon:LayoutDashboard, detail:"Mission control" },
  { label:"Detailed analysis", href:"/details",icon:ChartNoAxesCombined,detail:"Environmental layers" },
  { label:"Vulnerability", href:"/vulnerability",icon:Waves,detail:"Relative indicators" },
  { label:"Grid explorer", href:"/explore",icon:Grid2X2,detail:"Cell-level inspection" },
  { label:"Sources & methods", href:"/sources",icon:BookOpenText,detail:"Scientific provenance" },
];
const routeName:Record<string,string>={"/":"Overview","/details":"Detailed analysis","/vulnerability":"Vulnerability","/explore":"Grid explorer","/sources":"Sources & methods","/grid":"Grid explorer","/science":"Vulnerability"};

function Shell({children}:{children:React.ReactNode}) {
  const pathname=usePathname(),router=useRouter();
  const [collapsed,setCollapsed]=useState(false);
  const [mobileOpen,setMobileOpen]=useState(false);
  const [search,setSearch]=useState("");
  const contentRef=useRef<HTMLElement|null>(null);
  const {data,loading,error,setSelectedId}=useEarth();

  useEffect(()=>{
    setMobileOpen(false);
    const scope=contentRef.current;
    if (!scope || window.matchMedia("(prefers-reduced-motion: reduce)").matches)return;
    const ctx=gsap.context(()=>{
      gsap.fromTo("[data-animate]",{opacity:0,y:14},{opacity:1,y:0,duration:.55,stagger:.055,ease:"power2.out",clearProps:"transform,opacity"});
    },scope);
    return ()=>ctx.revert();
  },[pathname]);

  useEffect(()=>{
    if (!mobileOpen)return;
    function onEscape(e:KeyboardEvent){if(e.key==="Escape")setMobileOpen(false);}
    window.addEventListener("keydown",onEscape);
    return ()=>window.removeEventListener("keydown",onEscape);
  },[mobileOpen]);

  const openCell=()=>{
    const id=search.trim();
    if (!data || !data.byId.has(id)) return;
    setSelectedId(id);
    router.push("/explore");
    setSearch("");
  };
  const isValidSearch=!!data && data.byId.has(search.trim());
  return <div className={`ed-shell ${collapsed?"ed-shell--collapsed":""}`}>
    {mobileOpen&&<button aria-label="Close navigation" className="ed-mobile-shade" onClick={()=>setMobileOpen(false)}/>}
    <aside className={`ed-sidebar ${mobileOpen?"ed-sidebar--mobile-open":""}`} aria-label="Main navigation">
      <div className="ed-sidebar-top">
        <Link className="ed-brand" href="/" title="Earth Detective - Overview" onClick={()=>setMobileOpen(false)}>
          <span className="ed-brand-symbol"><Earth size={23} strokeWidth={1.6}/></span>
          <span className="ed-brand-copy"><strong>EARTH<br/>DETECTIVE</strong><small>SPACE APPS / 2026</small></span>
        </Link>
        <button className="ed-close-mobile ed-icon-button" aria-label="Close navigation" onClick={()=>setMobileOpen(false)}><X size={19}/></button>
      </div>
      <div className="ed-sidebar-section">WORKSPACE</div>
      <nav className="ed-nav">
        {links.map(({label,href,icon:Icon,detail})=>{
          const active=pathname===href||(href==="/explore"&&pathname==="/grid")||(href==="/vulnerability"&&pathname==="/science");
          return <Link key={href} href={href} className={`ed-nav-link ${active?"is-active":""}`} aria-current={active?"page":undefined} title={label}>
            <Icon size={18} strokeWidth={1.7}/><span className="ed-nav-label"><span>{label}</span><small>{detail}</small></span>
            {active&&<span className="ed-active-dot"/>}
          </Link>;
        })}
      </nav>
      <div className="ed-sidebar-bottom">
        <div className="ed-sidebar-status">
          <div className="ed-status-heading"><span className={`ed-dot ${error?"is-danger":data?"is-good":"is-muted"}`}/><span>Data workspace</span></div>
          <p>{error?"Source verification needed":loading?"Loading processed layers":data?`${data.grid.features.length.toLocaleString()} verified cell IDs`:"Waiting for sources"}</p>
          <Link href="/sources">View provenance <ArrowRight size={13}/></Link>
        </div>
        <button className="ed-collapse-btn" onClick={()=>setCollapsed(v=>!v)} aria-label={collapsed?"Expand sidebar":"Collapse sidebar"} title={collapsed?"Expand sidebar":"Collapse sidebar"}>
          {collapsed?<PanelLeftOpen size={18}/>:<PanelLeftClose size={18}/>}<span>Collapse sidebar</span>
        </button>
      </div>
    </aside>
    <div className="ed-main">
      <header className="ed-topbar">
        <div className="ed-topbar-left">
          <button className="ed-mobile-menu ed-icon-button" aria-label="Open navigation" onClick={()=>setMobileOpen(true)}><Menu size={20}/></button>
          <span className="ed-topbar-section">MISSION CONTROL</span>
          <ChevronRight size={14} className="ed-muted-icon"/>
          <span className="ed-topbar-page">{routeName[pathname]??"Analysis"}</span>
        </div>
        <div className="ed-topbar-right">
          <form className="ed-search" onSubmit={(e:React.FormEvent<HTMLFormElement>)=>{e.preventDefault();openCell();}} role="search">
            <Search size={16}/><input type="search" aria-label="Search exact cell ID" placeholder="Find cell ID..." value={search} onChange={(e:React.ChangeEvent<HTMLInputElement>)=>setSearch(e.target.value)} />
            {search&&<button type="submit" disabled={!isValidSearch} aria-label="Open cell"><ArrowRight size={15}/></button>}
          </form>
          <span className="ed-study-tag">SINDH · AUG 2022</span>
        </div>
      </header>
      <main className="ed-content" ref={contentRef} id="main-content">
        {error&&<div className="ed-error-banner" role="alert"><DatabaseZap size={19}/><div><strong>Scientific sources not loaded</strong><p>{error}</p></div><Link href="/sources">Methods <ArrowRight size={14}/></Link></div>}
        {children}
        <footer className="ed-footer"><span><Activity size={14}/> Earth Detective · retrospective environmental analysis</span><span>NASA GPM / NASADEM / HydroRIVERS <ShieldCheck size={14}/></span></footer>
      </main>
    </div>
  </div>;
}
export default function SiteShell({children}:{children:React.ReactNode}) {
  const pathname = usePathname();
  return <EarthDataProvider>{pathname === "/" ? children : <Shell>{children}</Shell>}</EarthDataProvider>;
}
