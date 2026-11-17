"""Make explore.html (tiled, multi-night test viewer) from index.html by swapping the data layer.
Every replacement must match exactly once. Usage: python make_explore.py <site_template.html> <out.html>"""
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
function drawDensity(rad){ if(!aladin||!window.A) return; const db=$('densbox'); const on=rad>TILE_RAD&&visible.size>0&&!!(db&&db.checked);
 if(!densOv){ try{ densOv=A.graphicOverlay({name:'Where more alerts are',color:'rgba(170,185,215,0.32)',lineWidth:1}); aladin.addOverlay(densOv); }catch(e){ return; } }
 try{ densOv.removeAll(); }catch(e){} if(!on) return; const tot={};
 SELN.forEach(n=>{ const dv=DENSV[n]; if(!dv) return; Object.keys(dv).forEach(t=>{ const e=dv[t]; let c=0; visible.forEach(k=>{ c+=(e[2][k]||0); }); if(c){ if(!tot[t]) tot[t]=[e[0],e[1],0]; tot[t][2]+=c; } }); });
 const vals=Object.keys(tot).map(k=>tot[k]); if(!vals.length) return; const mx=Math.max.apply(null,vals.map(v=>v[2]));
 vals.forEach(v=>{ try{ densOv.add(A.circle(v[0],v[1],0.12+0.6*Math.sqrt(v[2]/mx))); }catch(e){} }); }
/* ---------- search this area in Fink (all dates, nothing stored here) ---------- */
const CONE_MAX=0.75; /* deg: largest search radius; the button appears when the view radius is at most this */
const FCOLS='r:diaObjectId,r:diaSourceId,r:ra,r:dec,r:band,r:psfFlux,r:snr,r:reliability,r:midpointMjdTai,r:isDipole,r:glint_trail,r:pixelFlags_saturatedCenter,r:trailLength,f:xm_vsx_Type,f:xm_tns_fullname,f:xm_tns_type,f:xm_x4lac_type,f:xm_x3hsp_type,f:xm_mangrove_HyperLEDA_name,f:xm_legacydr8_pstar,f:firstDiaSourceMjdTaiFink';
let FINKRES=[], FLAYERS={}, FCONE=null, coneBusy=false;
function fclean(v){ if(v===null||v===undefined) return null; const s=String(v); return (s===''||s==='nan'||s==='NaN'||s==='None'||s==='Fail'||s==='Unknown'||s==='null')?null:s; }
function fnight(m){ return new Date((m-40587)*86400000-37000).toISOString().slice(0,10).replace(/-/g,''); }
function finkClassify(r){ /* same quality cuts as the nightly build; types from Fink's own cross-matches only (no Gaia/SIMBAD) */
 if(r['r:isDipole']||r['r:pixelFlags_saturatedCenter']) return null;
 if((+r['r:snr']||0)<5) return null;
 if(r['r:glint_trail']) return ['glint',null,'Rubin glint-trail flag'];
 const vsx=fclean(r['f:xm_vsx_Type']), tns=fclean(r['f:xm_tns_fullname']), tt=fclean(r['f:xm_tns_type']), bl=fclean(r['f:xm_x4lac_type'])||fclean(r['f:xm_x3hsp_type']), led=fclean(r['f:xm_mangrove_HyperLEDA_name']), ps=+r['f:xm_legacydr8_pstar'];
 if(tt&&tt!=='AGN'&&tt!=='Varstar'&&tt!=='CV') return ['sn',tns,tt];
 if(tt==='AGN'||bl||vsx==='AGN'||vsx==='BLLAC'||vsx==='CV|QSO') return ['agn',tns,vsx?'VSX '+vsx:(bl||'AGN')];
 if((vsx&&vsx!=='SN Ia'&&vsx!=='SN Ia-pec')||tt==='Varstar'||tt==='CV') return ['var',tns,vsx?'VSX '+vsx:tt];
 if(tns) return ['at',tns,'TNS transient'];
 if(ps>0.5) return ['star',null,'Legacy Survey point source'];
 if(led) return ['gal',null,'HyperLEDA '+led];
 if((+r['r:reliability']||0)<0.8) return null;
 return ['unk',null,null]; }
function finkObj(r){ const c=finkClassify(r); if(!c) return null; const id=String(r['r:diaObjectId']), m=+r['r:midpointMjdTai'], f=Math.abs(+r['r:psfFlux']||0);
 const a={id:id,sid:String(r['r:diaSourceId']),ra:+r['r:ra'],dec:+r['r:dec'],cat:c[0],name:c[1],band:r['r:band'],mag:+(31.4-2.5*Math.log10(Math.max(f,1))).toFixed(2),
  snr:+(+r['r:snr']).toFixed(1),rel:r['r:reliability']==null?null:+(+r['r:reliability']).toFixed(2),mjd:+m.toFixed(4),
  xm:(c[2]?c[2]+' · ':'')+'type from Fink cross-matches',age:null,src:'Fink area search (all dates)',ss:null};
 const f0=+r['f:firstDiaSourceMjdTaiFink']; if(f0) a.age=Math.max(0,Math.floor(m-f0)); a.night=fnight(m); a.key=id+'@fink'; a.fink=true; return a; }
