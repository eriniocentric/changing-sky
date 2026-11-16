"""Make explore.html (tiled, multi-night test viewer) from index.html by swapping the data layer.
Every replacement must match exactly once. Usage: python make_explore.py <index.html> <explore.html>"""
import re, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding='utf-8').read()

def rep(old, new, regex=False):
    global s
    if regex:
        n = len(re.findall(old, s, flags=re.S)); assert n == 1, (n, old[:80]); s = re.sub(old, lambda m: new, s, flags=re.S)
    else:
        n = s.count(old); assert n == 1, (n, old[:80]); s = s.replace(old, new)

# ---------- 1. data store: night index + top-ranked rows + sky tiles ----------
STORE = r'''let MANIFEST={};
const COLS2=["id","sid","ra","dec","cat","name","band","mag","snr","rel","mjd","xm","age","src","ss"];
const ALERTS=[], BYID=new Map(), BYKEY=new Map(), BYCAT={}, LOADED={unk:true,star:true}; let BGDONE=false;
const SSG=['Near-Earth','Inner belt / Mars-crossing zone','Main belt','Outer belt / Hilda zone','Jupiter Trojan zone','Centaur zone','Beyond Neptune','Comet'];
let NIGHTS=[], SELN=new Set(), TB=64, TN=[]; const DIRTY=new Set(), TILEP={}, DENSV={}; let TOPP=Promise.resolve();
const TILE_RAD=15; /* view radius (deg) below which every alert in view is loaded */
const TIME={on:false,i:0,t:0,night:null,trail:'night',visits:[],play:null};
function toObj(r,night){ const a={}; COLS2.forEach((c,i)=>{ a[c]=(r[i]===undefined)?null:r[i]; }); a.night=night; a.key=a.id+'@'+night;
 if(a.ss){ a.xm=SSG[a.ss[0]]+' · '+a.ss[1].toFixed(2)+' AU from the Sun'; a.rel=null; } if(a.snr===null) a.snr=0; return a; }
function addRows(rows,night){ rows.forEach(r=>{ const a=toObj(r,night); if(BYKEY.has(a.key)) return; BYKEY.set(a.key,a); ALERTS.push(a);
  if(!BYCAT[a.cat]) BYCAT[a.cat]=[]; BYCAT[a.cat].push(a); DIRTY.add(a.cat);
  const b=BYID.get(a.id); if(!b||(a.mjd||0)>(b.mjd||0)) BYID.set(a.id,a); }); }
function sortDirty(){ DIRTY.forEach(k=>{ if(BYCAT[k]) BYCAT[k].sort((x,y)=>y.snr-x.snr); }); DIRTY.clear(); }
function nightLabel(n){ const s=String(n), M=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']; return (+s.slice(6,8))+' '+M[+s.slice(4,6)-1]+' '+s.slice(0,4); }
function tileInit(){ TN=[]; for(let j=0;j<TB;j++){ const d=-90+(j+0.5)*180/TB; TN.push(Math.max(1,Math.ceil(360*Math.cos(d*Math.PI/180)/(180/TB)))); } }
function tileCentre(j,i){ return [(i+0.5)*360/TN[j], -90+(j+0.5)*180/TB]; }
function tilesNear(ra0,de0,rad){ const out=[], h=180/TB; for(let j=0;j<TB;j++){ const dc=-90+(j+0.5)*h; if(Math.abs(dc-de0)>rad+h) continue;
  for(let i=0;i<TN[j];i++){ const c=tileCentre(j,i); if(sepDeg(c[0],c[1],ra0,de0)<rad+2.2) out.push(j+'_'+i); } } return out; }
function loadTop(){ const ps=[];
 SELN.forEach(n=>{ const kt=n+'/top', kd=n+'/dens';
  if(!TILEP[kt]) TILEP[kt]=fetch('data/n/'+n+'/top.json').then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }).then(rows=>addRows(rows,n)).catch(e=>console.warn('top',n,e));
  if(!TILEP[kd]) TILEP[kd]=fetch('data/n/'+n+'/dens.json').then(r=>r.json()).then(d=>{ DENSV[n]=d; }).catch(e=>{ DENSV[n]={}; console.warn('dens',n,e); });
  ps.push(TILEP[kt],TILEP[kd]); });
 TOPP=Promise.all(ps); return TOPP; }
function ensureCat(k){ return TOPP; }
let listT=null; function renderListSoon(){ clearTimeout(listT); listT=setTimeout(renderList,300); }
let tilesPending=0;
function loadTilesInView(ra0,de0,rad){ if(rad>TILE_RAD||!TN.length) return; const want=tilesNear(ra0,de0,rad); let started=0;
 SELN.forEach(n=>{ const dv=DENSV[n]; if(!dv) return; want.forEach(t=>{ if(!dv[t]) return; const key=n+'/'+t; if(TILEP[key]||started>=48) return; started++; tilesPending++;
   TILEP[key]=fetch('data/n/'+n+'/t/'+t+'.json').then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
     .then(rows=>{ addRows(rows,n); }).catch(e=>{ console.warn('tile',key,e); TILEP[key]='failed'; })
     .then(()=>{ tilesPending--; scheduleCull(); renderListSoon(); }); }); });
 if(started) $('nshow').textContent='Loading every alert in view…'; }
function timeOK(a){ if(!SELN.has(a.night)) return false; if(!TIME.on) return true; const m=a.mjd||0;
 if(m>TIME.t+0.0002) return false;
 if(TIME.trail==='visit') return m>TIME.t-0.0002; if(TIME.trail==='hour') return m>TIME.t-1/24; if(TIME.trail==='night') return a.night===TIME.night; return true; }
let densOv=null;
function drawDensity(rad){ if(!aladin||!window.A) return; const on=rad>TILE_RAD&&visible.size>0;
 if(!densOv){ try{ densOv=A.graphicOverlay({name:'Alert density (zoom in for every alert)',color:'#8fa3c7',lineWidth:1}); aladin.addOverlay(densOv); }catch(e){ return; } }
 try{ densOv.removeAll(); }catch(e){} if(!on) return; const tot={};
 SELN.forEach(n=>{ const dv=DENSV[n]; if(!dv) return; Object.keys(dv).forEach(t=>{ const e=dv[t]; let c=0; visible.forEach(k=>{ c+=(e[2][k]||0); }); if(c){ if(!tot[t]) tot[t]=[e[0],e[1],0]; tot[t][2]+=c; } }); });
 const vals=Object.keys(tot).map(k=>tot[k]); if(!vals.length) return; const mx=Math.max.apply(null,vals.map(v=>v[2]));
 vals.forEach(v=>{ try{ densOv.add(A.circle(v[0],v[1],0.2+1.2*Math.sqrt(v[2]/mx))); }catch(e){} }); }
function mjdUTC(m){ const d=new Date((m-40587)*86400000-37000); return d.toISOString().replace('T',' ').slice(0,16)+' UTC'; }
function applyTime(){ const v=TIME.visits[TIME.i]; TIME.t=v?v[0]:0; TIME.night=v?v[1]:null; TIME.trail=$('trail').value;
 $('tlabel').textContent=v?('Exposure '+(TIME.i+1)+' of '+TIME.visits.length+' · '+mjdUTC(v[0])):'No exposure times for this selection';
 scheduleCull(); renderListSoon(); }
function setupSlider(){ const s=$('tslider'); s.max=Math.max(0,TIME.visits.length-1); s.value=s.max; TIME.i=+s.value; applyTime(); }
function stopPlay(){ if(TIME.play){ clearInterval(TIME.play); TIME.play=null; } $('playbtn').textContent='▶'; }
function wireTime(){
 $('timebox').onchange=()=>{ TIME.on=$('timebox').checked; $('timerow').style.display=TIME.on?'flex':'none'; if(!TIME.on) stopPlay(); applyTime(); };
 $('tslider').oninput=()=>{ TIME.i=+$('tslider').value; applyTime(); };
 $('trail').onchange=applyTime;
 $('playbtn').onclick=()=>{ if(TIME.play){ stopPlay(); return; } if(TIME.i>=TIME.visits.length-1) TIME.i=0; $('playbtn').textContent='⏸';
   TIME.play=setInterval(()=>{ if(TIME.i>=TIME.visits.length-1){ stopPlay(); return; } TIME.i++; $('tslider').value=TIME.i; applyTime(); },700); };
 $('nightsel').onchange=()=>selectNights($('nightsel').value); }
function nightSummary(){ const L=NIGHTS.filter(n=>SELN.has(n.night)); let shown=0, fink=0; const miss=[];
 L.forEach(n=>{ shown+=n.n; fink+=(n.fink&&n.fink.fink_objects)||0; if(n.xm&&!n.xm.milliquas) miss.push(nightLabel(n.night)); });
 return shown.toLocaleString()+' alerts after quality cuts'+(fink?' (Fink recorded '+fink.toLocaleString()+' objects)':'')+
   (miss.length?'. Quasar catalogue (Milliquas) not used for '+miss.join(', ')+' while CDS is offline.':''); }
function buildNightPicker(){ const s=$('nightsel'), L=NIGHTS.slice().reverse();
 s.innerHTML=L.map((n,i)=>'<option value="'+n.night+'">'+(i===0?'Latest night · ':'')+nightLabel(n.night)+' · '+n.n.toLocaleString()+'</option>').join('')+
   (NIGHTS.length>1?'<option value="all">All '+NIGHTS.length+' nights · '+NIGHTS.reduce((t,n)=>t+n.n,0).toLocaleString()+'</option>':''); }
function selectNights(v){ stopPlay(); SELN=new Set(v==='all'?NIGHTS.map(n=>n.night):[v]);
 MANIFEST={}; NIGHTS.forEach(n=>{ if(!SELN.has(n.night)) return; Object.keys(n.counts).forEach(k=>{ if(!MANIFEST[k]) MANIFEST[k]={n:0}; MANIFEST[k].n+=n.counts[k]; }); });
 TIME.visits=[]; NIGHTS.forEach(n=>{ if(SELN.has(n.night)&&n.visits) n.visits.forEach(t=>TIME.visits.push([t,n.night])); }); TIME.visits.sort((x,y)=>x[0]-y[0]);
 $('cats').innerHTML=''; buildCats(); $('nightinfo').textContent=nightSummary(); setupSlider();
 loadTop().then(()=>{ BGDONE=true; visible.forEach(k=>{ if(!layers[k]&&MANIFEST[k]) makeLayer(k); }); cullAll(); renderList();
   if(typeof renderTop==='function'){ renderTop(); renderFU(); drawPicks(); } }); }
'''
rep(r'const MANIFEST=\{.*?\n', '__STORE_PLACEHOLDER__\n', regex=True)
rep(r'const ALERTS=\[\], BYID=new Map\(\), BYCAT=\{\}, LOADED=\{\}; let BGDONE=false;\n.*?return LOADED\[k\]; \}\n', '', regex=True)
rep('__STORE_PLACEHOLDER__\n', STORE)

