"""Static publishing — first-class deployment target, not an afterthought.

Writes a self-contained bundle openable from file:// or any static host:
  bundle/
    lecture.json      {manifest, events, checkpoint}
    artifacts/<sha>   content-addressed blobs
    index.html        dependency-free replay viewer (keyboard nav, ?step=N)

Static profile rules enforced: no live sockets, no credentials, sanitized HTML
only, relative artifact links, recorded fallback for interactive components.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from .context import ExecutionContext
from .ir import Checkpoint, LectureManifest

VIEWER_CSS = """
:root{color-scheme:light dark;--lectpy-body-font:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;--lectpy-code-font:ui-monospace,SFMono-Regular,Consolas,monospace;--lectpy-font-scale:1;--lectpy-line-height:1.55;--trace-highlight:#d97706}
body{font-family:var(--lectpy-body-font);font-size:calc(1rem * var(--lectpy-font-scale));margin:0 auto;max-width:1100px;padding:1.5rem;line-height:var(--lectpy-line-height)}
body[data-display=technical]{--lectpy-line-height:1.45}body[data-display=reading]{--lectpy-line-height:1.7}
code,pre,.source-line code{font-family:var(--lectpy-code-font)}
header.top{display:flex;flex-wrap:wrap;gap:1rem;align-items:baseline;border-bottom:1px solid #8884;padding-bottom:.5rem}
#stepbar{display:flex;gap:.5rem;align-items:center;margin:1rem 0;flex-wrap:wrap}
button{padding:.4rem .8rem;border:1px solid #888;border-radius:6px;background:Canvas;color:CanvasText;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
button:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:3px solid #0969da;outline-offset:2px}
#trace-layout{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:1rem;align-items:start}
#trace-layout:not(.trace-open){display:block}
#stage{border:1px solid #8884;border-radius:8px;padding:1rem;min-height:200px}
#source-panel{min-width:0}#source-panel[hidden]{display:none}
.source-title{font-size:1rem;margin:.1rem 0 .5rem}.source-scroll{border:1px solid #8884;border-radius:8px;overflow:auto;height:60vh;font-size:.88em;background:Canvas}
.source-line{display:flex;gap:.7rem;min-height:1.55em;line-height:1.55em;padding:0 .5rem;white-space:pre;cursor:pointer}.source-line:hover{background:#8882}
.source-line.current{background:color-mix(in srgb,var(--trace-highlight) 14%,Canvas);box-shadow:inset 3px 0 0 var(--trace-highlight)}.source-line.current .source-lineno{font-weight:700;color:var(--trace-highlight)}
.source-lineno{min-width:3em;text-align:right;opacity:.55;user-select:none}
.trace-location{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.75rem 0;font-family:var(--lectpy-code-font);font-size:.88em}.trace-location-current{opacity:.7}.trace-reference{border:0;border-radius:999px;padding:.2rem .55rem;color:CanvasText;background:color-mix(in srgb,var(--trace-highlight) 14%,Canvas);font-family:inherit;font-size:.95em}.trace-reference:hover{background:color-mix(in srgb,var(--trace-highlight) 24%,Canvas)}
pre.code{background:#8881;border-radius:8px;padding:.75rem;overflow:auto}
.lecture-code{margin:1rem 0}.lecture-code figcaption{font-weight:600}
.lecture-media{margin:1rem 0}.lecture-media img,.lecture-media video{display:block;max-width:100%;height:auto}.lecture-media figcaption{margin-top:.5rem}
.lecture-browser-window{border:1px solid #8884;border-radius:8px;padding:1rem;margin:1rem 0;background:#8881}.lecture-browser-window h3{margin:.1rem 0 .5rem}.browser-window-url{overflow-wrap:anywhere;word-break:break-word}.browser-window-actions{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center}.browser-window-actions a{padding:.4rem .8rem}.browser-window-status{min-height:1.4em;margin:.6rem 0 0}
.lecture-table{overflow:auto;max-height:480px;margin:1rem 0;border:1px solid #8884;border-radius:6px}
.lecture-table table{border-collapse:collapse;width:100%;text-align:left}
.lecture-table caption{text-align:left;padding:.75rem;font-weight:600}
.lecture-table th,.lecture-table td{padding:.5rem .75rem;border-top:1px solid #8884;vertical-align:top;min-width:8ch;max-width:35ch;overflow-wrap:anywhere}
.lecture-table thead{position:sticky;top:0;background:Canvas}.lecture-table tbody tr:nth-child(even){background:#8881}
.lecture-table th{white-space:nowrap}
pre.term{background:#111;color:#eee;border-radius:8px;padding:.75rem;overflow:auto;max-height:320px}
.muted{opacity:.7;font-size:.9em}
.viewbar{display:flex;flex-wrap:wrap;gap:1rem;align-items:center;margin:1rem 0}
.viewbar select{font:inherit;color:CanvasText;background:Canvas;border:1px solid #888;border-radius:6px;padding:.35rem .5rem}
.viewbar select:focus-visible{outline:3px solid #0969da;outline-offset:2px}
body[data-view=reader] #stepbar{display:none}
body[data-view=reader] #stage{border:0;padding:0}
body[data-view=presenter] #stage{font-size:1.35rem;min-height:60vh;padding:1.5rem}
body:not([data-view=inspector]) #help{display:none}
@media(max-width:900px){#trace-layout{grid-template-columns:1fr}}
@media(max-width:600px){body{padding:1rem}body[data-view=presenter] #stage{font-size:1.1rem;padding:1rem}}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
"""

VIEWER_JS = """
(function(){
"use strict";
var DATA=document.getElementById("lecture-data");
var bundle=JSON.parse(DATA.textContent);
var events=bundle.events||[];
var steps=events.filter(function(e){return e.kind==="step"});
var params=new URLSearchParams(location.search);
function resolveView(value){
  var valid=["reader","presenter","inspector"];
  if(valid.indexOf(value)>=0)return value;
  var configured=(bundle.manifest||{}).view;
  return valid.indexOf(configured)>=0?configured:(steps.length?"inspector":"reader");
}
var view=resolveView(params.get("view"));
var idx=Math.min(Math.max(parseInt(params.get("step")||"0",10)||0,0),Math.max(steps.length-1,0));
var stage=document.getElementById("stage");
var layout=document.getElementById("trace-layout");
var sourcePanel=document.getElementById("source-panel");
var traceLocation=document.getElementById("trace-location");
var sourceToggle=document.getElementById("source-toggle");
var displayMode=document.getElementById("display-mode");
var highlightMode=document.getElementById("highlight-mode");
var showSource=false;
var pos=document.getElementById("pos");
var meta=document.getElementById("meta");
var boardStates=new Map(),boardDisposers=[];
var browserController=typeof BrowserWindowController==="function"?new BrowserWindowController():null;
function safeBrowserUrl(value){try{var u=new URL(String(value||""));return u.protocol==="http:"||u.protocol==="https:"?u.href:""}catch(e){return ""}}
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function sourceFileName(value){return String(value||"").replace(/\\\\/g,"/").split("/").pop()||String(value||"")}
function traceReference(step){var ref=step&&step.payload&&step.payload.ref;if(!ref||typeof ref!=="object"||typeof ref.file!=="string"||typeof ref.line!=="number")return null;return ref}
function stepIndexForLine(line){var i,p;for(i=0;i<steps.length;i++){p=steps[i].payload||{};if(Number(p.line)>=line)return i}for(i=steps.length-1;i>=0;i--){p=steps[i].payload||{};if(Number(p.line)<=line)return i}return 0}
function stepIndexForReference(ref){var i,p,file;for(i=0;i<steps.length;i++){p=steps[i].payload||{};file=String(p.file||"");if(Number(p.line)===Number(ref.line)&&(!ref.func||p.func===ref.func)&&(!file||file===ref.file||sourceFileName(file)===sourceFileName(ref.file)))return i}return stepIndexForLine(Number(ref.line))}
function highlightValue(){return {amber:"#d97706",blue:"#2563eb",mint:"#0f766e",violet:"#7c3aed"}[highlightMode.value]||"#d97706"}
function applyDisplay(){
  var presets={
    system:{body:"system-ui,-apple-system,Segoe UI,Roboto,sans-serif",code:"ui-monospace,SFMono-Regular,Consolas,monospace",scale:"1",line:"1.55"},
    technical:{body:"Segoe UI,system-ui,sans-serif",code:"Cascadia Code,SFMono-Regular,Consolas,monospace",scale:".96",line:"1.45"},
    reading:{body:"Georgia,Times New Roman,serif",code:"ui-monospace,SFMono-Regular,Consolas,monospace",scale:"1.05",line:"1.7"}
  };
  var preset=presets[displayMode.value]||presets.system,root=document.documentElement.style;
  document.body.dataset.display=displayMode.value;
  root.setProperty("--lectpy-body-font",preset.body);
  root.setProperty("--lectpy-code-font",preset.code);
  root.setProperty("--lectpy-font-scale",preset.scale);
  root.setProperty("--lectpy-line-height",preset.line);
  root.setProperty("--trace-highlight",highlightValue());
}
function renderTraceLocation(step){
  if(view==="reader"||!step){traceLocation.innerHTML="";return}
  var p=step.payload||{},ref=traceReference(step),html='<span class="trace-location-current">'+esc(p.func||"main")+' · line '+esc(p.line||"?")+'</span>';
  if(ref)html+='<button type="button" class="trace-reference" data-ref-line="'+esc(ref.line)+'" title="Jump to '+esc(ref.file)+':'+esc(ref.line)+'">ref → '+esc(ref.func||"caller")+':'+esc(ref.line)+'</button>';
  traceLocation.innerHTML=html;
  var button=traceLocation.querySelector("[data-ref-line]");
  if(button&&ref)button.addEventListener("click",function(){idx=stepIndexForReference(ref);render()})
}
function renderSource(step){
  if(!bundle.source||!showSource||view==="reader"){sourcePanel.hidden=true;layout.classList.remove("trace-open");return}
  sourcePanel.hidden=false;layout.classList.add("trace-open");
  var scrollBox=sourcePanel.querySelector(".source-scroll");
  if(!scrollBox){
    var lines=bundle.source.text.split("\\n"),html='<h2 class="source-title">Source · '+esc(bundle.source.file)+'</h2><div class="source-scroll" role="log" aria-label="Lecture source">';
    lines.forEach(function(line,i){var number=i+1;html+='<div class="source-line" data-source-line="'+number+'" role="button" tabindex="0" aria-current="false"><span class="source-lineno">'+number+'</span><code>'+esc(line||" ")+'</code></div>'});
    sourcePanel.innerHTML=html+"</div>";
    scrollBox=sourcePanel.querySelector(".source-scroll");
    sourcePanel.querySelectorAll("[data-source-line]").forEach(function(row){var line=Number(row.getAttribute("data-source-line"));row.addEventListener("click",function(){idx=stepIndexForLine(line);render()});row.addEventListener("keydown",function(e){if(e.key==="Enter"||e.key===" "){e.preventDefault();idx=stepIndexForLine(line);render()}})})
  }
  var current=Number(step&&step.payload&&step.payload.line)||-1,active=null;
  sourcePanel.querySelectorAll("[data-source-line]").forEach(function(row){var isCurrent=Number(row.getAttribute("data-source-line"))===current;row.classList.toggle("current",isCurrent);row.setAttribute("aria-current",isCurrent?"true":"false");if(isCurrent)active=row});
  if(scrollBox&&active){var activeTop=active.offsetTop-scrollBox.offsetTop;scrollBox.scrollTop=Math.max(0,activeTop-(scrollBox.clientHeight-active.offsetHeight)/2)}
}
function renderOutput(ev){
  var p=ev.payload||{};
  if(ev.kind==="text"||ev.kind==="note"){return '<div class="out">'+(typeof p.html==="string"?p.html:'<pre>'+esc(p.markdown||"")+'</pre>')+'</div>'}
  if(ev.kind==="image"){return '<figure class="lecture-media"><img loading="lazy" src="'+esc(p.src||"")+'" alt="'+esc(p.alt||"")+'"><figcaption>'+esc(p.title||"")+'</figcaption></figure>'}
  if(ev.kind==="video"){return '<figure class="lecture-media"><video controls preload="metadata" aria-label="'+esc(p.title||"Video")+'" src="'+esc(p.src||"")+'"></video><figcaption>'+esc(p.title||"")+'</figcaption></figure>'}
  if(ev.kind==="link"){return '<p><a href="'+esc(p.href||"#")+'">'+esc(p.label||p.href||"")+'</a></p>'}
  if(ev.kind==="plot"){return '<details><summary>Plot (static fallback — spec retained)</summary><pre class="code">'+esc(JSON.stringify(p.spec||{},null,2))+'</pre></details>'}
  if(ev.kind==="terminal"){
    if(p.output){return '<pre class="term">'+esc(p.output)+'</pre>'}
    var cmd="$ "+(Array.isArray(p.argv)?p.argv.join(" "):String(p.argv||""));
    return '<pre class="term">'+esc(cmd)+'</pre><p class="muted">Recorded process block — attach a broker for a live PTY.</p>';
  }
  if(ev.kind==="component"){
    if(p.component_type==="whiteboard")return '<div data-whiteboard="'+ev.seq+'"></div>';
    if(p.component_type==="browser-window"){
      var props=p.props||{},action=props.action||"open",id=props.window_id||"reference",url=safeBrowserUrl(props.url),title=props.title||"Reference";
      if(action==="close")return '<section class="lecture-browser-window" data-browser-action="close" data-browser-id="'+esc(id)+'"><h3>Reference window: close request</h3><p class="muted">Window <code>'+esc(id)+'</code> is released when this step is reached.</p><p class="browser-window-status" role="status" aria-live="polite">Close request recorded.</p></section>';
      return '<section class="lecture-browser-window" data-browser-action="open" data-browser-id="'+esc(id)+'" data-browser-url="'+esc(url)+'" data-browser-title="'+esc(title)+'" data-browser-width="'+esc(props.width||1200)+'" data-browser-height="'+esc(props.height||800)+'" data-browser-left="'+esc(props.left==null?"":props.left)+'" data-browser-top="'+esc(props.top==null?"":props.top)+'" data-browser-resizable="'+(props.resizable===false?"false":"true")+'" data-browser-focus="'+(props.focus===false?"false":"true")+'"><h3>'+esc(title)+'</h3><p class="browser-window-url"><span>Reference: </span><code>'+esc(url||"Blocked URL")+'</code></p><p class="muted">'+esc(props.width||1200)+' × '+esc(props.height||800)+(props.left!=null||props.top!=null?' · position '+esc(props.left==null?"auto":props.left)+', '+esc(props.top==null?"auto":props.top):'')+' · lectpy_'+esc(id)+'</p><div class="browser-window-actions"><button type="button" data-browser-open="1"'+(url?'':' disabled')+'>Open reference window</button><button type="button" data-browser-close="1">Close reference window</button>'+(url?'<a href="'+esc(url)+'" target="_blank" rel="noopener noreferrer">Open reference link</a>':'')+'</div><p class="browser-window-status" role="status" aria-live="polite">Ready to open from this control.</p></section>';
    }
    return '<div class="muted" role="note">Interactive component <code>'+esc(p.component_type||"")+'</code> — recorded fallback in static mode.</div>'
  }
  if(ev.kind==="error"){return '<p role="alert"><strong>Error:</strong> '+esc(p.message||"")+'</p>'}
  return ""
}
function render(){
  document.body.dataset.view=view;
  if(view==="reader")showSource=false;
  document.getElementById("view-mode").value=view;
  sourceToggle.disabled=!bundle.source||view==="reader";
  sourceToggle.textContent=showSource?"Hide source":"Show source";
  sourceToggle.setAttribute("aria-pressed",showSource?"true":"false");
  applyDisplay();
  renderTraceLocation(steps[idx]);
  renderSource(steps[idx]);
  document.getElementById("view-status").textContent=view==="reader"?"Final recorded page":view==="presenter"?"Presentation with stepping":"State inspection";
  var s=steps[idx];
  var h="";
  // The final step owns the tail: outputs of the last source line (and crash
  // errors) have no later step to attach to, so they join the last step.
  // Anything at or before a `clear` event is dropped from outputs/inspects.
  var endSeq=(view==="reader"||!s||idx>=steps.length-1)?Infinity:s.seq;
  var clearSeq=-1,i;
  for(i=0;i<events.length;i++){if(events[i].kind==="clear"&&events[i].seq<=endSeq&&events[i].seq>clearSeq){clearSeq=events[i].seq}}
  var upto=events.filter(function(e){return e.kind!=="step"&&e.kind!=="clear"&&e.kind!=="inspect"&&e.kind!=="session_start"&&e.kind!=="session_end"&&e.kind!=="snapshot"&&e.seq<=endSeq&&e.seq>clearSeq});
  var p=(s&&s.payload)||{};
  var loc=(p.func||"")+" @ line "+(p.line||"?");
  if(s&&view==="inspector"){h+='<p class="muted">'+esc(loc)+'</p>'}
  var locals=p.locals||{};
  var keys=Object.keys(locals);
  if(keys.length&&view==="inspector"){h+='<details open><summary>Environment ('+keys.length+')</summary><pre class="code">'+esc(keys.map(function(k){return k+" = "+locals[k]}).join("\\n"))+'</pre></details>'}
  upto.forEach(function(ev){h+=renderOutput(ev)});
  var insp=events.filter(function(e){return e.kind==="inspect"&&e.seq<=endSeq&&e.seq>clearSeq}).slice(-8);
  if(insp.length&&view==="inspector"){h+='<details><summary>Inspected values</summary><pre class="code">'+esc(insp.map(function(e){return (e.payload.name||"?")+" = "+(e.payload.summary||"")}).join("\\n"))+'</pre></details>'}
  boardDisposers.forEach(function(dispose){dispose()});boardDisposers=[];
  stage.innerHTML=h||'<p class="muted">No content recorded.</p>';
  upto.forEach(function(ev){
    if(ev.kind!=="component"||(ev.payload||{}).component_type!=="whiteboard")return;
    var host=stage.querySelector('[data-whiteboard="'+ev.seq+'"]'),props=ev.payload.props||{};
    var state=boardStates.get(ev.seq)||{};boardStates.set(ev.seq,state);
    function mount(){
      host.replaceChildren();
      try{boardDisposers.push(mountWhiteboard(host,props,state))}catch(error){host.textContent="Whiteboard could not open: "+error.message}
    }
    if(state.open){mount()}else{
      var button=document.createElement("button");button.textContent="Open "+(props.title||"whiteboard");
      button.addEventListener("click",function(){state.open=true;mount()});host.append(button);
    }
  });
  if(browserController){stage.querySelectorAll('[data-browser-action]').forEach(function(card){
    var id=card.getAttribute('data-browser-id')||'reference',action=card.getAttribute('data-browser-action');
    var status=card.querySelector('.browser-window-status');
    function setStatus(message){if(status)status.textContent=message}
    if(action==='close'){
      setStatus(browserController.close(id).message);
      return;
    }
    var spec={window_id:id,url:card.getAttribute('data-browser-url')||'',title:card.getAttribute('data-browser-title')||'Reference',width:Number(card.getAttribute('data-browser-width')),height:Number(card.getAttribute('data-browser-height')),left:card.getAttribute('data-browser-left')===''?undefined:Number(card.getAttribute('data-browser-left')),top:card.getAttribute('data-browser-top')===''?undefined:Number(card.getAttribute('data-browser-top')),resizable:card.getAttribute('data-browser-resizable')!=='false',focus:card.getAttribute('data-browser-focus')!=='false'};
    var open=card.querySelector('[data-browser-open]'),close=card.querySelector('[data-browser-close]');
    if(open)open.addEventListener('click',function(){setStatus(browserController.open(spec).message)});
    if(close)close.addEventListener('click',function(){setStatus(browserController.close(id).message)});
  })}
  pos.textContent=steps.length?(idx+1)+" / "+steps.length:"Document";
  document.getElementById("prev").disabled=idx<=0;
  document.getElementById("next").disabled=idx>=steps.length-1;
  document.getElementById("over").disabled=idx>=steps.length-1;
  try{var u=new URL(location.href);u.searchParams.set("step",String(idx));history.replaceState(null,"",u)}catch(e){}
  meta.textContent=steps.length?"Step "+(idx+1)+" of "+steps.length:"Recorded document";
}
function go(d){idx=Math.min(Math.max(idx+d,0),Math.max(steps.length-1,0));render()}
document.getElementById("prev").addEventListener("click",function(){go(-1)});
document.getElementById("next").addEventListener("click",function(){go(1)});
document.getElementById("over").addEventListener("click",function(){go(1)});
document.getElementById("view-mode").addEventListener("change",function(e){
  view=resolveView(e.target.value);
  try{var u=new URL(location.href);u.searchParams.set("view",view);history.replaceState(null,"",u)}catch(error){}
  render();
});
sourceToggle.addEventListener("click",function(){showSource=!showSource;render()});
displayMode.addEventListener("change",function(){applyDisplay()});
highlightMode.addEventListener("change",function(){applyDisplay();render()});
window.addEventListener("popstate",function(){
  var p=new URLSearchParams(location.search);
  idx=Math.min(Math.max(parseInt(p.get("step")||"0",10)||0,0),Math.max(steps.length-1,0));
  view=resolveView(p.get("view"));render();
});
document.addEventListener("keydown",function(e){
  if(view==="reader")return;
  if(e.target&&e.target.closest&&e.target.closest('input,textarea,select,button,a,[contenteditable=true],[role=slider],.lecture-table,.lecture-code pre'))return;
  if(["ArrowRight","ArrowLeft","Home","End"].indexOf(e.key)>=0)e.preventDefault();
  if(e.key==="ArrowRight"){go(1)}else if(e.key==="ArrowLeft"){go(-1)}
  else if(e.key==="Home"){idx=0;render()}else if(e.key==="End"){idx=Math.max(steps.length-1,0);render()}
});
var reduced=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
if(!reduced){try{stage.scrollIntoView({block:"nearest"})}catch(e){}}
render();
})();
"""


def _viewer_html(title: str, bundle: dict[str, Any]) -> str:
    # Embedded JSON lives inside <script type="application/json">. A literal
    # `</script>` (or `<!--`) in lecture *data* would break out of that element
    # and become executable markup, so escape it for the HTML context. The
    # JSON parser still sees the same string after `\/` → `/` unescaping.
    embedded = json.dumps(bundle).replace("</", "<\\/").replace("<!--", "<\\!--")
    has_whiteboard = any(
        event.get("kind") == "component"
        and event.get("payload", {}).get("component_type") == "whiteboard"
        for event in bundle.get("events", [])
    )
    has_browser_window = any(
        event.get("kind") == "component"
        and event.get("payload", {}).get("component_type") == "browser-window"
        for event in bundle.get("events", [])
    )
    viewer = VIEWER_JS
    script_type = ""
    modules = []
    if has_whiteboard:
        modules.append(
            (Path(__file__).parent / "static" / "whiteboard.js").read_text(encoding="utf-8")
        )
    if has_browser_window:
        modules.append(
            (Path(__file__).parent / "static" / "browser_window.js").read_text(encoding="utf-8")
        )
    if modules:
        # Inline ESM has no external requests and works from file:// as well.
        viewer = "\n".join(modules) + "\n" + viewer
        script_type = ' type="module"'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self' http: https: data: blob:; media-src 'self' http: https: data: blob:; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-src 'none'; object-src 'none'">
<title>{html.escape(title)}</title>
<style>{VIEWER_CSS}</style>
</head>
<body>
<header class="top"><h1>{html.escape(title)}</h1><span class="muted">static replay · lectpy v0.3</span></header>
<div class="viewbar"><label for="view-mode">View</label>
<select id="view-mode"><option value="reader">Reader</option><option value="presenter">Presenter</option><option value="inspector">Inspector</option></select>
<label for="display-mode">Display</label>
<select id="display-mode"><option value="system">System</option><option value="technical">Technical</option><option value="reading">Reading</option></select>
<label for="highlight-mode">Highlight</label>
<select id="highlight-mode"><option value="amber">Amber</option><option value="blue">Blue</option><option value="mint">Mint</option><option value="violet">Violet</option></select>
<button id="source-toggle" type="button" aria-pressed="false">Show source</button>
<span id="view-status" class="muted" role="status"></span></div>
<div id="stepbar" role="toolbar" aria-label="Lecture stepping">
<button id="prev" aria-label="Previous step">← Back</button>
<button id="next" aria-label="Next step">Forward →</button>
<button id="over" aria-label="Step over">Step over</button>
<span id="pos" aria-live="off"></span>
<span id="meta" class="muted" role="status" aria-live="polite"></span>
</div>
<div id="trace-location" aria-live="polite"></div>
<div id="trace-layout">
<section id="source-panel" hidden aria-label="Lecture source"></section>
<main id="stage" tabindex="0" aria-label="Lecture stage"></main>
</div>
<p id="help" class="muted">Keyboard: ←/→ step, Home/End first/last. Step is deep-linked via <code>?step=N</code>. Reduced-motion respected. Plots/components show recorded fallbacks.</p>
<script id="lecture-data" type="application/json">{embedded}</script>
<script{script_type}>{viewer}</script>
</body>
</html>
"""


def _bundle_source(manifest: LectureManifest) -> dict[str, Any] | None:
    """Embed author source text for the shell's source pane (v0.2+).

    Static-profile safe: this is authored lecture content, not credentials.
    Missing/unreadable files yield None; the shell then hides the source pane.
    """
    if not manifest.source_file:
        return None
    try:
        text = Path(manifest.source_file).read_text(encoding="utf-8")
    except OSError:
        return None
    if len(text.encode("utf-8")) > 2_000_000:  # never bloat the bundle
        return None
    return {
        "file": Path(manifest.source_file).name,
        "sha256": manifest.source_sha256,
        "text": text,
    }


def export_static(
    ctx: ExecutionContext,
    manifest: LectureManifest,
    out_dir: str | Path,
    *,
    checkpoint: Checkpoint | None = None,
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "artifacts").mkdir(exist_ok=True)

    events = ctx.log.to_list()
    bundle = {
        "manifest": manifest.to_dict(),
        "events": events,
        "checkpoint": (
            checkpoint or Checkpoint(flavor="recorded", event_seq=len(events))
        ).to_dict(),
        "source": _bundle_source(manifest),
    }
    from .media import EXTENSIONS, collect_refs, rewrite_resources

    refs = collect_refs(events)
    refs.update(ref for event in events for ref in event.get("artifact_refs", []))
    resources = {}
    for ref in sorted(refs):
        if ctx.artifacts is None:
            raise ValueError(f"cannot export referenced artifact without a store: {ref}")
        ctx.artifacts.path(ref)  # Missing blobs are errors, not silently broken exports.
        meta = ctx.artifacts.meta(ref)
        mime = meta.mime if meta else "application/octet-stream"
        relative = "artifacts/" + ref.removeprefix("sha256:") + EXTENSIONS.get(mime, ".bin")
        ctx.artifacts.copy_to(ref, out / relative)
        resources[ref] = {
            "path": relative,
            "mime": mime,
            "bytes": meta.bytes if meta else (out / relative).stat().st_size,
        }
    if resources:
        bundle["resources"] = resources
        bundle["events"] = rewrite_resources(events, resources)

    (out / "lecture.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    (out / "index.html").write_text(_viewer_html(manifest.title, bundle), encoding="utf-8")
    return out