function drawFink(){ if(!aladin) return; Object.keys(FLAYERS).forEach(k=>FLAYERS[k].removeAll());
 FINKRES.forEach(a=>{ if(!visible.has(a.cat)) return; if(!FLAYERS[a.cat]){ const c=catInfo[a.cat]; FLAYERS[a.cat]=A.catalog({name:'Area search: '+c[1],color:c[2],sourceSize:12,shape:'square',selectionColor:'#ffffff'}); aladin.addCatalog(FLAYERS[a.cat]); }
   FLAYERS[a.cat].addSources([A.source(a.ra,a.dec,{id:a.key})]); }); }
function showFinkSummary(){ const n=$('conenote'); if(!FCONE){ n.style.display='none'; return; } const cnt={}; FINKRES.forEach(a=>{ if(visible.has(a.cat)) cnt[a.cat]=(cnt[a.cat]||0)+1; });
 const parts=Object.keys(cnt).map(k=>cnt[k].toLocaleString()+' '+catInfo[k][1].toLowerCase()); n.style.display='block';
 n.innerHTML='<b>Area search</b> (Fink, every date since Oct 2025, within '+(FCONE.rad*60).toFixed(0)+'′): '+FCONE.n.toLocaleString()+' objects; of the selected types '+(parts.length?parts.join(', '):'none')+' — shown as squares. Types use Fink\'s own cross-matches, so they are rougher than the nightly ones. <a href="#" id="coneclear">Clear</a>';
 $('coneclear').onclick=e=>{ e.preventDefault(); clearFink(true); }; }
function clearFink(hide){ FINKRES.forEach(a=>BYKEY.delete(a.key)); FINKRES=[]; Object.keys(FLAYERS).forEach(k=>FLAYERS[k].removeAll()); if(hide){ FCONE=null; $('conenote').style.display='none'; } }
async function coneSearch(){ if(coneBusy||!aladin) return; let ra0,de0,fov; try{ [ra0,de0]=aladin.getRaDec(); fov=Math.max.apply(null,aladin.getFov()); }catch(e){ return; }
 if(!visible.size){ $('conenote').style.display='block'; $('conenote').textContent='Choose one or more alert types first; the search returns those types.'; return; }
 const rad=Math.min(CONE_MAX,fov*0.75), b=$('conebtn'); coneBusy=true; b.disabled=true; b.textContent='🔎 Searching Fink…';
 try{ const r=await fetch(F+'/conesearch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ra:ra0,dec:de0,radius:Math.round(rad*3600),n:100,columns:FCOLS,'output-format':'json'})});
   if(!r.ok) throw new Error('HTTP '+r.status); const rows=bigJSON(await r.text()); if(!Array.isArray(rows)) throw new Error('unexpected reply');
   clearFink(false); const seen=new Set();
   rows.forEach(x=>{ const a=finkObj(x); if(!a||seen.has(a.id)) return; seen.add(a.id); const own=BYID.get(a.id); if(own&&!own.fink){ a.cat=own.cat; a.name=own.name||a.name; a.xm=own.xm; } FINKRES.push(a); BYKEY.set(a.key,a); });
   FCONE={ra:ra0,dec:de0,rad:rad,n:rows.length}; drawFink(); showFinkSummary();
 }catch(e){ $('conenote').style.display='block'; $('conenote').textContent='The Fink search did not work ('+e.message+'). Try again, or a smaller area.'; }
 finally{ coneBusy=false; b.disabled=false; b.textContent='🔎 All alerts here (Fink, all dates)'; } }
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
 $('nightsel').onchange=()=>selectNights($('nightsel').value);
 $('densbox').onchange=()=>cullAll();
 $('conebtn').onclick=coneSearch; }
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
    " const rad=Math.min(180,fov*0.75); let capped=false; sortDirty(); loadTilesInView(ra0,de0,rad);\n visible.forEach(k=>{ const L=layers[k], arr=BYCAT[k]; if(!L) return; L.removeAll(); if(!arr) return;\n   let s=[]; for(const a of arr){ if(!timeOK(a)) continue; if(rad>=90||sepDeg(a.ra,a.dec,ra0,de0)<rad){ s.push(a); if(s.length>=MAXPER){ capped=true; break; } } }\n   L.addSources(s.map(a=>A.source(a.ra,a.dec,{id:a.key}))); });\n drawDensity(rad);\n { const cb=$('conebtn'); if(cb) cb.style.display=(rad<=CONE_MAX)?'inline-block':'none'; } if(FCONE){ drawFink(); showFinkSummary(); }\n const n=$('cullnote'); if(n){ const zo=rad>TILE_RAD&&visible.size>0; n.style.display=(capped||zo)?'block':'none';\n   n.textContent=zo?'Zoomed out: showing the top-ranked alerts of each type. Zoom in to load every alert'+(($('densbox')&&$('densbox').checked)?' (faint circles mark where more are).':'.'):'Showing the strongest 4,000 alerts per type in view — zoom in to see more.'; }")

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
    '  <label class="cat" style="cursor:pointer" title="When zoomed out, only the strongest alerts are drawn. Circles mark sky patches holding more of the selected types; bigger means more. Zoom in to see them all."><input type="checkbox" id="densbox"> ◌ Show where more alerts are (zoomed out)</label>\n'
    '  <div class="ph flash" id="cathead">')