# ---------- 2. layers and culling ----------
rep(" if(!aladin||layers[k]||!BYCAT[k]) return; const c=catInfo[k];", " if(!aladin||layers[k]) return; const c=catInfo[k];")
rep(" const rad=Math.min(180,fov*0.75); let capped=false;\n visible.forEach(k=>{ const L=layers[k], arr=BYCAT[k]; if(!L||!arr) return;\n   let s=[]; for(const a of arr){ if(rad>=90||sepDeg(a.ra,a.dec,ra0,de0)<rad){ s.push(a); if(s.length>=MAXPER){ capped=capped||arr.length>MAXPER; break; } } }\n   L.removeAll(); L.addSources(s.map(a=>A.source(a.ra,a.dec,{id:a.id}))); });\n const n=$('cullnote'); if(n) n.style.display=capped?'block':'none';",
    " const rad=Math.min(180,fov*0.75); let capped=false; sortDirty(); loadTilesInView(ra0,de0,rad);\n visible.forEach(k=>{ const L=layers[k], arr=BYCAT[k]; if(!L) return; L.removeAll(); if(!arr) return;\n   let s=[]; for(const a of arr){ if(!timeOK(a)) continue; if(rad>=90||sepDeg(a.ra,a.dec,ra0,de0)<rad){ s.push(a); if(s.length>=MAXPER){ capped=true; break; } } }\n   L.addSources(s.map(a=>A.source(a.ra,a.dec,{id:a.key}))); });\n drawDensity(rad);\n const n=$('cullnote'); if(n){ const zo=rad>TILE_RAD&&visible.size>0; n.style.display=(capped||zo)?'block':'none';\n   n.textContent=zo?'Zoomed out: showing the top-ranked alerts of each type. Grey circles show where the rest are; zoom in to load every alert.':'Showing the strongest 4,000 alerts per type in view — zoom in to see more.'; }")

