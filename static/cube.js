"use strict";
const $ = id => document.getElementById(id);
const text = (id, value) => { $(id).textContent = value; };
let catalog, region, selected, map, generation = 0, regionGeneration = 0, controller, sampleController, imageUrl;
const ready = new Promise(resolve => {
  setTimeout(()=>resolve(false),12000);
  if (!window.maplibregl) { resolve(false); return; }
  try {
    map = new maplibregl.Map({container:"map", style:{version:8,sources:{},layers:[{id:"background",type:"background",paint:{"background-color":"#202524"}}]},center:[-75,6],zoom:6, attributionControl:false});
    map.addControl(new maplibregl.NavigationControl({showCompass:false}),"bottom-right");
    map.addControl(new maplibregl.ScaleControl({unit:"metric"}),"bottom-left");
    map.once("load",()=>resolve(true));
    map.on("error",()=>text("error","A map source could not load. Retry the observation."));
  } catch { resolve(false); }
});
function message(title) { $("empty").hidden=false; $("empty").querySelector("h3").textContent=title; }
function remove(name) { if(map?.getLayer(name))map.removeLayer(name); if(map?.getSource(name))map.removeSource(name); }
function fit(bounds) { if(bounds&&map)map.fitBounds([[bounds[0],bounds[1]],[bounds[2],bounds[3]]],{padding:45,duration:matchMedia("(prefers-reduced-motion: reduce)").matches?0:650}); }
function family(item) { return item.id.replace(/_\d{4}-\d{2}-\d{2}$/, ""); }
function updateDates() {
  const dates=region.layers.filter(item=>family(item)===family(selected)).sort((a,b)=>a.id.localeCompare(b.id));
  $("dates").replaceChildren();
  dates.forEach(item=>{ const option=document.createElement("option");option.value=item.id;option.textContent=item.provenance.date||"Source acquisition";$("dates").append(option); });
  $("dates").value=selected.id;$("dates").disabled=dates.length<2;
  $("previous").disabled=$("dates").selectedIndex<=0;
  $("next").disabled=$("dates").selectedIndex>=dates.length-1;
  text("date-label",selected.provenance.date||"See provenance");
}
function listLayers() {
  $("layers").replaceChildren();
  const query=$("search").value.toLowerCase();
  const groups=new Map();
  region.layers.filter(l=>l.display.label.toLowerCase().includes(query)).forEach(item=>{
    const group=item.display.category;if(!groups.has(group))groups.set(group,[]);groups.get(group).push(item);
  });
  for(const [group,items] of groups){
    const heading=document.createElement("div");heading.className="group-title";heading.textContent=group;$("layers").append(heading);
    items.forEach(item=>{const button=document.createElement("button");button.className="layer"+(selected?.id===item.id?" active":"");button.setAttribute("aria-pressed",String(selected?.id===item.id));button.textContent=item.display.label;const hint=document.createElement("small");hint.textContent=item.display.units+" · "+(item.provenance.date||"CACHED OBSERVATION");button.append(hint);button.onclick=()=>selectLayer(item);$("layers").append(button);});
  }
  if(!groups.size){const p=document.createElement("p");p.className="muted";p.textContent=region.layers.length?"No matching observations.":"No packaged observations for this region.";$("layers").append(p);}
}
function updateMetadata(item) {
  const d=item.display;
  text("title",d.label);text("coverage",item.finite_pixels.toLocaleString()+" / "+item.total_pixels.toLocaleString());
  text("grid",item.shape.join(" × "));text("crs",item.crs);text("stream",d.provisional?"PROVISIONAL":"Source observation");
  text("source-file",item.source_file);text("provenance",JSON.stringify(item.provenance,null,2));text("method",item.command);
  text("legend-label",d.categorical?"Observed classes":"Display scale");text("units",d.units);
  text("minimum",d.minimum.toLocaleString(undefined,{maximumFractionDigits:3}));text("maximum",d.maximum.toLocaleString(undefined,{maximumFractionDigits:3}));
  text("legend-note",d.categorical?"Discrete classes · see source methodology":"Fixed layer range · transparent = no data");
  $("colorbar").replaceChildren();d.colors.forEach(color=>{const segment=document.createElement("span");segment.style.background=color;$("colorbar").append(segment);});
  $("legend").hidden=false;updateDates();listLayers();
}
async function selectLayer(item) {
  const token=++generation;controller?.abort();sampleController?.abort();controller=new AbortController();
  selected=item;$("point").hidden=true;remove("observation");$("legend").hidden=true;
  if(imageUrl){URL.revokeObjectURL(imageUrl);imageUrl=null;}
  updateMetadata(item);text("status","Loading");text("error","");message("Reading this observation…");
  history.replaceState(null,"","?aoi="+encodeURIComponent(region.aoi)+"&layer="+encodeURIComponent(item.id));
  const url="/api/cube/"+encodeURIComponent(region.aoi)+"/"+encodeURIComponent(item.id)+"/preview.png";
  try {
    const response=await fetch(url,{signal:controller.signal});if(!response.ok)throw Error("Preview unavailable");
    const blob=await response.blob();if(token!==generation)return;
    const localUrl=URL.createObjectURL(blob);const image=new Image();
    image.onload=()=>{if(token!==generation){URL.revokeObjectURL(localUrl);return;}imageUrl=localUrl;
      const [w,s,e,n]=item.bounds;
      map.addSource("observation",{type:"image",url:localUrl,coordinates:[[w,n],[e,n],[e,s],[w,s]]});
      map.addLayer({id:"observation",type:"raster",source:"observation",paint:{"raster-opacity":Number($("opacity").value)/100,"raster-resampling":"nearest","raster-fade-duration":0}});
      $("empty").hidden=true;text("status","Cached");text("map-note",item.display.provisional?"NISAR · PROVISIONAL":"CACHED OBSERVATION");
    };
    image.onerror=()=>{URL.revokeObjectURL(localUrl);if(token===generation){message("The preview could not be decoded.");text("status","Error");}};
    image.src=localUrl;
  } catch(error){if(error.name==="AbortError"||token!==generation)return;message("Observation unavailable. Select it to retry.");text("status","Error");text("error",error.message);}
}
async function selectRegion(preferred) {
  const regionToken=++regionGeneration;
  ++generation;controller?.abort();sampleController?.abort();selected=null;region=catalog.regions.find(r=>r.aoi===$("region").value);
  remove("observation");remove("context");$("point").hidden=true;$("legend").hidden=true;$("search").value="";
  text("region-title",region.label);text("region-state",region.state);text("title",region.label);text("error","");
  ["coverage","grid","crs","stream","date-label"].forEach(id=>text(id,"—"));["source-file","provenance","method"].forEach(id=>text(id,""));
  $("dates").replaceChildren();$("dates").disabled=true;$("previous").disabled=true;$("next").disabled=true;
  listLayers();fit(region.bounds);
  if(!region.layers.length){text("status","Not cached");message("This region’s observations are not cached.");history.replaceState(null,"","?aoi="+encodeURIComponent(region.aoi));return;}
  const initial=region.layers.find(l=>l.id===preferred)||region.layers.find(l=>l.id.startsWith("water_extent"))||region.layers.find(l=>l.id==="los_disp_mm")||region.layers[0];
  fit(initial.bounds);selectLayer(initial);
  const aoi=region.aoi;
  try {const response=await fetch("/api/sentinel-tiles/"+aoi);if(!response.ok)return;const context=(await response.json()).s2;
    if(regionToken!==regionGeneration||region.aoi!==aoi||!context?.tile_url)return;
    map.addSource("context",{type:"raster",tiles:[location.origin+context.tile_url],tileSize:256,bounds:context.bounds,minzoom:context.minzoom,maxzoom:context.maxzoom});
    map.addLayer({id:"context",type:"raster",source:"context",paint:{"raster-opacity":0.55}},map.getLayer("observation")?"observation":undefined);
  }catch{/* Context is optional; the analysis retains its own availability state. */}
}
$("search").oninput=()=>region&&listLayers();$("region").onchange=()=>selectRegion();
$("dates").onchange=()=>selectLayer(region.layers.find(l=>l.id===$("dates").value));
for(const [id,direction] of [["previous",-1],["next",1]])$(id).onclick=()=>{$("dates").selectedIndex+=direction;$("dates").onchange();};
$("opacity").oninput=()=>{if(map?.getLayer("observation"))map.setPaintProperty("observation","raster-opacity",Number($("opacity").value)/100);};
$("fit").onclick=()=>fit(selected?.bounds||region?.bounds);$("close-point").onclick=()=>{$("point").hidden=true;};
$("share").onclick=async()=>{try{await navigator.clipboard.writeText(location.href);text("share","View copied ✓");}catch{text("error","Copy the address bar to share this region and observation.");}};
async function start(){
  try{
    if(!await ready)throw Error("Map assets or WebGL unavailable. Check the frontend-assets cache and browser support.");
    map.on("click",async event=>{
      if(!selected)return;sampleController?.abort();sampleController=new AbortController();const token=generation;
      $("point").hidden=false;text("point-value","Reading…");text("point-detail","");
      try{const response=await fetch("/api/cube/"+region.aoi+"/"+selected.id+"/sample?lon="+event.lngLat.lng+"&lat="+event.lngLat.lat,{signal:sampleController.signal});if(!response.ok)throw Error();const sample=await response.json();if(token!==generation)return;
        text("point-value",sample.value===null?"No data":sample.value.toLocaleString(undefined,{maximumFractionDigits:4})+" "+sample.units);
        text("point-detail",sample.value===null?"No observed pixel at this location.":"Measured · nearest native pixel. Source and methodology below.");
      }catch(e){if(e.name!=="AbortError"&&token===generation)text("point-value","Unavailable");}
    });
    const response=await fetch("/api/cube");if(!response.ok)throw Error("Cube catalog unavailable");catalog=await response.json();
    catalog.regions.forEach(r=>{const option=document.createElement("option");option.value=r.aoi;option.textContent=r.label;$("region").append(option);});
    $("download").href=URL.createObjectURL(new Blob([JSON.stringify(catalog,null,2)],{type:"application/json"}));
    const query=new URLSearchParams(location.search);if(catalog.regions.some(r=>r.aoi===query.get("aoi")))$("region").value=query.get("aoi");
    await selectRegion(query.get("layer"));
  }catch(error){text("status","Error");message("The observatory could not open.");text("error",error.message);}
}
start();
