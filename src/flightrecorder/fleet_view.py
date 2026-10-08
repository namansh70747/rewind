"""Offline cluster map, nearest neighbors and bounded timeline drilldown."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def render_fleet(report: dict[str, Any], path: Path) -> None:
    data = (
        json.dumps(report).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    html = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'">
<title>Rewind / Fleet evidence</title>
<style>
body{background:#101413;color:#edf2e9;font:16px system-ui;margin:4vw;max-width:1400px}
h1{font-size:38px}p{color:#b1bfb4;line-height:1.6}svg{width:100%;max-width:950px;height:auto;border:1px solid #303b35;border-radius:12px;background:#191f1d}
circle{cursor:pointer;stroke:#edf2e9;stroke-width:1}circle:focus,circle[aria-pressed=true]{stroke:#ff864e;stroke-width:4}
pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:20px;background:#191f1d}
button{background:#233529;color:white;padding:10px;border:1px solid #536654;margin:4px;cursor:pointer;border-radius:6px}
button:focus-visible,summary:focus-visible{outline:3px solid #ff864e;outline-offset:3px}
button[aria-pressed=true]{background:#435e47}details{border-bottom:1px solid #303b35;padding:12px 0}summary{cursor:pointer;overflow-wrap:anywhere}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}.columns>*{min-width:0}
@media(max-width:700px){.columns{display:block}h1{font-size:30px}}
</style>
<h1>Failure map</h1><p>Explore event similarity. Clusters are exploratory; a human must validate their meaning. Cluster -1 means noise.</p>
<p id="qualification"></p><div id="filters" aria-label="Cluster filters"></div>
<svg viewBox="0 0 950 450" id="map" aria-label="Failure cluster map"></svg>
<pre id="clusterSummary">Cluster summaries, when supplied, are unverified model suggestions.</pre>
<div class="columns"><section><h2>Selected run</h2><pre id="detail" aria-live="polite">Select a point or a run below.</pre></section>
<section><h2>Nearest runs</h2><p id="metric"></p><div id="neighbors"></div></section></div>
<section><h2>Runs in selected cluster</h2><div id="runs"></div></section>
<section><h2>Boundary timeline</h2><p id="timelineNote">Select a run to inspect recorded boundaries.</p><div id="timeline"></div></section>
<p id="method"></p>
<script type="application/json" id="data">__DATA__</script><script>
'use strict';
const $=id=>document.getElementById(id), d=JSON.parse($('data').textContent), pts=d.points,
ns='http://www.w3.org/2000/svg', svg=$('map'), colors=['#ff864e','#9cdeaf','#a4b8ef','#dcadea','#ffe59b'];
const byId=new Map(pts.map(p=>[p.id,p]));
const bounds=pts.reduce((a,p)=>[Math.min(a[0],p.x),Math.max(a[1],p.x),Math.min(a[2],p.y),Math.max(a[3],p.y)],[Infinity,-Infinity,Infinity,-Infinity]);
function scale(v,lo,hi,size){return 30+(v-lo)/(hi-lo||1)*size}
function button(label,action){const b=document.createElement('button');b.textContent=label;b.onclick=action;return b}
function select(id){
 const p=byId.get(id);if(!p)return;
 $('detail').textContent=JSON.stringify(p,null,2);
 for(const c of svg.children)c.setAttribute('aria-pressed',String(c.dataset.id===id));
 $('neighbors').replaceChildren();
 for(const n of (d.neighbors||{})[id]||[]){
  $('neighbors').appendChild(button(`${n.id} · distance ${n.distance.toFixed(4)}`,()=>select(n.id)));
 }
 if(!$('neighbors').children.length)$('neighbors').textContent='No neighbors included in this report. Rebuild the index to include them.';
 const t=(d.timelines||{})[id];$('timeline').replaceChildren();
 if(!t){$('timelineNote').textContent='No timeline included in this report. Rebuild the index to include it.';return}
 $('detail').textContent=JSON.stringify({...p,features:t.features||null},null,2);
 $('timelineNote').textContent=`Run ${id}: showing ${t.events.length} of ${t.total_events} boundaries. Payload previews are redacted and limited to 4,000 characters. Full evidence remains in the local recording.`;
 for(const e of t.events){
  const row=document.createElement('details'),title=document.createElement('summary'),body=document.createElement('pre');
  title.textContent=`#${e.seq} · ${e.kind} · ${e.key}`;
  body.textContent=`Request\n${e.request}\n\nResponse\n${e.response}`;
  row.append(title,body);$('timeline').appendChild(row);
 }
}
for(const p of pts){
 const c=document.createElementNS(ns,'circle');c.setAttribute('cx',scale(p.x,bounds[0],bounds[1],890));c.setAttribute('cy',scale(p.y,bounds[2],bounds[3],390));
 c.setAttribute('r',9);c.setAttribute('fill',p.cluster<0?'#667268':colors[p.cluster%colors.length]);c.setAttribute('tabindex','0');c.setAttribute('role','button');
 c.setAttribute('aria-label',`Run ${p.id}, cluster ${p.cluster}`);c.setAttribute('aria-pressed','false');c.dataset.cluster=p.cluster;c.dataset.id=p.id;
 c.onclick=()=>select(p.id);c.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(p.id)}};svg.appendChild(c);
}
function filter(cluster){
 $('clusterSummary').textContent=cluster==='all'?'Select a cluster to inspect its optional summary.':JSON.stringify((d.summaries||{})[String(cluster)]||{note:'No model summary available'},null,2);
 for(const c of svg.children)c.style.display=cluster==='all'||String(cluster)===c.dataset.cluster?'':'none';
 for(const b of $('filters').children)b.setAttribute('aria-pressed',String(b.dataset.cluster===String(cluster)));
 $('runs').replaceChildren();for(const p of pts.filter(p=>cluster==='all'||p.cluster===cluster))$('runs').appendChild(button(p.id,()=>select(p.id)));
}
for(const cluster of ['all',...new Set(pts.map(p=>p.cluster))]){
 const b=button(cluster==='all'?'All runs':`Cluster ${cluster}`,()=>filter(cluster));b.dataset.cluster=cluster;$('filters').appendChild(b);
}
filter('all');
$('metric').textContent=d.neighbor_metric||'No neighbor metric supplied.';
$('qualification').textContent=d.qualification||'Input provenance: supplied recordings; quality requires human review.';
$('method').textContent=`${d.embedding||d.model} · ${d.projection||'UMAP'} · human evaluation: ${d.human_evaluation}`;
</script></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html.replace("__DATA__", data), encoding="utf-8")