rep('#cullnote{', '#nightrow select{width:100%;background:#141a28;color:#e6e9ef;border:1px solid #2b3550;border-radius:5px;padding:3px;font-size:12px}\n'
    '#nightinfo{font-size:10.5px;margin:2px 0 4px}\n'
    '#timerow{flex-wrap:wrap;gap:4px;align-items:center;margin:2px 0 6px} #timerow input[type=range]{flex:1;min-width:120px}\n'
    '#timerow button{background:#141a28;color:#e6e9ef;border:1px solid #2b3550;border-radius:5px;padding:1px 8px;cursor:pointer}\n'
    '#timerow select{background:#141a28;color:#c8cfdd;border:1px solid #2b3550;border-radius:5px;font-size:11px} #tlabel{width:100%;font-size:10.5px}\n'
    '#conenote{display:none;position:absolute;top:66px;left:50%;transform:translateX(-50%);z-index:30;background:#141a28ee;border:1px solid #2b3550;border-radius:5px;padding:4px 10px;font-size:11px;color:#c8cfdd;max-width:min(640px,80%)}\n#conenote a{color:#74c0fc}\n'
    '#cullnote{')
rep('<div id="topbar"><button id="whole">Whole sky</button><button id="zoomsel">Zoom to selected</button></div>', '<div id="topbar"><button id="whole">Whole sky</button><button id="zoomsel">Zoom to selected</button><button id="conebtn" style="display:none" title="Ask Fink for every alert it has ever issued in this view, of the types you have selected. Nothing is stored here.">🔎 All alerts here (Fink, all dates)</button></div><div id="conenote"></div>')
rep('<head>', '<head><meta name="robots" content="noindex">')