# ---------- 3. category list, search list, clicks ----------
rep("ensureCat(k).then(()=>{ d.classList.remove('loading'); if(!visible.has(k)) return; if(layers[k]) layers[k].show(); else makeLayer(k); renderList(); });",
    "ensureCat(k).then(()=>{ d.classList.remove('loading'); if(!visible.has(k)) return; if(layers[k]) layers[k].show(); else makeLayer(k); cullAll(); renderList(); });")
rep("let L=ALERTS.filter(a=>visible.has(a.cat)&&(!q||", "let L=ALERTS.filter(a=>visible.has(a.cat)&&timeOK(a)&&(!q||")
rep("<br>${a.mag} mag (${a.band}) · SNR ${a.snr}${a.ss?' · seen '+a.ss[4]+'× tonight':' · rel '+a.rel}`;",
    "<br>${a.mag} mag (${a.band}) · SNR ${a.snr}${a.ss?' · seen '+a.ss[4]+'× that night':' · rel '+a.rel}${SELN.size>1?' · '+nightLabel(a.night):''}`;")
rep("aladin.on('objectClicked',o=>{ if(o&&o.data&&o.data.id){const a=BYID.get(o.data.id); if(a) openAlert(a,false);} });",
    "aladin.on('objectClicked',o=>{ if(o&&o.data&&o.data.id){const a=BYKEY.get(o.data.id)||BYID.get(o.data.id); if(a) openAlert(a,false);} });")
