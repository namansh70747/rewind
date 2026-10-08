"""Offline cluster map with point inspection; no external assets or telemetry."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


def render_fleet(report: dict[str, Any], path: Path) -> None:
    data = (
        json.dumps(report).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'"><title>Rewind / Fleet evidence</title>
<style>body{background:#101413;color:#edf2e9;font:16px system-ui;margin:4vw}h1{font-size:38px}p{color:#b1bfb4}svg{width:100%;max-width:950px;height:auto;border:1px solid #303b35;border-radius:12px;background:#191f1d}circle{cursor:pointer;stroke:#edf2e9;stroke-width:1}circle:focus{stroke:#ff864e;stroke-width:4}pre{white-space:pre-wrap;padding:20px;background:#191f1d}button{background:#233529;color:white;padding:10px;border:1px solid #536654;margin:4px;cursor:pointer}</style>
<h1>Failure map</h1><p>Explore event similarity. Clusters are exploratory; a human must validate their meaning. Cluster -1 means noise.</p><p id="qualification"></p><div id="filters"></div><svg viewBox="0 0 950 450" id="map" aria-label="Failure cluster map"></svg><pre id="clusterSummary">Cluster summaries, when supplied, are unverified model suggestions.</pre><pre id="detail">Select a point to inspect its run ID and cluster.</pre><p id="method"></p>
<script type="application/json" id="data">__DATA__</script><script>'use strict';const d=JSON.parse(document.getElementById('data').textContent),pts=d.points,ns='http://www.w3.org/2000/svg',svg=document.getElementById('map');const colors=['#ff864e','#9cdeaf','#a4b8ef','#dcadea','#ffe59b'];const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);function scale(v,a,size){const lo=Math.min(...a),hi=Math.max(...a);return 30+(v-lo)/(hi-lo||1)*size}for(const p of pts){const c=document.createElementNS(ns,'circle');c.setAttribute('cx',scale(p.x,xs,890));c.setAttribute('cy',scale(p.y,ys,390));c.setAttribute('r',9);c.setAttribute('fill',p.cluster<0?'#667268':colors[p.cluster%colors.length]);c.setAttribute('tabindex','0');c.setAttribute('role','button');c.setAttribute('aria-label',`Run ${p.id}, cluster ${p.cluster}`);c.dataset.cluster=p.cluster;c.onclick=()=>document.getElementById('detail').textContent=JSON.stringify(p,null,2);c.onkeydown=e=>{if(e.key==='Enter')c.onclick()};svg.appendChild(c)}for(const cluster of ['all',...new Set(pts.map(p=>p.cluster))]){const b=document.createElement('button');b.textContent=cluster==='all'?'All runs':`Cluster ${cluster}`;b.onclick=()=>{document.getElementById('clusterSummary').textContent=cluster==='all'?'Select a cluster to inspect its optional summary.':JSON.stringify((d.summaries||{})[String(cluster)]||{note:'No model summary available'},null,2);for(const c of svg.children)c.style.display=cluster==='all'||String(cluster)===c.dataset.cluster?'':'none'};document.getElementById('filters').appendChild(b)}document.getElementById('qualification').textContent=d.qualification||'Input provenance: supplied recordings; quality requires human review.';document.getElementById('method').textContent=`${d.embedding||d.model} · ${d.projection||'UMAP'} · human evaluation: ${d.human_evaluation}`;</script></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html.replace("__DATA__", data), encoding="utf-8")