# ---------- 6. automatic all-dates loading when zoomed in, and search anywhere (added 2026-11-17) ----------
SEARCH = r"""
/* ---------- zoomed in: load every alert ever seen here; search anywhere ---------- */
let autoT=null, PENDOPEN=null, FROWS=new Map();
function autoCone(ra0,de0,rad){ const ab=$('autocone'); if(!ab||!ab.checked||rad>CONE_MAX||!visible.size||coneBusy) return;
 if(FCONE && sepDeg(ra0,de0,FCONE.ra,FCONE.dec)<FCONE.rad*0.35 && rad<=FCONE.rad*1.3) return;
 clearTimeout(autoT); autoT=setTimeout(()=>coneSearch(),900); }
async function fpost(ep,body){ let r=null; for(let k=0;k<3;k++){ r=await fetch(F+'/'+ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({'output-format':'json'},body))});
   if(r.ok||![502,503,504].includes(r.status)) break; await new Promise(z=>setTimeout(z,2500*(k+1))); }
 if(!r.ok) throw new Error(ep+' HTTP '+r.status+(r.status>=500?' — Fink is busy':'')); const j=bigJSON(await r.text()); return Array.isArray(j)?j:[]; }
function parseCoords(q){ const s=q.trim(); if(!/^[-+0-9.:\shmsd°'",]+$/i.test(s)) return null; const sex=/[:hms°'"]/.test(s);
 const tk=s.replace(/[hmsd°'",:]/gi,' ').trim().split(/\s+/); if(tk.some(x=>!/^[-+]?\d+(\.\d+)?$/.test(x))) return null;
 let ra,de;
 if(tk.length===2&&!sex){ ra=+tk[0]; de=+tk[1]; }
 else if(tk.length===6){ ra=15*(+tk[0]+tk[1]/60+tk[2]/3600); const sg=tk[3].startsWith('-')?-1:1; de=sg*(Math.abs(+tk[3])+tk[4]/60+tk[5]/3600); }
 else if(tk.length===2&&sex){ ra=15*(+tk[0]); de=+tk[1]; }
 else return null;
 if(!(ra>=0&&ra<360&&de>=-90&&de<=90)) return null; return [ra,de]; }
function snote(t){ const n=$('conenote'); n.style.display='block'; n.textContent=t; }
async function findAnywhere(raw){ const q=raw.trim(); if(!q) return;
 try{
 const c=parseCoords(q); if(c){ return goSearch(c[0],c[1],null,'RA '+c[0].toFixed(5)+'°, Dec '+c[1].toFixed(5)+'°'); }
 let id=null, ra=null, de=null, label=q, tns=null;
 if(/^\d{15,20}$/.test(q)){ id=q; }
 else if(/^(SN|AT|TDE)\s*\d{4}[a-z]{1,4}$/i.test(q)||/^\d{4}[a-z]{2,4}$/i.test(q)){
   const core=q.replace(/^(SN|AT|TDE)\s*/i,''), pre=(q.match(/^(SN|AT|TDE)/i)||['SN'])[0].toUpperCase();
   snote('Looking up '+pre+' '+core+' on the Transient Name Server (via Fink)…');
   let js=[]; for(const p of [pre,'SN','AT','TDE']){ js=await fpost('resolver',{resolver:'tns',name_or_id:p+' '+core}); if(js.length) break; }
   if(!js.length){ snote('No Transient Name Server object called '+core+'.'); return; }
   const r=js[0]; ra=+r['f:ra']; de=+r['f:declination']; tns={name:r['f:fullname'],type:(r['f:type']&&r['f:type']!=='nan')?r['f:type']:null}; label=r['f:fullname']+(r['f:type']&&r['f:type']!=='nan'?' ('+r['f:type']+')':'');
   const m=String(r['f:internalname']||'').match(/LSST-AP-DO-(\d+)/); if(m) id=m[1]; }
 else { snote('Looking up “'+q+'” in SIMBAD (via Fink)…'); const js=await fpost('resolver',{resolver:'simbad',name_or_id:q});
   if(!js.length||js[0].jradeg==null){ snote('“'+q+'” was not found as a Rubin ID, TNS name, coordinates or SIMBAD name.'); return; }
   ra=+js[0].jradeg; de=+js[0].jdedeg; label=js[0].oname+(js[0].otype?' ('+js[0].otype+')':''); }
 if(id&&!tns){ try{ const rv=await fpost('resolver',{resolver:'tns',name_or_id:id,reverse:true}); const best=rv.filter(x=>x['f:xm_tns_fullname']).sort((x,y)=>(y['f:xm_tns_type']?1:0)-(x['f:xm_tns_type']?1:0))[0];
   if(best){ tns={name:best['f:xm_tns_fullname'],type:best['f:xm_tns_type']||null}; label=tns.name+(tns.type?' ('+tns.type+')':''); } }catch(e){} }
 if(id&&ra==null){ snote('Looking up Rubin object '+id+'…'); const rows=await fpost('sources',{diaObjectId:id,columns:'r:ra,r:dec,r:midpointMjdTai'});
   if(!rows.length){ snote('Fink has no Rubin object '+id+'.'); return; } rows.sort((x,y)=>x['r:midpointMjdTai']-y['r:midpointMjdTai']); ra=+rows[rows.length-1]['r:ra']; de=+rows[rows.length-1]['r:dec']; }
 return goSearch(ra,de,id,label,tns);
 }catch(e){ snote('Search failed ('+e.message+'). Try again.'); } }
async function goSearch(ra,de,id,label,tns){ if(!aladin) return; PENDOPEN=id; clearTimeout(autoT); FCONE=null;
 aladin.gotoRaDec(ra,de); aladin.setFoV(0.25); snote('Loading every alert around '+label+' from Fink…');
 coneSearch.force=true; try{ await coneSearch(); } finally { coneSearch.force=false; }
 if(id) await openPending(id,ra,de,tns); }
async function openPending(id,ra,de,tns){ let a=FINKRES.find(x=>x.id===id)||BYID.get(id);
 if(!a){ let r=FROWS.get(id); if(!r){ const rows=await fpost('conesearch',{ra:ra,dec:de,radius:5,n:100,columns:FCOLS}); r=rows.find(x=>String(x['r:diaObjectId'])===id); }
   if(r){ a=finkObj(r,true); if(a){ BYKEY.set(a.key,a); } } }
 PENDOPEN=null;
 if(a&&tns){ a.name=a.name||tns.name; const ty=tns.type;
   if(ty&&!/AGN|Varstar|CV/.test(ty)&&(a.cat==='unk'||a.cat==='at')){ a.cat='sn'; a.xm='TNS: '+tns.name+' · '+ty; } else if(a.cat==='unk'){ a.cat='at'; a.xm='TNS: '+tns.name+(ty?' · '+ty:''); } }
 if(a) openAlert(a,false); else snote('Found the position, but Fink returned no alert for object '+id+' there.'); }
"""
rep("function mjdUTC(m){", SEARCH + "function mjdUTC(m){")
rep("function finkObj(r){ const c=finkClassify(r); if(!c) return null;", "function finkObj(r,force){ const c=finkClassify(r)||(force?['unk',null,'below this site\\'s quality cuts']:null); if(!c) return null;")
rep("if(!visible.size){ $('conenote').style.display='block';", "if(!visible.size&&!coneSearch.force){ $('conenote').style.display='block';")
rep("clearFink(false); const seen=new Set();\n   rows.forEach(x=>{ const a=finkObj(x);", "clearFink(false); const seen=new Set(); FROWS=new Map();\n   rows.forEach(x=>{ FROWS.set(String(x['r:diaObjectId']),x); const a=finkObj(x);")
rep("FCONE={ra:ra0,dec:de0,rad:rad,n:rows.length}; drawFink(); showFinkSummary();", "FCONE={ra:ra0,dec:de0,rad:rad,n:rows.length}; drawFink(); showFinkSummary(); renderListSoon();")
rep("{ const cb=$('conebtn'); if(cb) cb.style.display=(rad<=CONE_MAX)?'inline-block':'none'; }", "{ const cb=$('conebtn'); if(cb) cb.style.display=(rad<=CONE_MAX)?'inline-block':'none'; } autoCone(ra0,de0,rad);")
rep("let L=ALERTS.filter(a=>visible.has(a.cat)&&timeOK(a)&&(!q||", "let L=ALERTS.concat(FCONE?FINKRES.filter(a=>!BYID.has(a.id)):[]).filter(a=>visible.has(a.cat)&&(a.fink||timeOK(a))&&(!q||")
rep("$('conebtn').onclick=coneSearch; }", "$('conebtn').onclick=()=>{ FCONE=null; coneSearch(); };\n $('autocone').onchange=()=>{ if($('autocone').checked){ FCONE=null; cullAll(); } else clearFink(true); };\n $('q').addEventListener('keydown',e=>{ if(e.key==='Enter'){ e.preventDefault(); const v=$('q').value; if(/^\\d{15,20}$/.test(v.trim())||parseCoords(v)||filtered().length===0){ $('q').value=''; renderList(); findAnywhere(v); } } }); }")
rep('<label class="cat" style="cursor:pointer" title="When zoomed out,', '<label class="cat" style="cursor:pointer" title="When the view is under about 1.5 degrees across, ask Fink for every alert it has ever issued there (all dates since Oct 2025), not only the selected night. They are drawn as squares and added to the list."><input type="checkbox" id="autocone" checked> 🔎 Zoomed in: load every alert ever seen here</label>\n  <label class="cat" style="cursor:pointer" title="When zoomed out,')