rep("<tr><td>Found via</td><td>${a.src}</td></tr>",
    "<tr><td>Night</td><td>${nightLabel(a.night)}${a.age!=null?' · first detected '+(a.age===0?'that night':a.age+' days earlier'):''}</td></tr>\n  <tr><td>Found via</td><td>${a.src||'nightly sweep of all alerts'}</td></tr>")
rep("$('q').oninput=()=>{shown=300;renderList();};", "$('q').oninput=()=>{shown=300;renderList();};")

# ---------- 4. start-up: night index instead of category preloading ----------
rep(r" CATS\.forEach\(\(\[k\]\)=>\{ if\(visible\.has\(k\)\) ensureCat\(k\)\.then\(\(\)=>makeLayer\(k\)\); \}\);\n", "", regex=True)
rep(r" const startBG=\(\)=>\(async\(\)=>\{.*?setTimeout\(\(\)=>\{ if\(window\.requestIdleCallback\) requestIdleCallback\(startBG,\{timeout:4000\}\); else startBG\(\); \},2500\);\n",
    " wireTime();\n fetch('data/nights.json',{cache:'no-cache'}).then(r=>{ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); }).then(idx=>{ NIGHTS=idx.nights||[]; TB=idx.tile_bands||64; tileInit();\n   if(!NIGHTS.length) throw new Error('no nights'); buildNightPicker(); selectNights(NIGHTS[NIGHTS.length-1].night); })\n  .catch(e=>{ $('nshow').textContent='Could not load the list of nights ('+e.message+').'; });\n", regex=True)

# ---------- 5. controls ----------
rep('<div class="ph flash" id="cathead">',
    '<div class="ph">Night</div><div id="nightrow"><select id="nightsel"></select><div id="nightinfo" class="sub"></div></div>\n'
    '  <label class="cat" style="cursor:pointer"><input type="checkbox" id="timebox"> ⏱ Time view: step through the exposures</label>\n'
    '  <div id="timerow" style="display:none"><button id="playbtn" title="Play / pause">▶</button><input type="range" id="tslider" min="0" max="0" value="0">'
    '<select id="trail" title="Which alerts to keep on the sky"><option value="visit">this exposure only</option><option value="hour">the last hour</option>'
    '<option value="night" selected>this night so far</option><option value="all">everything so far</option></select><div id="tlabel" class="sub"></div></div>\n'
    '  <div class="ph flash" id="cathead">')
rep('#cullnote{', '#nightrow select{width:100%;background:#141a28;color:#e6e9ef;border:1px solid #2b3550;border-radius:5px;padding:3px;font-size:12px}\n'
    '#nightinfo{font-size:10.5px;margin:2px 0 4px}\n'
    '#timerow{flex-wrap:wrap;gap:4px;align-items:center;margin:2px 0 6px} #timerow input[type=range]{flex:1;min-width:120px}\n'
    '#timerow button{background:#141a28;color:#e6e9ef;border:1px solid #2b3550;border-radius:5px;padding:1px 8px;cursor:pointer}\n'
    '#timerow select{background:#141a28;color:#c8cfdd;border:1px solid #2b3550;border-radius:5px;font-size:11px} #tlabel{width:100%;font-size:10.5px}\n'
    '#cullnote{')
rep('<head>', '<head><meta name="robots" content="noindex">')
open(dst, 'w', encoding='utf-8').write(s)
print('wrote', dst, len(s))
