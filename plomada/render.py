"""render — property-graph → un HTML autocontenido, estilo Google, con drill-down.

Sin CDNs ni dependencias: CSS + Vanilla JS + SVG embebidos. La vista navega de
arquitectura (paquetes → módulos, aristas `import`) hasta el DFD (funciones de un
módulo, aristas `call`). Layout determinista (grid ordenado por id). El grafo se
embebe como JSON; toda la interacción es client-side.
"""
import html
import json


def render_html(graph, title="plomada"):
    data = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    return _TEMPLATE.replace("/*__DATA__*/", data).replace("__TITLE__", html.escape(title))


_TEMPLATE = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>plomada · __TITLE__</title>
<style>
:root{--bg:#f8f9fa;--panel:#fff;--ink:#202124;--dim:#5f6368;--line:#dadce0;
--blue:#1a73e8;--pkg:#e8f0fe;--pkgL:#1a73e8;--mod:#e6f4ea;--modL:#188038;
--cls:#fef7e0;--clsL:#e37400;--fn:#f1f3f4;--fnL:#5f6368;--mtd:#fce8e6;--mtdL:#c5221f;}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:14px/1.4 "Google Sans",Roboto,system-ui,sans-serif;display:flex;flex-direction:column}
header{background:var(--panel);border-bottom:1px solid var(--line);padding:12px 20px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
header h1{font-size:18px;font-weight:500;margin:0;color:var(--blue)}
#crumbs{display:flex;gap:6px;align-items:center;flex-wrap:wrap;font-size:13px}
#crumbs a{color:var(--blue);cursor:pointer;text-decoration:none}#crumbs span.sep{color:var(--dim)}
#stats{margin-left:auto;color:var(--dim);font-size:12px;display:flex;gap:14px}
#stats b{color:var(--ink);font-weight:500}
svg{display:block}
.node{cursor:pointer}
.node rect,.node path,.node polygon{stroke-width:1.5;transition:filter .12s}
.node:hover rect,.node:hover polygon,.node:hover path{filter:brightness(.97)}
.node.has-children rect{stroke-dasharray:none}
.node text.t{font-weight:500;font-size:13px}
.node text.s{font-size:11px;fill:var(--dim)}
.kind-package rect{fill:var(--pkg);stroke:var(--pkgL)}
.kind-module rect{fill:var(--mod);stroke:var(--modL)}
.kind-class rect{fill:var(--cls);stroke:var(--clsL)}
.kind-function rect{fill:var(--fn);stroke:var(--fnL)}
.kind-method rect{fill:var(--mtd);stroke:var(--mtdL)}
.kind-assign rect,.kind-process rect{fill:#f1f3f4;stroke:#9aa0a6}
.kind-start rect,.kind-end rect{fill:#e8f0fe;stroke:#1a73e8}
.kind-decision polygon{fill:#fef7e0;stroke:#e37400}
.kind-read polygon,.kind-write polygon{fill:#e6f4ea;stroke:#188038}
.kind-call rect{fill:#f1f3f4;stroke:#5f6368}
.kind-loop polygon{fill:#fce8e6;stroke:#c5221f}
.kind-return rect{fill:#fce8e6;stroke:#c5221f}
.edge.data_flow{stroke:#9334e6;opacity:.55}
/* Gane-Sarson por rol (gana sobre kind-* para nodos statement) */
.role-process rect{fill:#e8f0fe;stroke:#1a73e8}
.role-store path,.role-store rect{fill:#fef7e0;stroke:#e37400;stroke-width:1.8}
.role-external rect{fill:#e6f4ea;stroke:#188038}
.flowlabel{fill:#9334e6;font-size:10px;text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:3px}
.node.inloop rect,.node.inloop path,.node.inloop polygon{stroke-dasharray:5 3}  /* dentro de un loop (anotación, no nodo) */
.shadow{fill:#9aa0a6;opacity:.35}                          /* sombra de entidad externa (Gane-Sarson) */
.divider{stroke:#888;stroke-width:1}                       /* franja de proceso / compartimento de almacén */
.dfdnum{font-size:10px;font-weight:700;fill:#5f6368}       /* nº de proceso (1,2…) / id de almacén (D1…) */
.edge{fill:none;stroke:var(--dim);stroke-width:1.4;marker-end:url(#arrow);opacity:.45}
.edge.import{stroke:var(--modL)}.edge.call{stroke:var(--blue)}
.edge.unresolved{stroke-dasharray:4 3;opacity:.3}
.edge.loop{stroke:#c5221f;stroke-width:2.2;opacity:.9;marker-end:url(#arrowLoop)}
.node.recursive rect{stroke:#c5221f;stroke-width:2.5}
.node.sel rect,.node.sel polygon{stroke-width:3.5}
.edge.hot{opacity:1;stroke-width:2.4}
.node text.loop{fill:#c5221f;font-size:14px;font-weight:700}
#empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--dim);pointer-events:none}
#empty[hidden]{display:none}
#legend{position:fixed;right:336px;bottom:16px;background:var(--panel);border:1px solid var(--line);
border-radius:8px;padding:10px 12px;font-size:12px;box-shadow:0 1px 3px rgba(0,0,0,.1);z-index:9}
#legend div{display:flex;align-items:center;gap:6px;margin:3px 0}
#legend i{width:12px;height:12px;border-radius:3px;display:inline-block;border:1px solid}

/* Estilos de toggle, panel lateral y etiquetas */
#view-toggle-container{display:none;background:var(--bg);border:1px solid var(--line);border-radius:20px;padding:2px;gap:2px;margin:0 12px}
.toggle-btn{border:none;background:transparent;padding:6px 14px;border-radius:18px;cursor:pointer;font-size:12px;font-weight:500;color:var(--dim);transition:all .2s ease}
.toggle-btn.active{background:var(--panel);color:var(--blue);box-shadow:0 1px 3px rgba(0,0,0,.1)}
.control-label{fill:var(--dim);font-size:10px;font-weight:500;text-anchor:middle;paint-order:stroke;stroke:var(--bg);stroke-width:4px}

#workspace{flex:1;display:flex;position:relative;overflow:hidden}
#stage{flex:1;position:relative;overflow:auto}
#doc-panel{width:320px;background:var(--panel);border-left:1px solid var(--line);display:flex;flex-direction:column;box-shadow:-2px 0 6px rgba(0,0,0,.04);z-index:10;transition:width .2s ease,opacity .2s ease}
#doc-panel.collapsed{width:0;opacity:0;pointer-events:none;border-left:none}
.panel-header{padding:14px 18px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between}
.panel-header h2{font-size:15px;font-weight:500;margin:0;color:var(--blue)}
.close-btn{background:transparent;border:none;font-size:20px;cursor:pointer;color:var(--dim);line-height:1;padding:0}
#panel-content{padding:18px;overflow-y:auto;flex:1;font-size:13px;line-height:1.5}
.doc-section{margin-bottom:20px}
.doc-section h3{font-size:11px;font-weight:700;text-transform:uppercase;color:var(--dim);margin:0 0 8px 0;letter-spacing:.5px}
.docstring{background:#f8f9fa;border-left:3px solid var(--blue);padding:8px 12px;border-radius:0 4px 4px 0;white-space:pre-wrap;font-family:inherit;margin:0}
.signature-box{background:#f1f3f4;border-radius:6px;padding:10px;font-family:monospace;font-size:12px;overflow-x:auto;border:1px solid var(--line)}
.sig-param{margin-bottom:4px}
.sig-param:last-child{margin-bottom:0}
.sig-param-name{color:var(--ink);font-weight:700}
.sig-param-type{color:#c5221f}
.sig-param-default{color:var(--dim)}
.sig-returns{margin-top:8px;border-top:1px solid var(--line);padding-top:6px;font-weight:700}
.adr-badge-list{display:flex;flex-wrap:wrap;gap:6px}
.adr-badge{background:#fce8e6;color:#c5221f;border:1px solid #c5221f;padding:4px 8px;border-radius:4px;font-weight:700;font-size:11px}
</style></head><body>
<header>
  <h1>plomada</h1>
  <nav id="crumbs"></nav>
  <div id="view-toggle-container"></div>
  <div id="stats"></div>
</header>
<div id="workspace">
  <div id="stage"><svg id="svg"></svg><div id="empty" hidden>Vacío</div></div>
  <aside id="doc-panel">
    <div class="panel-header">
      <h2 id="panel-title">Detalles</h2>
      <button class="close-btn" onclick="closePanel()">&times;</button>
    </div>
    <div id="panel-content"></div>
  </aside>
</div>
<div id="legend"></div>
<script>
const G = /*__DATA__*/;
const SVGNS="http://www.w3.org/2000/svg";
const byId={}; G.nodes.forEach(n=>byId[n.id]=n);
const childrenOf={}; G.nodes.forEach(n=>childrenOf[n.id]=[]);
G.nodes.forEach(n=>{ if(n.parent_id && childrenOf[n.parent_id]) childrenOf[n.parent_id].push(n.id); });
Object.values(childrenOf).forEach(a=>a.sort());
const ROOT = G.nodes.find(n=>n.level==="package" && !n.parent_id);
let focus = ROOT ? ROOT.id : null;
let selected = null;
let currentGraphType = "flow";
let panelCollapsed = false;

window.closePanel = function() {
  panelCollapsed = true;
  document.getElementById("doc-panel").classList.add("collapsed");
};

window.openPanel = function() {
  panelCollapsed = false;
  document.getElementById("doc-panel").classList.remove("collapsed");
  updatePanel();
};

window.setGraphType = function(type) {
  currentGraphType = type;
  draw();
};

const KIND={package:"paquete",module:"módulo",class:"clase",function:"función",method:"método",
  statement:"sentencia",assign:"asignación",loop:"loop",branch:"rama",return:"return",call:"llamada",expr:"expr",
  store:"almacén",parameter:"parámetro",iterate:"bucle",start:"inicio",end:"fin",decision:"decisión",read:"lectura",write:"escritura"};
const NW=210, NH=52, GAPX=46, GAPY=70, PAD=40;

function ancestors(id){const out=[];let c=byId[id];while(c){out.unshift(c);c=c.parent_id?byId[c.parent_id]:null;}return out;}

function visibleEdges(ids){
  const set=new Set(ids), out=[];
  for(const e of G.edges){
    if(e.type==="contains") continue;
    if(set.has(e.src)&&set.has(e.dst)){
      if (!e.graph_type || e.graph_type === currentGraphType) {
        out.push(e);
      }
    }
  }
  return out;
}

function formatCompactSignature(sig) {
  if (!sig || !sig.params) return "";
  const pList = sig.params.map(p => p.name).join(", ");
  const ret = sig.returns ? ` -> ${sig.returns}` : "";
  const fullSig = `(${pList})${ret}`;
  if (fullSig.length > 26) {
    const shortParams = sig.params.map(p => p.name).slice(0, 2).join(", ");
    return `(${shortParams}, ...)${ret}`;
  }
  return fullSig;
}

function updatePanel() {
  const panel = document.getElementById("doc-panel");
  const content = document.getElementById("panel-content");
  const title = document.getElementById("panel-title");
  
  if (panelCollapsed) {
    panel.classList.add("collapsed");
    return;
  } else {
    panel.classList.remove("collapsed");
  }
  
  const fNode = byId[focus];
  const sNode = selected ? byId[selected] : null;
  let html = "";
  
  if (sNode) {
    title.textContent = `Detalles de Sentencia (L${sNode.line})`;
    html += `<div class="doc-section">
      <h3>Tipo</h3>
      <div><b>${KIND[sNode.kind] || sNode.kind}</b></div>
    </div>`;
    
    if (sNode.label) {
      html += `<div class="doc-section">
        <h3>Expresión</h3>
        <div style="font-family:monospace; background:#f8f9fa; padding:8px; border-radius:4px; border:1px solid var(--line); white-space:pre-wrap; word-break:break-all;">${sNode.label}</div>
      </div>`;
    }
    
    if (sNode.comment) {
      html += `<div class="doc-section">
        <h3>Comentario</h3>
        <div class="docstring" style="border-left-color: var(--blue)">${sNode.comment}</div>
      </div>`;
    }
    
    if (sNode.adrs && sNode.adrs.length > 0) {
      html += `<div class="doc-section">
        <h3>ADRs Relacionados</h3>
        <div class="adr-badge-list">
          ${sNode.adrs.map(adr => `<span class="adr-badge">${adr}</span>`).join("")}
        </div>
      </div>`;
    }
    
    if (fNode && (fNode.kind === "function" || fNode.kind === "method")) {
      html += `<hr style="border:0; border-top:1px dashed var(--line); margin:20px 0" />`;
      html += `<div style="color:var(--dim); font-size:10px; font-weight:700; text-transform:uppercase; margin-bottom:8px">Función Contenedora: ${fNode.label}</div>`;
      if (fNode.doc) {
        html += `<div class="doc-section">
          <h3>Docstring</h3>
          <pre class="docstring">${fNode.doc}</pre>
        </div>`;
      }
    }
  } else if (fNode) {
    title.textContent = fNode.label || fNode.id;
    html += `<div class="doc-section">
      <h3>Tipo</h3>
      <div><b>${KIND[fNode.kind] || fNode.kind}</b></div>
    </div>`;
    
    if (fNode.doc) {
      html += `<div class="doc-section">
        <h3>Documentación</h3>
        <pre class="docstring">${fNode.doc}</pre>
      </div>`;
    }
    
    if (fNode.signature && fNode.signature.params) {
      html += `<div class="doc-section">
        <h3>Firma de Tipos</h3>
        <div class="signature-box">`;
      if (fNode.signature.params.length === 0) {
        html += `<div>(sin parámetros)</div>`;
      } else {
        fNode.signature.params.forEach(p => {
          let pStr = `<div class="sig-param">`;
          pStr += `<span class="sig-param-name">${p.name}</span>`;
          if (p.type) pStr += `: <span class="sig-param-type">${p.type}</span>`;
          if (p.default) pStr += ` = <span class="sig-param-default">${p.default}</span>`;
          pStr += `</div>`;
          html += pStr;
        });
      }
      if (fNode.signature.returns) {
        html += `<div class="sig-returns">Retorno: <span class="sig-param-type">${fNode.signature.returns}</span></div>`;
      }
      html += `</div></div>`;
    }
    
    if (fNode.adrs && fNode.adrs.length > 0) {
      html += `<div class="doc-section">
        <h3>ADRs del Componente</h3>
        <div class="adr-badge-list">
          ${fNode.adrs.map(adr => `<span class="adr-badge">${adr}</span>`).join("")}
        </div>
      </div>`;
    }
    
    if (fNode.comment) {
      html += `<div class="doc-section">
        <h3>Nota de Código</h3>
        <div class="docstring" style="border-left-color: var(--blue)">${fNode.comment}</div>
      </div>`;
    }
  } else {
    title.textContent = "Sin selección";
    html = `<div style="color:var(--dim); text-align:center; margin-top:40px">Selecciona un elemento para ver su documentación o comentarios.</div>`;
  }
  content.innerHTML = html;
}

function draw(){
  const svg=document.getElementById("svg"); svg.innerHTML="";
  const allKids=(childrenOf[focus]||[]).map(id=>byId[id]);
  const hasGraphType = allKids.some(n => n.graph_type);
  
  // Toggle visibility
  const viewToggle = document.getElementById("view-toggle-container");
  if (hasGraphType) {
    viewToggle.style.display = "flex";
    viewToggle.innerHTML = `
      <button class="toggle-btn ${currentGraphType==='flow'?'active':''}" onclick="setGraphType('flow')">Flujo de control (Flowchart)</button>
      <button class="toggle-btn ${currentGraphType==='dfd'?'active':''}" onclick="setGraphType('dfd')">Flujo de datos (DFD)</button>
    `;
  } else {
    viewToggle.style.display = "none";
  }

  let kids = allKids;
  if (hasGraphType) {
    kids = allKids.filter(n => n.graph_type === currentGraphType);
  }

  document.getElementById("empty").hidden = kids.length>0;
  // crumbs
  const cr=document.getElementById("crumbs"); cr.innerHTML="";
  ancestors(focus).forEach((n,i,arr)=>{
    const a=document.createElement("a"); a.textContent=n.label||n.id; a.onclick=()=>{focus=n.id;selected=null;draw();};
    cr.appendChild(a);
    if(i<arr.length-1){const s=document.createElement("span");s.className="sep";s.textContent="›";cr.appendChild(s);}
  });
  // stats
  const st=G.stats||{};
  document.getElementById("stats").innerHTML =
    `<span><b>${st.packages??""}</b> paquetes</span><span><b>${st.modules??""}</b> módulos</span>`+
    `<span><b>${st.functions??""}</b> funciones</span><span><b>${st.calls??""}</b> llamadas</span>`+
    (st.loops?`<span style="color:#c5221f"><b>${st.loops}</b> loops · ${st.recursive_functions} recursivas</span>`:"");
  // defs (arrows: normal + loop)
  const defs=document.createElementNS(SVGNS,"defs");
  defs.innerHTML='<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#5f6368"/></marker>'+
    '<marker id="arrowLoop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#c5221f"/></marker>';
  svg.appendChild(defs);
  
  // layout orientado al flujo (determinista)
  const nodeIds = kids.map(n => n.id);
  const edges = visibleEdges(nodeIds);

  const adj = {};
  const rev_adj = {};
  const inDegree = {};
  const outDegree = {};
  
  nodeIds.forEach(id => {
    adj[id] = [];
    rev_adj[id] = [];
    inDegree[id] = 0;
    outDegree[id] = 0;
  });

  edges.forEach(e => {
    if (adj[e.src] && adj[e.dst]) {
      adj[e.src].push(e.dst);
      rev_adj[e.dst].push(e.src);
      inDegree[e.dst]++;
      outDegree[e.src]++;
    }
  });

  const visited = new Set();
  const recStack = new Set();
  const backEdges = new Set();

  function dfs(u) {
    visited.add(u);
    recStack.add(u);
    const neighbors = [...adj[u]].sort();
    for (const v of neighbors) {
      if (recStack.has(v)) {
        backEdges.add(u + "->" + v);
      } else if (!visited.has(v)) {
        dfs(v);
      }
    }
    recStack.delete(u);
  }

  const dfsSources = nodeIds.filter(id => inDegree[id] === 0).sort();
  dfsSources.forEach(u => {
    if (!visited.has(u)) dfs(u);
  });
  nodeIds.sort().forEach(u => {
    if (!visited.has(u)) dfs(u);
  });

  const dagAdj = {};
  const dagInDegree = {};
  nodeIds.forEach(id => {
    dagAdj[id] = [];
    dagInDegree[id] = 0;
  });
  edges.forEach(e => {
    if (adj[e.src] && adj[e.dst]) {
      if (!backEdges.has(e.src + "->" + e.dst)) {
        dagAdj[e.src].push(e.dst);
        dagInDegree[e.dst]++;
      }
    }
  });

  const layers = {};
  const queue = [];
  nodeIds.forEach(id => {
    layers[id] = 0;
    if (dagInDegree[id] === 0) {
      queue.push(id);
    }
  });

  while (queue.length > 0) {
    queue.sort();
    const u = queue.shift();
    const uLayer = layers[u];
    for (const v of dagAdj[u]) {
      layers[v] = Math.max(layers[v], uLayer + 1);
      dagInDegree[v]--;
      if (dagInDegree[v] === 0) {
        queue.push(v);
      }
    }
  }

  kids.forEach(n => {
    if (n.dfd_role === "store") {
      const connectedProcIds = [];
      edges.forEach(e => {
        if (e.src === n.id && byId[e.dst] && byId[e.dst].dfd_role === "process") {
          connectedProcIds.push(e.dst);
        }
        if (e.dst === n.id && byId[e.src] && byId[e.src].dfd_role === "process") {
          connectedProcIds.push(e.src);
        }
      });
      if (connectedProcIds.length > 0) {
        connectedProcIds.sort();
        const targetProcId = connectedProcIds[0];
        layers[n.id] = layers[targetProcId];
      }
    }
  });

  let maxLayer = 0;
  nodeIds.forEach(id => {
    if (layers[id] > maxLayer) maxLayer = layers[id];
  });

  kids.forEach(n => {
    const isReturn = n.kind === "return";
    const isExtSink = n.dfd_role === "external" && outDegree[n.id] === 0 && inDegree[n.id] > 0;
    if (isReturn || isExtSink) {
      layers[n.id] = maxLayer + 1;
    }
  });

  const uniqueLayers = [...new Set(Object.values(layers))].sort((a, b) => a - b);
  const layerMap = {};
  uniqueLayers.forEach((l, idx) => {
    layerMap[l] = idx;
  });
  nodeIds.forEach(id => {
    layers[id] = layerMap[layers[id]];
  });

  const totalLayers = uniqueLayers.length;
  const layerNodes = [];
  for (let i = 0; i < totalLayers; i++) {
    layerNodes.push([]);
  }
  nodeIds.forEach(id => {
    layerNodes[layers[id]].push(id);
  });

  layerNodes.forEach(nodesInLayer => {
    nodesInLayer.sort();
  });

  function getPositionMap() {
    const posInLayer = {};
    layerNodes.forEach((nodesInLayer, layerIdx) => {
      nodesInLayer.forEach((id, idx) => {
        posInLayer[id] = idx;
      });
    });
    return posInLayer;
  }

  const sweeps = 4;
  for (let sweep = 0; sweep < sweeps; sweep++) {
    const posInLayer = getPositionMap();

    for (let i = 1; i < layerNodes.length; i++) {
      const nodes = layerNodes[i];
      const baricenters = {};
      nodes.forEach(u => {
        const preds = (rev_adj[u] || []).filter(v => layers[v] === i - 1);
        if (preds.length > 0) {
          const sum = preds.reduce((acc, v) => acc + posInLayer[v], 0);
          baricenters[u] = sum / preds.length;
        } else {
          baricenters[u] = -1;
        }
      });

      nodes.sort((a, b) => {
        const ba = baricenters[a];
        const bb = baricenters[b];
        if (ba !== bb) {
          if (ba === -1) return 1;
          if (bb === -1) return -1;
          return ba - bb;
        }
        return a.localeCompare(b);
      });
    }

    for (let i = layerNodes.length - 2; i >= 0; i--) {
      const nodes = layerNodes[i];
      const baricenters = {};
      nodes.forEach(u => {
        const succs = (adj[u] || []).filter(v => layers[v] === i + 1);
        if (succs.length > 0) {
          const sum = succs.reduce((acc, v) => acc + posInLayer[v], 0);
          baricenters[u] = sum / succs.length;
        } else {
          baricenters[u] = -1;
        }
      });

      nodes.sort((a, b) => {
        const ba = baricenters[a];
        const bb = baricenters[b];
        if (ba !== bb) {
          if (ba === -1) return 1;
          if (bb === -1) return -1;
          return ba - bb;
        }
        return a.localeCompare(b);
      });
    }
  }

  const maxCols = Math.max(...layerNodes.map(a => a.length), 1);
  const pos = {};
  const svgW = Math.max(window.innerWidth - 340, PAD * 2 + maxCols * (NW + GAPX) - GAPX);

  layerNodes.forEach((nodesInLayer, layerIdx) => {
    const nInLayer = nodesInLayer.length;
    const layerW = nInLayer * NW + (nInLayer - 1) * GAPX;
    const startX = (svgW - layerW) / 2;

    nodesInLayer.forEach((id, colIdx) => {
      pos[id] = {
        x: startX + colIdx * (NW + GAPX),
        y: PAD + layerIdx * (NH + GAPY)
      };
    });
  });

  svg.setAttribute("width", svgW);
  svg.setAttribute("height", Math.max(300, PAD * 2 + layerNodes.length * (NH + GAPY) - GAPY));

  // edges
  const ids=kids.map(n=>n.id);
  const vEdges = visibleEdges(ids);
  
  for(const e of vEdges){
    const a=pos[e.src],b=pos[e.dst]; if(!a||!b)continue;
    
    const isBackEdge = backEdges.has(e.src + "->" + e.dst);
    let pathD = "";
    let lx, ly;
    
    if (isBackEdge) {
      // Salida por la izquierda, entrada por la izquierda
      const x1 = a.x;
      const y1 = a.y + NH / 2;
      const x2 = b.x;
      const y2 = b.y + NH / 2;
      const offset = 50;
      
      pathD = `M${x1} ${y1} C ${x1 - offset} ${y1} ${x2 - offset} ${y2} ${x2} ${y2}`;
      lx = Math.min(x1, x2) - offset;
      ly = (y1 + y2) / 2;
    } else {
      const x1=a.x+NW/2,y1=a.y+NH,x2=b.x+NW/2,y2=b.y;
      const my=(y1+y2)/2;
      
      pathD = `M${x1} ${y1} C ${x1} ${my} ${x2} ${my} ${x2} ${y2}`;
      lx = x1 + (x2 - x1) * 0.35;
      ly = y1 + (y2 - y1) * 0.35;
    }
    
    const p=document.createElementNS(SVGNS,"path");
    p.setAttribute("d", pathD);
    const isLoopEdge = isBackEdge || e.in_cycle;
    p.setAttribute("class","edge "+e.type+(e.resolved===false?" unresolved":"")+(isLoopEdge?" loop":""));
    p.dataset.src=e.src;p.dataset.dst=e.dst;
    svg.appendChild(p);
    
    if (e.label) {
      const lab = document.createElementNS(SVGNS, "text");
      lab.setAttribute("class", "control-label");
      lab.setAttribute("x", lx);
      lab.setAttribute("y", ly + 4);
      lab.textContent = e.label;
      svg.appendChild(lab);
    }
    
    if(e.type==="data_flow"&&e.var){
      const lab=document.createElementNS(SVGNS,"text");
      lab.setAttribute("class","flowlabel");
      let dx, dy;
      if (isBackEdge) {
        dx = lx; dy = ly;
      } else {
        const x1=a.x+NW/2, x2=b.x+NW/2, y1=a.y+NH, y2=b.y;
        dx = (x1+x2)/2;
        dy = (y1+y2)/2 - 2;
      }
      lab.setAttribute("x", dx);
      lab.setAttribute("y", dy);
      lab.textContent=e.var; svg.appendChild(lab);
    }
  }

  // numeración DFD determinista: procesos 1,2… · almacenes D1,D2… (kids ya viene ordenado)
  let pn=0, dn=0; const num={};
  kids.forEach(n=>{ if(n.dfd_role==="process") num[n.id]=""+(++pn);
                    else if(n.dfd_role==="store") num[n.id]="D"+(++dn); });
  const mk=t=>document.createElementNS(SVGNS,t);
  
  // nodes
  kids.forEach(n=>{
    const p=pos[n.id], role=n.dfd_role;
    const g=mk("g");
    const isFlowNode = n.graph_type === "flow";
    
    g.setAttribute("class",`node kind-${n.kind}`+
      (role?` role-${role}`:"")+
      (childrenOf[n.id].length?" has-children":"")+
      (selected===n.id?" sel":"")+
      (n.recursive?" recursive":"")+
      (n.in_loop?" inloop":"")+
      (isFlowNode?" flow-node":"")
    );
    g.setAttribute("transform",`translate(${p.x},${p.y})`);
    
    if (isFlowNode) {
      if (n.kind === "start" || n.kind === "end") {
        const r = mk("rect"); r.setAttribute("width", NW); r.setAttribute("height", NH); r.setAttribute("rx", 26); g.appendChild(r);
      } else if (n.kind === "decision") {
        const poly = mk("polygon"); poly.setAttribute("points", "105,0 210,26 105,52 0,26"); g.appendChild(poly);
      } else if (n.kind === "read" || n.kind === "write") {
        const poly = mk("polygon"); poly.setAttribute("points", "20,0 210,0 190,52 0,52"); g.appendChild(poly);
      } else if (n.kind === "call") {
        const r = mk("rect"); r.setAttribute("width", NW); r.setAttribute("height", NH); g.appendChild(r);
        const l1 = mk("line"); l1.setAttribute("class", "divider"); l1.setAttribute("x1", 15); l1.setAttribute("y1", 0); l1.setAttribute("x2", 15); l1.setAttribute("y2", NH); g.appendChild(l1);
        const l2 = mk("line"); l2.setAttribute("class", "divider"); l2.setAttribute("x1", 195); l2.setAttribute("y1", 0); l2.setAttribute("x2", 195); l2.setAttribute("y2", NH); g.appendChild(l2);
      } else if (n.kind === "loop") {
        const poly = mk("polygon"); poly.setAttribute("points", "15,0 195,0 210,26 195,52 15,52 0,26"); g.appendChild(poly);
      } else {
        const r = mk("rect"); r.setAttribute("width", NW); r.setAttribute("height", NH); g.appendChild(r);
      }
    } else {
      if(role==="external"){
        const sh=mk("rect");sh.setAttribute("class","shadow");sh.setAttribute("x",4);sh.setAttribute("y",4);
        sh.setAttribute("width",NW);sh.setAttribute("height",NH);g.appendChild(sh);
        const r=mk("rect");r.setAttribute("width",NW);r.setAttribute("height",NH);r.setAttribute("rx",0);g.appendChild(r);
      }else if(role==="store"){
        const pth=mk("path");pth.setAttribute("d",`M${NW} 0 H0 V${NH} H${NW}`);g.appendChild(pth);
        const ln=mk("line");ln.setAttribute("class","divider");ln.setAttribute("x1",30);ln.setAttribute("y1",0);ln.setAttribute("x2",30);ln.setAttribute("y2",NH);g.appendChild(ln);
        const id=mk("text");id.setAttribute("class","dfdnum");id.setAttribute("x",15);id.setAttribute("y",30);id.setAttribute("text-anchor","middle");id.textContent=num[n.id]||"D";g.appendChild(id);
      }else{
        const r=mk("rect");r.setAttribute("width",NW);r.setAttribute("height",NH);r.setAttribute("rx",8);g.appendChild(r);
        if(role==="process"){
          const ln=mk("line");ln.setAttribute("class","divider");ln.setAttribute("x1",0);ln.setAttribute("y1",18);ln.setAttribute("x2",NW);ln.setAttribute("y2",18);g.appendChild(ln);
          const id=mk("text");id.setAttribute("class","dfdnum");id.setAttribute("x",8);id.setAttribute("y",13);id.textContent=num[n.id]||"";g.appendChild(id);
        }
      }
    }
    
    let tx, ty, sy, anchor = "start";
    if (isFlowNode) {
      anchor = "middle";
      tx = NW / 2;
      ty = 24;
      sy = 40;
    } else {
      const isProc = role === "process";
      tx = role === "store" ? 38 : 12;
      ty = isProc ? 32 : 22;
      sy = isProc ? 46 : 40;
    }
    
    const t=mk("text");t.setAttribute("class","t");t.setAttribute("x",tx);t.setAttribute("y",ty);
    if (anchor === "middle") {
      t.setAttribute("text-anchor", "middle");
    }
    
    let maxLen = 28;
    if (isFlowNode) {
      if (n.kind === "decision") maxLen = 20;
      else if (n.kind === "read" || n.kind === "write" || n.kind === "loop") maxLen = 22;
      else maxLen = 26;
    } else if (role === "store") {
      maxLen = 20;
    } else if (n.recursive) {
      maxLen = 24;
    }
    
    t.textContent=(n.label||n.id).slice(0, maxLen);
    g.appendChild(t);
    
    const s=mk("text");s.setAttribute("class","s");s.setAttribute("x",tx);s.setAttribute("y",sy);
    if (anchor === "middle") {
      s.setAttribute("text-anchor", "middle");
    }
    
    const nk=childrenOf[n.id].length;
    let subtitleText = KIND[n.kind];
    if ((n.kind === "function" || n.kind === "method") && n.signature) {
      subtitleText = formatCompactSignature(n.signature);
    } else {
      subtitleText = KIND[n.kind] + (nk ? ` · ${nk} dentro` : "") + (n.kind !== "package" && n.kind !== "module" && n.line ? ` · L${n.line}` : "");
    }
    s.textContent = subtitleText;
    g.appendChild(s);
    
    if(n.recursive){const lp=mk("text");lp.setAttribute("class","loop");lp.setAttribute("x",NW-22);lp.setAttribute("y",role==="process"?14:24);lp.textContent="↺";lp.appendChild(mk("title")).textContent="recursión / en un ciclo";g.appendChild(lp);}
    
    // Iconos de notas de comentario y ADRs flotando sobre el nodo statement
    if (isFlowNode || role) {
      if (n.comment) {
        const cGroup = mk("g");
        cGroup.setAttribute("transform", `translate(${NW - 28}, -12)`);
        const cRect = mk("rect"); cRect.setAttribute("width", 22); cRect.setAttribute("height", 22); cRect.setAttribute("rx", 11); cRect.setAttribute("fill", "#e8f0fe"); cRect.setAttribute("stroke", "#1a73e8"); cRect.setAttribute("stroke-width", "1"); cGroup.appendChild(cRect);
        const cText = mk("text"); cText.setAttribute("x", 11); cText.setAttribute("y", 15); cText.setAttribute("text-anchor", "middle"); cText.setAttribute("style", "font-size:11px;cursor:help;"); cText.textContent = "💬";
        const cTitle = mk("title"); cTitle.textContent = n.comment; cText.appendChild(cTitle);
        cGroup.appendChild(cText);
        g.appendChild(cGroup);
      }
      if (n.adrs && n.adrs.length > 0) {
        n.adrs.forEach((adr, idx) => {
          const aGroup = mk("g");
          aGroup.setAttribute("transform", `translate(${8 + idx * 56}, -12)`);
          const aRect = mk("rect"); aRect.setAttribute("width", 52); aRect.setAttribute("height", 16); aRect.setAttribute("rx", 4); aRect.setAttribute("fill", "#fce8e6"); aRect.setAttribute("stroke", "#c5221f"); aRect.setAttribute("stroke-width", "1.2"); aGroup.appendChild(aRect);
          const aText = mk("text"); aText.setAttribute("x", 26); aText.setAttribute("y", 11); aText.setAttribute("text-anchor", "middle"); aText.setAttribute("style", "font-size:8px;font-weight:bold;fill:#c5221f"); aText.textContent = adr; aGroup.appendChild(aText);
          g.appendChild(aGroup);
        });
      }
    }
    
    g.onclick=(evt)=>{
      evt.stopPropagation();
      if(childrenOf[n.id].length){
        focus=n.id;selected=null;
      } else {
        selected=selected===n.id?null:n.id;
      }
      draw();
    };
    svg.appendChild(g);
  });
  
  // Desconflictualizar etiquetas de flujo para evitar solapes
  const labels = Array.from(svg.querySelectorAll(".flowlabel, .control-label"));
  labels.sort((a, b) => parseFloat(a.getAttribute("x")) - parseFloat(b.getAttribute("x")));
  for (let i = 0; i < labels.length; i++) {
    const la = labels[i];
    const xa = parseFloat(la.getAttribute("x"));
    let ya = parseFloat(la.getAttribute("y"));
    for (let j = 0; j < i; j++) {
      const lb = labels[j];
      const xb = parseFloat(lb.getAttribute("x"));
      const yb = parseFloat(lb.getAttribute("y"));
      if (Math.abs(xa - xb) < 80 && Math.abs(ya - yb) < 12) {
        ya = yb + 12;
        la.setAttribute("y", ya);
      }
    }
  }

  // resaltar aristas del seleccionado
  if(selected){
    svg.querySelectorAll(".edge").forEach(p=>{
      if(p.dataset.src===selected||p.dataset.dst===selected) p.classList.add("hot");
    });
  }

  // Leyenda dinámica
  const lgEl = document.getElementById("legend");
  if (hasGraphType) {
    if (currentGraphType === "flow") {
      lgEl.innerHTML = `
        <div style="font-weight:500;margin-bottom:4px">Símbolos Flowchart:</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #1a73e8;background:#e8f0fe;border-radius:6px;margin-right:6px"></span>Inicio / Fin</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #9aa0a6;background:#f1f3f4;margin-right:6px"></span>Proceso / Asig</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #e37400;background:#fef7e0;transform:rotate(45deg);margin-right:6px;transform-origin:center"></span>Decisión</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #188038;background:#e6f4ea;transform:skewX(-15deg);margin-right:6px"></span>Lec / Esc</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #5f6368;background:#f1f3f4;border-left:3px solid #5f6368;border-right:3px solid #5f6368;margin-right:6px"></span>Llamada</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #c5221f;background:#fce8e6;clip-path:polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);margin-right:6px"></span>Bucle</div>
        <div style="margin-top:6px;color:#5f6368">— control flow · <span style="color:#c5221f">— back-edge (loop)</span></div>
      `;
    } else {
      lgEl.innerHTML = `
        <div style="font-weight:500;margin-bottom:4px">Símbolos DFD (Gane-Sarson):</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #1a73e8;background:#e8f0fe;border-radius:3px;margin-right:6px"></span>Proceso</div>
        <div><span style="display:inline-block;width:12px;height:12px;border-bottom:1px solid #e37400;border-top:1px solid #e37400;border-left:1px solid #e37400;background:#fef7e0;margin-right:6px"></span>Almacén</div>
        <div><span style="display:inline-block;width:12px;height:12px;border:1px solid #188038;background:#e6f4ea;margin-right:6px"></span>Entidad Externa / Return</div>
        <div style="margin-top:6px;color:#5f6368"><span style="color:#9334e6">— data flow</span></div>
      `;
    }
  } else {
    const LG=[["package","paquete"],["module","módulo"],["class","clase"],["function","función"],["method","método"]];
    lgEl.innerHTML = LG.map(([k,l])=>
      `<div><i class="leg-${k}"></i>${l}</div>`).join("")+
      `<div style="margin-top:6px;color:#5f6368">— import · <span style="color:#1a73e8">— call</span>${G.stats && G.stats.loops ? ' · <span style="color:#c5221f">— loop (↺)</span>' : ''}</div>`;
    
    document.querySelectorAll("#legend i").forEach((el,i)=>{
      const k=LG[i][0]; const cs=getComputedStyle(document.documentElement);
      el.style.background=cs.getPropertyValue("--"+(k==="package"?"pkg":k==="module"?"mod":k==="class"?"cls":k==="function"?"fn":"mtd"));
      el.style.borderColor=cs.getPropertyValue("--"+(k==="package"?"pkgL":k==="module"?"modL":k==="class"?"clsL":k==="function"?"fnL":"mtdL"));
      el.style.borderRadius="3px";
      el.style.display="inline-block";
      el.style.width="12px";
      el.style.height="12px";
      el.style.border="1px solid";
    });
  }

  // Deep-linking: Actualizar location.hash según el foco actual o la selección
  if (selected && byId[selected] && byId[selected].url_id) {
    const targetHash = byId[selected].url_id;
    if (decodeURIComponent(location.hash.replace("#", "")) !== targetHash) {
      history.pushState(null, null, "#" + targetHash);
    }
  } else if (byId[focus] && byId[focus].url_id) {
    const targetHash = byId[focus].url_id;
    if (decodeURIComponent(location.hash.replace("#", "")) !== targetHash) {
      history.pushState(null, null, "#" + targetHash);
    }
  }

  updatePanel();
}

svg.onclick = () => {
  selected = null;
  draw();
};

function handleInitialHash() {
  const hash = decodeURIComponent(location.hash.replace("#", ""));
  if (hash) {
    const target = G.nodes.find(n => n.url_id === hash);
    if (target) {
      if (childrenOf[target.id] && childrenOf[target.id].length > 0) {
        focus = target.id;
        selected = null;
      } else {
        focus = target.parent_id || ROOT.id;
        selected = target.id;
      }
    }
  }
}

window.addEventListener("hashchange", () => {
  const hash = decodeURIComponent(location.hash.replace("#", ""));
  if (hash) {
    const target = G.nodes.find(n => n.url_id === hash);
    if (target) {
      if (childrenOf[target.id] && childrenOf[target.id].length > 0) {
        if (focus !== target.id) {
          focus = target.id;
          selected = null;
          draw();
        }
      } else {
        if (focus !== target.parent_id || selected !== target.id) {
          focus = target.parent_id || ROOT.id;
          selected = target.id;
          draw();
        }
      }
    }
  } else {
    if (focus !== ROOT.id || selected !== null) {
      focus = ROOT.id;
      selected = null;
      draw();
    }
  }
});

handleInitialHash();
window.addEventListener("resize", draw);
draw();
</script></body></html>"""