# ---------- 7. simpler right panel: month + night pickers, extra options folded away (added 2026-11-17) ----------
rep('<div class="ph">Night</div><div id="nightrow"><select id="nightsel"></select>', '<div class="ph">Night</div><div id="nightrow"><select id="monthsel" title="Month"></select><select id="nightsel" title="Night"></select>')
m = re.search(r'\n  <label class="cat" style="cursor:pointer"><input type="checkbox" id="timebox">.*?(?=\n  <div class="ph flash" id="cathead">)', s, re.S); assert m; OPTS = m.group(0); s = s.replace(OPTS, '', 1)
m = re.search(r'\n  <div class="ph">🛰 Satellites</div>.*?(?=\n  <div class="ph">Find</div>)', s, re.S); assert m; SAT = m.group(0); s = s.replace(SAT, '', 1)
SAT = SAT.replace('<div class="ph">🛰 Satellites</div>', '')
rep('\n  <div class="ph">Find</div>', '\n  <details id="moreopts"><summary>⚙ More options</summary>' + OPTS + SAT + '\n  </details>\n  <div class="ph">Find</div>')
rep('#nightrow select{width:100%;', '#right .tabs{display:none}\n#moreopts{margin:6px 0 2px}#moreopts summary{cursor:pointer;font-size:12px;color:#c8cfdd}#moreopts .cat{margin-left:2px}\n#nightrow{display:flex;flex-wrap:wrap;gap:4px}#nightrow #monthsel{flex:0 0 42%}#nightrow #nightsel{flex:1}#nightinfo{width:100%}\n#nightrow select{')
m = re.search(r"function buildNightPicker\(\)\{.*?\.toLocaleString\(\)\+'</option>':''\); \}\n", s, re.S); assert m and m.group(0).count('function buildNightPicker')==1
s = s.replace(m.group(0), r"""function monthKey(n){ return String(n).slice(0,6); }
function monthLabel(k){ const M=['January','February','March','April','May','June','July','August','September','October','November','December']; return M[+k.slice(4,6)-1]+' '+k.slice(0,4); }
function fillNights(mk,pick){ const s=$('nightsel'), L=ALLN.filter(n=>monthKey(n.night)===mk).slice().reverse(), newest=ALLN.length?ALLN[ALLN.length-1].night:'';
 s.innerHTML=L.map(n=>'<option value="'+n.night+'">'+(n.night===newest?'Latest · ':'')+nightLabel(n.night)+' · '+(n.stored?n.n.toLocaleString()+' alerts, whole sky':(n.fink?n.fink.toLocaleString()+' alerts · zoom in to load':'zoom in to load'))+'</option>').join('');
 const st=L.find(n=>n.stored); s.value=pick||(st?st.night:(L[0]&&L[0].night)); }
function buildNightPicker(){ if(!ALLN.length) ALLN=NIGHTS.map(n=>({night:n.night,n:n.n,stored:true})); ALLN.forEach(a=>{ const s=NIGHTS.find(n=>n.night===a.night); if(s){ a.stored=true; a.n=s.n; } });
 const ms=$('monthsel'), keys=[...new Set(ALLN.map(n=>monthKey(n.night)))].reverse(), stk=monthKey(NIGHTS[NIGHTS.length-1].night);
 ms.innerHTML=keys.map(k=>{ const c=ALLN.filter(n=>monthKey(n.night)===k).length; return '<option value="'+k+'">'+monthLabel(k)+' · '+c+' night'+(c>1?'s':'')+'</option>'; }).join('');
 ms.value=stk; fillNights(stk);
 ms.onchange=()=>{ fillNights(ms.value); selectNights($('nightsel').value); }; }
""", 1)


