/* Shared by index.html and county.html.

   Both maps had byte-identical copies of everything below. The phone layout was
   116 lines in each file, and porting it by hand the first time is exactly how
   one copy ended up missing a CSS variable the other had. The two places the
   maps genuinely differ — what the peek strip says, and what the mode label
   appends — come in through phoneHooks() instead. */

/* ---- embedding (samkp.com wraps this page in an iframe) ----------------------
   A deep link shared from samkp.com has to reopen the same view, and "copy link"
   has to hand back the samkp.com URL, not the github.io one. So the parent is told
   the hash on every change, and is asked for its own URL when copying. Only the
   origins listed here are trusted, and only the hash — which is not sensitive — is
   ever sent. Standalone (unframed) use is unaffected. */
const EMBED_PARENTS = ["https://samkp.com", "https://www.samkp.com"];
const FRAMED = (()=>{ try { return !!window.parent && window.parent !== window; } catch(e){ return false; } })();
let _shareWaiters = [];
if(FRAMED) window.addEventListener("message", ev=>{
  if(!EMBED_PARENTS.includes(ev.origin)) return;
  const d = ev.data || {};
  if(d.type === "bpm:share-url" && typeof d.url === "string"){
    const w = _shareWaiters; _shareWaiters = []; w.forEach(fn=>fn(d.url));
  }
});
let EMBED_PAGE = "index";
function embedInit(page){ EMBED_PAGE = page; }
function notifyParent(){
  if(!FRAMED) return;
  for(const o of EMBED_PARENTS){
    try { window.parent.postMessage({type:"bpm:hash", page:EMBED_PAGE, hash:location.hash}, o); } catch(e){}
  }
}
function shareUrl(){
  if(!FRAMED) return Promise.resolve(location.href);
  return new Promise(res=>{
    let done=false; const finish=u=>{ if(!done){ done=true; res(u); } };
    _shareWaiters.push(finish);
    for(const o of EMBED_PARENTS){
      try { window.parent.postMessage({type:"bpm:share-url-request"}, o); } catch(e){}
    }
    setTimeout(()=>finish(location.href), 400);   // no answer: fall back to our own URL
  });
}

/* ================= phone layout =========================================
   The map is full-bleed and the results panel is a bottom sheet with three
   snap points, the pattern Google Maps uses and NN/G describes: non-modal,
   so the map stays live behind it, and never full height so it still reads
   as a sheet. The controls open as a separate sheet from the top bar, and
   only one sheet is ever open at a time.
   ====================================================================== */
const isPhone = () => matchMedia("(max-width:760px)").matches;
const SNAPS = ["peek","half","full"];
let sheetSnap = "peek";

function setSnap(sn){
  sheetSnap = SNAPS.includes(sn)? sn : "peek";
  const b=document.body;
  b.classList.remove("sheet-peek","sheet-half","sheet-full");
  b.classList.add("sheet-"+sheetSnap);
  const g=document.getElementById("sheetGrip");
  if(g) g.setAttribute("aria-expanded", String(sheetSnap!=="peek"));
  if(sheetSnap==="peek") document.getElementById("panel").scrollTop=0;
}

/* The peek strip has to earn its 112px: it carries the answer, so the map is
   readable without opening anything. Each map words that differently, so it
   supplies the text through phoneHooks(). */
let _phoneHooks = { label: ()=>"", modeSuffix: ()=>"" };
function phoneHooks(h){ Object.assign(_phoneHooks, h); }

function syncSheetLabel(){
  const g=document.getElementById("sheetGrip");
  if(!g || !isPhone()) return;
  let txt="";
  try { txt = _phoneHooks.label() || ""; } catch(e){}
  g.querySelector(".lbl").innerHTML = txt || "Results";
}

function syncTopBar(){
  if(!isPhone()) return;
  const c=document.getElementById("mbarContest"), m=document.getElementById("mbarMode");
  if(c) c.querySelector(".v").textContent = state.contest || "—";
  if(m){
    const btn=document.querySelector(`.modes button[data-mode="${state.mode}"]`);
    let v=btn? btn.textContent.trim() : state.mode;
    try { v += _phoneHooks.modeSuffix() || ""; } catch(e){}
    m.querySelector(".v").textContent = v;
  }
}

const openControls = on => document.body.classList.toggle("ctl-open", !!on);

function wirePhoneUI(){
  const grip=document.getElementById("sheetGrip");
  const sheet=document.getElementById("sheet");
  setSnap("peek");

  // tap cycles up, and back to peek from the top
  let dragged=false;
  grip.addEventListener("click", ()=>{
    if(dragged){ dragged=false; return; }
    setSnap(sheetSnap==="peek"? "half" : sheetSnap==="half"? "full" : "peek");
  });

  // drag: follow the finger, then snap to whichever point is nearest
  let startY=0, startTop=0, moved=0, dragging=false;
  const topFor = sn => sn==="full"? 0 : sn==="half"? window.innerHeight*0.42
                                      : sheet.offsetHeight - parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--peek"));
  grip.addEventListener("pointerdown", e=>{
    if(!isPhone()) return;
    dragging=true; moved=0; startY=e.clientY; startTop=topFor(sheetSnap);
    document.body.classList.add("sheet-drag");
    grip.setPointerCapture(e.pointerId);
  });
  grip.addEventListener("pointermove", e=>{
    if(!dragging) return;
    moved=e.clientY-startY;
    const max=topFor("peek");
    sheet.style.transform=`translateY(${Math.max(0,Math.min(max,startTop+moved))}px)`;
  });
  const end=()=>{
    if(!dragging) return;
    dragging=false; document.body.classList.remove("sheet-drag");
    sheet.style.transform="";
    if(Math.abs(moved)>8){
      dragged=true;
      const now=Math.max(0,Math.min(topFor("peek"), startTop+moved));
      let best=SNAPS[0], bd=Infinity;
      for(const sn of SNAPS){ const d=Math.abs(topFor(sn)-now); if(d<bd){ bd=d; best=sn; } }
      setSnap(best);
      setTimeout(()=>{ dragged=false; }, 60);
    }
  };
  grip.addEventListener("pointerup", end);
  grip.addEventListener("pointercancel", end);

  // top bar -> controls sheet
  const open=()=>{ openControls(true); setSnap("peek"); };
  document.getElementById("mbarContest").onclick = open;
  document.getElementById("mbarMode").onclick = open;
  document.getElementById("mbarInfo").onclick = ()=>{ document.getElementById("about").style.display="flex"; };
  document.getElementById("ctlDone").onclick = ()=> openControls(false);
  document.getElementById("ctlBackdrop").onclick = ()=> openControls(false);

  // legend collapses to one line until tapped
  const lg=document.getElementById("legend");
  lg.addEventListener("click", ()=>{ if(isPhone()) lg.classList.toggle("open"); });

  document.addEventListener("keydown", e=>{ if(e.key==="Escape") openControls(false); });
}
