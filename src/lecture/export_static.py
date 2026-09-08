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
:root{color-scheme:light dark}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0 auto;max-width:900px;padding:1.5rem;line-height:1.55}
header.top{display:flex;gap:1rem;align-items:baseline;border-bottom:1px solid #8884;padding-bottom:.5rem}
#stepbar{display:flex;gap:.5rem;align-items:center;margin:1rem 0;flex-wrap:wrap}
button{padding:.4rem .8rem;border:1px solid #888;border-radius:6px;background:Canvas;color:CanvasText;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
button:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:3px solid #0969da;outline-offset:2px}
#stage{border:1px solid #8884;border-radius:8px;padding:1rem;min-height:200px}
pre.code{background:#8881;border-radius:8px;padding:.75rem;overflow:auto}
pre.term{background:#111;color:#eee;border-radius:8px;padding:.75rem;overflow:auto;max-height:320px}
.muted{opacity:.7;font-size:.9em}
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
var idx=Math.min(Math.max(parseInt(params.get("step")||"0",10)||0,0),Math.max(steps.length-1,0));
var stage=document.getElementById("stage");
var pos=document.getElementById("pos");
var meta=document.getElementById("meta");
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function renderOutput(ev){
  var p=ev.payload||{};
  if(ev.kind==="text"||ev.kind==="note"){return '<div class="out">'+(typeof p.html==="string"?p.html:'<pre>'+esc(p.markdown||"")+'</pre>')+'</div>'}
  if(ev.kind==="image"){return '<figure><img src="'+esc(p.src||"")+'" alt="'+esc(p.alt||"")+'"><figcaption>'+esc(p.title||"")+'</figcaption></figure>'}
  if(ev.kind==="video"){return '<video controls src="'+esc(p.src||"")+'"></video>'}
  if(ev.kind==="link"){return '<p><a href="'+esc(p.href||"#")+'">'+esc(p.label||p.href||"")+'</a></p>'}
  if(ev.kind==="plot"){return '<details><summary>Plot (static fallback — spec retained)</summary><pre class="code">'+esc(JSON.stringify(p.spec||{},null,2))+'</pre></details>'}
  if(ev.kind==="terminal"){
    if(p.output){return '<pre class="term">'+esc(p.output)+'</pre>'}
    var cmd="$ "+(Array.isArray(p.argv)?p.argv.join(" "):String(p.argv||""));
    return '<pre class="term">'+esc(cmd)+'</pre><p class="muted">Recorded process block — attach a broker for a live PTY.</p>';
  }
  if(ev.kind==="component"){return '<div class="muted" role="note">Interactive component <code>'+esc(p.component_type||"")+'</code> — recorded fallback in static mode.</div>'}
  if(ev.kind==="error"){return '<p role="alert"><strong>Error:</strong> '+esc(p.message||"")+'</p>'}
  return ""
}
function render(){
  var s=steps[idx];
  var h="";
  // The final step owns the tail: outputs of the last source line (and crash
  // errors) have no later step to attach to, so they join the last step.
  // Anything at or before a `clear` event is dropped from outputs/inspects.
  var endSeq=(!s||idx>=steps.length-1)?Infinity:s.seq;
  var clearSeq=-1,i;
  for(i=0;i<events.length;i++){if(events[i].kind==="clear"&&events[i].seq<=endSeq&&events[i].seq>clearSeq){clearSeq=events[i].seq}}
  var upto=events.filter(function(e){return e.kind!=="step"&&e.kind!=="clear"&&e.kind!=="inspect"&&e.kind!=="session_start"&&e.kind!=="session_end"&&e.kind!=="snapshot"&&e.seq<=endSeq&&e.seq>clearSeq});
  var p=(s&&s.payload)||{};
  var loc=(p.func||"")+" @ line "+(p.line||"?");
  if(s){h+='<p class="muted">'+esc(loc)+'</p>'}
  var locals=p.locals||{};
  var keys=Object.keys(locals);
  if(keys.length){h+='<details open><summary>Environment ('+keys.length+')</summary><pre class="code">'+esc(keys.map(function(k){return k+" = "+locals[k]}).join("\\n"))+'</pre></details>'}
  upto.forEach(function(ev){h+=renderOutput(ev)});
  var insp=events.filter(function(e){return e.kind==="inspect"&&e.seq<=endSeq&&e.seq>clearSeq}).slice(-8);
  if(insp.length){h+='<details><summary>Inspected values</summary><pre class="code">'+esc(insp.map(function(e){return (e.payload.name||"?")+" = "+(e.payload.summary||"")}).join("\\n"))+'</pre></details>'}
  stage.innerHTML=h||'<p class="muted">No content recorded.</p>';
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
document.addEventListener("keydown",function(e){
  if(e.target&&e.target.closest&&e.target.closest('input,textarea,select,button,a,[contenteditable=true],[role=slider]'))return;
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
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src http: https: data: blob:; media-src http: https: data: blob:; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-src 'none'; object-src 'none'">
<title>{html.escape(title)}</title>
<style>{VIEWER_CSS}</style>
</head>
<body>
<header class="top"><h1>{html.escape(title)}</h1><span class="muted">static replay · lectpy v0.1</span></header>
<div id="stepbar" role="toolbar" aria-label="Lecture stepping">
<button id="prev" aria-label="Previous step">← Back</button>
<button id="next" aria-label="Next step">Forward →</button>
<button id="over" aria-label="Step over">Step over</button>
<span id="pos" aria-live="off"></span>
<span id="meta" class="muted" role="status" aria-live="polite"></span>
</div>
<main id="stage" tabindex="0" aria-label="Lecture stage"></main>
<p class="muted">Keyboard: ←/→ step, Home/End first/last. Step is deep-linked via <code>?step=N</code>. Reduced-motion respected. Plots/components show recorded fallbacks.</p>
<script id="lecture-data" type="application/json">{embedded}</script>
<script>{VIEWER_JS}</script>
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
    (out / "lecture.json").write_text(json.dumps(bundle, indent=2), encoding="utf-8")

    # Copy referenced blobs (relative links only — no absolute host paths).
    if ctx.artifacts is not None:
        for item in events:
            for ref in item.get("artifact_refs", []):
                try:
                    data = ctx.artifacts.get(ref)
                except (KeyError, ValueError):
                    continue
                hexpart = ref.split(":", 1)[1]
                dest = out / "artifacts" / hexpart
                if not dest.exists():
                    dest.write_bytes(data)

    (out / "index.html").write_text(_viewer_html(manifest.title, bundle), encoding="utf-8")
    return out