# ---------- 8. only the latest night is stored; any other Fink night loads on demand when zoomed in (added 2026-11-17) ----------
rep("function selectNights(v){", "function selectStored(v){")
rep("const FCOLS=", "let ODN=null, ALLN=[];\nconst SCOLS='r:diaObjectId,r:diaSourceId,r:ra,r:dec,r:band,r:psfFlux,r:snr,r:reliability,r:midpointMjdTai,r:isDipole,r:glint_trail,r:pixelFlags_saturatedCenter,r:trailLength';\nconst FCOLS=")
rep("<b>Area search</b> (Fink, every date since Oct 2025, within '", "<b>'+(ODN?'Alerts of '+nightLabel(ODN.night):'Area search')+'</b> (Fink, '+(ODN?'that night only':'every date since Oct 2025')+', within '")
rep("function autoCone(ra0,de0,rad){ const ab=$('autocone'); if(!ab||!ab.checked||rad>CONE_MAX||!visible.size||coneBusy) return;",
    "function autoCone(ra0,de0,rad){ const ab=$('autocone'); if(((!ab||!ab.checked)&&!ODN)||rad>CONE_MAX||!visible.size||coneBusy) return;")
rep(" CATS.forEach(([k,label,col])=>{ if(!n[k]) return;", " CATS.forEach(([k,label,col])=>{ if(!n[k]&&!(ODN&&k!=='sso')) return;")
rep("${label}<span class=\"cnt\">${n[k].toLocaleString()}</span>", "${label}<span class=\"cnt\">${n[k]?n[k].toLocaleString():'–'}</span>")
m = re.search(r"async function coneSearch\(\)\{.*?finally\{ coneBusy=false; b\.disabled=false; b\.textContent='🔎 All alerts here \(Fink, all dates\)'; \} \}\n", s, re.S); assert m
s = s.replace(m.group(0), r"""async function coneSearch(){ if(coneBusy||!aladin) return; let ra0,de0,fov; try{ [ra0,de0]=aladin.getRaDec(); fov=Math.max.apply(null,aladin.getFov()); }catch(e){ return; }
 if(!visible.size&&!coneSearch.force){ $('conenote').style.display='block'; $('conenote').textContent='Choose one or more alert types first; the search returns those types.'; return; }
 const rad=Math.min(CONE_MAX,fov*0.75), b=$('conebtn'), od=ODN; coneBusy=true; b.disabled=true; b.textContent='🔎 Searching Fink…';
 try{ const body={ra:ra0,dec:de0,radius:Math.round(rad*3600),n:100,columns:FCOLS};
   if(od){ Object.assign(body,{startdate:od.S,stopdate:od.E,kind:'across'}); snote('Loading the alerts of '+nightLabel(od.night)+' in view from Fink…'); }
   const rows=await fpost('conesearch',body); let use=rows;
   if(od){ const byId=new Map(rows.map(x=>[String(x['r:diaObjectId']),x])), multi=[];
     use=[]; rows.forEach(x=>{ if(Math.abs((+x['r:midpointMjdTai'])-(+x['f:firstDiaSourceMjdTaiFink']))>1e-6) multi.push(String(x['r:diaObjectId'])); else if(+x['r:midpointMjdTai']>=od.m0&&+x['r:midpointMjdTai']<=od.m1) use.push(x); });
     for(let k=0;k<multi.length;k+=300){ if(ODN!==od) return; snote('Loading the alerts of '+nightLabel(od.night)+' in view: light curves '+Math.min(k+300,multi.length)+' of '+multi.length+'…');
       const src=await fpost('sources',{diaObjectId:multi.slice(k,k+300).join(','),columns:SCOLS}); const best=new Map();
       src.forEach(d=>{ const t=+d['r:midpointMjdTai']; if(t<od.m0||t>od.m1) return; const id=String(d['r:diaObjectId']), q=(d['r:isDipole']||d['r:pixelFlags_saturatedCenter'])?-1:(+d['r:snr']||0), o=best.get(id);
         if(!o||q>o.q) best.set(id,{q:q,d:d}); });
       best.forEach((v,id)=>{ const x=Object.assign({},byId.get(id)||{},v.d); use.push(x); }); } }
   if(od&&ODN!==od) return;
   clearFink(false); const seen=new Set(); FROWS=new Map();
   use.forEach(x=>{ FROWS.set(String(x['r:diaObjectId']),x); const a=finkObj(x); if(!a||seen.has(a.id)) return; seen.add(a.id); if(od) a.src='Fink, alerts of '+nightLabel(od.night)+' (loaded on demand)';
     const own=BYID.get(a.id); if(own&&!own.fink&&!od){ a.cat=own.cat; a.name=own.name||a.name; a.xm=own.xm; } FINKRES.push(a); BYKEY.set(a.key,a); });
   FCONE={ra:ra0,dec:de0,rad:rad,n:use.length}; drawFink(); showFinkSummary(); renderListSoon(); if(od) odCounts();
 }catch(e){ $('conenote').style.display='block'; $('conenote').textContent='The Fink search did not work ('+e.message+'). Try again, or a smaller area.'; }
 finally{ coneBusy=false; b.disabled=false; b.textContent='🔎 All alerts here (Fink, all dates)'; } }
""", 1)
rep("function mjdUTC(m){", r"""function odWin(night){ const s=String(night), d=Date.UTC(+s.slice(0,4),+s.slice(4,6)-1,+s.slice(6,8)), a=new Date(d-6*3600e3), b=new Date(d+14*3600e3), f=x=>x.toISOString().slice(0,19).replace('T',' ');
 return {night:s,S:f(a),E:f(b),m0:a.getTime()/864e5+40587,m1:b.getTime()/864e5+40587}; }
function odCounts(){ const c={}; FINKRES.forEach(a=>c[a.cat]=(c[a.cat]||0)+1); document.querySelectorAll('#cats .cat').forEach(d=>{ const e=d.querySelector('.cnt'); if(e) e.textContent=(c[d.dataset.k]||0).toLocaleString(); }); }
function selectNights(v){ const stored=NIGHTS.some(n=>n.night===v);
 if(stored){ ODN=null; clearFink(true); return selectStored(v); }
 stopPlay(); ODN=odWin(v); clearFink(true); SELN=new Set([v]); MANIFEST={}; TIME.visits=[];
 $('cats').innerHTML=''; buildCats(); setupSlider(); const f=ALLN.find(n=>n.night===v);
 $('nightinfo').textContent=(f&&f.fink?f.fink.toLocaleString()+' alerts that night in Fink. ':'')+'Not stored here: zoom in (view under about 1.5° across) to load that night\'s alerts in view from Fink.';
 snote('Showing '+nightLabel(v)+': zoom in to load its alerts.'); cullAll(); renderList(); }
async function loadFinkNights(){ try{ const st=await fpost('statistics',{date:''}); const m=new Map(ALLN.map(n=>[n.night,n]));
   st.forEach(x=>{ const k=String(x['f:night']), a=+x['f:alerts']||0; if(!k||!a) return; const o=m.get(k); if(o) o.fink=a; else m.set(k,{night:k,fink:a,stored:false}); });
   ALLN=[...m.values()].sort((x,y)=>x.night<y.night?-1:1); const ms=$('monthsel').value, ns=$('nightsel').value; buildNightPicker(); $('monthsel').value=ms; fillNights(ms,ns);
 }catch(e){ console.warn('Fink night list',e); } }
function mjdUTC(m){""")

