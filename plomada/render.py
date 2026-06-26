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
#stage{flex:1;position:relative;overflow:auto}
svg{display:block}
.node{cursor:pointer}
.node rect,.node path{stroke-width:1.5;transition:filter .12s}
.node:hover rect{filter:brightness(.97)}
.node.has-children rect{stroke-dasharray:none}
.node text.t{font-weight:500;font-size:13px}
.node text.s{font-size:11px;fill:var(--dim)}
.kind-package rect{fill:var(--pkg);stroke:var(--pkgL)}
.kind-module rect{fill:var(--mod);stroke:var(--modL)}
.kind-class rect{fill:var(--cls);stroke:var(--clsL)}
.kind-function rect{fill:var(--fn);stroke:var(--fnL)}
.kind-method rect{fill:var(--mtd);stroke:var(--mtdL)}
.kind-assign rect,.kind-call rect,.kind-expr rect{fill:#f1f3f4;stroke:#9aa0a6}
.kind-branch rect{fill:#e8f0fe;stroke:#1a73e8}
.kind-return rect{fill:#e6f4ea;stroke:#188038}
.kind-loop rect{fill:#fce8e6;stroke:#c5221f}
.edge.data_flow{stroke:#9334e6;opacity:.55}
/* Gane-Sarson por rol (gana sobre kind-* para nodos statement) */
.role-process rect{fill:#e8f0fe;stroke:#1a73e8}
.role-store path,.role-store rect{fill:#fef7e0;stroke:#e37400;stroke-width:1.8}
.role-external rect{fill:#e6f4ea;stroke:#188038}
.flowlabel{fill:#9334e6;font-size:10px;text-anchor:middle;paint-order:stroke;stroke:#fff;stroke-width:3px}
.node.inloop rect,.node.inloop path{stroke-dasharray:5 3}  /* dentro de un loop (anotación, no nodo) */
.edge{fill:none;stroke:var(--dim);stroke-width:1.4;marker-end:url(#arrow);opacity:.45}
.edge.import{stroke:var(--modL)}.edge.call{stroke:var(--blue)}
.edge.unresolved{stroke-dasharray:4 3;opacity:.3}
.edge.loop{stroke:#c5221f;stroke-width:2.2;opacity:.9;marker-end:url(#arrowLoop)}
.node.recursive rect{stroke:#c5221f;stroke-width:2.5}
.node.sel rect{stroke-width:3.5}
.edge.hot{opacity:1;stroke-width:2.4}
.node text.loop{fill:#c5221f;font-size:14px;font-weight:700}
#empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--dim);pointer-events:none}
#empty[hidden]{display:none}
#legend{position:fixed;right:16px;bottom:16px;background:var(--panel);border:1px solid var(--line);
border-radius:8px;padding:10px 12px;font-size:12px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
#legend div{display:flex;align-items:center;gap:6px;margin:3px 0}
#legend i{width:12px;height:12px;border-radius:3px;display:inline-block;border:1px solid}
</style></head><body>
<header>
  <h1>plomada</h1>
  <nav id="crumbs"></nav>
  <div id="stats"></div>
</header>
<div id="stage"><svg id="svg"></svg><div id="empty" hidden>Vacío</div></div>
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

const KIND={package:"paquete",module:"módulo",class:"clase",function:"función",method:"método",
  statement:"sentencia",assign:"asignación",loop:"loop",branch:"rama",return:"return",call:"llamada",expr:"expr",
  store:"almacén",parameter:"parámetro",iterate:"bucle"};
const NW=210, NH=52, GAPX=46, GAPY=70, PAD=40;

function ancestors(id){const out=[];let c=byId[id];while(c){out.unshift(c);c=c.parent_id?byId[c.parent_id]:null;}return out;}

function visibleEdges(ids){
  const set=new Set(ids), out=[];
  for(const e of G.edges){
    if(e.type==="contains") continue;
    if(set.has(e.src)&&set.has(e.dst)) out.push(e);
  }
  return out;
}

function draw(){
  const svg=document.getElementById("svg"); svg.innerHTML="";
  const kids=(childrenOf[focus]||[]).map(id=>byId[id]);
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
  // layout grid (determinista)
  const cols=Math.max(1,Math.floor((window.innerWidth-2*PAD)/(NW+GAPX)));
  const pos={};
  kids.forEach((n,i)=>{const r=Math.floor(i/cols),c=i%cols;pos[n.id]={x:PAD+c*(NW+GAPX),y:PAD+r*(NH+GAPY)};});
  const rows=Math.ceil(kids.length/cols);
  svg.setAttribute("width", Math.max(window.innerWidth, PAD*2+cols*(NW+GAPX)));
  svg.setAttribute("height", Math.max(300, PAD*2+rows*(NH+GAPY)));
  // edges
  const ids=kids.map(n=>n.id);
  for(const e of visibleEdges(ids)){
    const a=pos[e.src],b=pos[e.dst]; if(!a||!b)continue;
    const x1=a.x+NW/2,y1=a.y+NH,x2=b.x+NW/2,y2=b.y;
    const my=(y1+y2)/2;
    const p=document.createElementNS(SVGNS,"path");
    p.setAttribute("d",`M${x1} ${y1} C ${x1} ${my} ${x2} ${my} ${x2} ${y2}`);
    p.setAttribute("class","edge "+e.type+(e.resolved===false?" unresolved":"")+(e.in_cycle?" loop":""));
    p.dataset.src=e.src;p.dataset.dst=e.dst;
    svg.appendChild(p);
    if(e.type==="data_flow"&&e.var){     // etiqueta del dato que fluye
      const lab=document.createElementNS(SVGNS,"text");
      lab.setAttribute("class","flowlabel");lab.setAttribute("x",(x1+x2)/2);lab.setAttribute("y",my-2);
      lab.textContent=e.var; svg.appendChild(lab);
    }
  }
  // nodes
  kids.forEach(n=>{
    const p=pos[n.id];
    const g=document.createElementNS(SVGNS,"g");
    g.setAttribute("class",`node kind-${n.kind}`+(n.dfd_role?` role-${n.dfd_role}`:"")+(childrenOf[n.id].length?" has-children":"")+(selected===n.id?" sel":"")+(n.recursive?" recursive":"")+(n.in_loop?" inloop":""));
    g.setAttribute("transform",`translate(${p.x},${p.y})`);
    let shape;
    if(n.dfd_role==="store"){            // almacén Gane-Sarson: rectángulo abierto a la derecha
      shape=document.createElementNS(SVGNS,"path");
      shape.setAttribute("d",`M${NW} 0 H0 V${NH} H${NW}`);
    }else{                               // proceso = redondeado · entidad externa = cuadrado
      shape=document.createElementNS(SVGNS,"rect");
      shape.setAttribute("width",NW);shape.setAttribute("height",NH);
      shape.setAttribute("rx", n.dfd_role==="external"?0:8);
    }
    g.appendChild(shape);
    const t=document.createElementNS(SVGNS,"text");
    t.setAttribute("class","t");t.setAttribute("x",12);t.setAttribute("y",22);
    t.textContent=(n.label||n.id).slice(0,n.recursive?24:28); g.appendChild(t);
    const s=document.createElementNS(SVGNS,"text");
    s.setAttribute("class","s");s.setAttribute("x",12);s.setAttribute("y",40);
    const nk=childrenOf[n.id].length;
    s.textContent=KIND[n.kind]+(nk?` · ${nk} dentro`:"")+(n.kind!=="package"&&n.kind!=="module"&&n.line?` · L${n.line}`:"");
    g.appendChild(s);
    if(n.recursive){  // badge de loop/recursión
      const lp=document.createElementNS(SVGNS,"text");
      lp.setAttribute("class","loop");lp.setAttribute("x",NW-22);lp.setAttribute("y",24);
      lp.textContent="↺"; lp.appendChild(document.createElementNS(SVGNS,"title")).textContent="recursión / en un ciclo";
      g.appendChild(lp);
    }
    g.onclick=()=>{ if(childrenOf[n.id].length){focus=n.id;selected=null;} else {selected=selected===n.id?null:n.id;} draw(); };
    svg.appendChild(g);
  });
  // resaltar aristas del seleccionado
  if(selected){
    svg.querySelectorAll(".edge").forEach(p=>{
      if(p.dataset.src===selected||p.dataset.dst===selected) p.classList.add("hot");
    });
  }
}
const LG=[["package","paquete"],["module","módulo"],["class","clase"],["function","función"],["method","método"]];
document.getElementById("legend").innerHTML = LG.map(([k,l])=>
  `<div><i class="leg-${k}"></i>${l}</div>`).join("")+
  `<div style="margin-top:6px;color:#5f6368">— import · <span style="color:#1a73e8">— call</span>${G.stats && G.stats.loops ? ' · <span style="color:#c5221f">— loop (↺)</span>' : ''}</div>`;
document.querySelectorAll("#legend i").forEach((el,i)=>{
  const k=LG[i][0]; const cs=getComputedStyle(document.documentElement);
  el.style.background=cs.getPropertyValue("--"+(k==="package"?"pkg":k==="module"?"mod":k==="class"?"cls":k==="function"?"fn":"mtd"));
  el.style.borderColor=cs.getPropertyValue("--"+(k==="package"?"pkgL":k==="module"?"modL":k==="class"?"clsL":k==="function"?"fnL":"mtdL"));
});
window.addEventListener("resize",draw);
draw();
</script></body></html>"""