rep("selectNights(NIGHTS[NIGHTS.length-1].night); })", "selectNights(NIGHTS[NIGHTS.length-1].night); loadFinkNights(); })")

# ---------- 9. picking a non-stored night: show where Rubin looked and fly to the busiest area (added 2026-11-17) ----------
rep("function odCounts(){", r"""let ODSEED=null, ODLAYER=null, ODI=0;
async function odSeeds(od){ const pts=[];
 for(const tg of ['most_likely_sn','extragalactic_new_candidate','in_tns']){ try{ const r=await fpost('tags',{tag:tg,n:5000,startdate:od.S,stopdate:od.E,columns:'r:ra,r:dec'}); r.forEach(x=>{ if(x['r:ra']!=null) pts.push([+x['r:ra'],+x['r:dec']]); }); }catch(e){ console.warn('tag',tg,e); } if(ODN!==od) return null; }
 const cells=new Map(), d2r=Math.PI/180;
 pts.forEach(([ra,de])=>{ const k=Math.round(de/1.5)+'_'+Math.round(ra*Math.cos(de*d2r)/1.5); let c=cells.get(k); if(!c){ c={n:0,x:0,y:0,z:0}; cells.set(k,c); }
   c.n++; c.x+=Math.cos(de*d2r)*Math.cos(ra*d2r); c.y+=Math.cos(de*d2r)*Math.sin(ra*d2r); c.z+=Math.sin(de*d2r); });
 const L=[...cells.values()].map(c=>{ const r=Math.hypot(c.x,c.y,c.z); return {ra:(Math.atan2(c.y,c.x)/d2r+360)%360, dec:Math.asin(c.z/r)/d2r, n:c.n}; }).sort((a,b)=>b.n-a.n);
 return {n:pts.length,cells:L}; }
function odDraw(){ if(!aladin||!window.A) return; if(!ODLAYER){ ODLAYER=A.catalog({name:'Where Rubin looked that night',color:'#7f9bd6',sourceSize:9,shape:'circle',selectionColor:'#ffffff'}); aladin.addCatalog(ODLAYER); }
 ODLAYER.removeAll(); if(ODSEED) ODLAYER.addSources(ODSEED.cells.map((c,k)=>A.source(c.ra,c.dec,{odc:k}))); }
function odShow(rad){ if(ODLAYER){ try{ if(ODN&&ODSEED&&rad>CONE_MAX) ODLAYER.show(); else ODLAYER.hide(); }catch(e){} } }
function odGo(k){ if(!ODSEED||!ODSEED.cells.length||!aladin) return; const N=ODSEED.cells.length; ODI=((k%N)+N)%N; const c=ODSEED.cells[ODI];
 FCONE=null; aladin.gotoRaDec(c.ra,c.dec); aladin.setFoV(1.0); const b=$('odnext'); b.style.display='inline-block'; b.textContent='▶ Next busy area ('+(ODI+1)+' of '+N+')'; }
function odStart(od){ ODSEED=null; odDraw(); const b=$('odnext'); if(b) b.style.display='none'; if(!od) return;
 snote('Finding where Rubin looked on '+nightLabel(od.night)+'…');
 odSeeds(od).then(s=>{ if(ODN!==od||!s) return; ODSEED=s; odDraw();
   if(!s.cells.length){ snote('Fink lists no tagged alerts for '+nightLabel(od.night)+', so its footprint is unknown here. Zoom in anywhere to try.'); return; }
   snote(nightLabel(od.night)+': Rubin’s alerts fall in about '+s.cells.length+' sky areas (blue dots). Flying to the busiest; use ▶ Next busy area or click a blue dot.'); odGo(0); }); }
function odCounts(){""")
rep("snote('Showing '+nightLabel(v)+': zoom in to load its alerts.'); cullAll(); renderList(); }", "cullAll(); renderList(); odStart(ODN); }")
rep("if(stored){ ODN=null; clearFink(true); return selectStored(v); }", "if(stored){ ODN=null; clearFink(true); odStart(null); return selectStored(v); }")
rep(" autoCone(ra0,de0,rad);", " autoCone(ra0,de0,rad); odShow(rad);")
rep("aladin.on('objectClicked',o=>{ if(o&&o.data&&o.data.id){", "aladin.on('objectClicked',o=>{ if(o&&o.data&&o.data.odc!==undefined){ odGo(o.data.odc); return; } if(o&&o.data&&o.data.id){")
rep('<button id="conebtn"', '<button id="odnext" style="display:none" title="Fly to the next area where Rubin observed on this night">▶ Next busy area</button><button id="conebtn"')
rep("$('autocone').onchange=", "$('odnext').onclick=()=>odGo(ODI+1);\n $('autocone').onchange=")

open(dst, 'w', encoding='utf-8').write(s)
print('wrote', dst, len(s))
