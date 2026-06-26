# plomada — diseño (co-diseñado Claude ✕ agy, XP)

> Visualiza un proyecto Python como **vista dinámica con drill-down: arquitectura → módulos → DFD**.
> CLI: `plomada /ruta/de/proyecto` → genera una interfaz estilo Google, offline, sin IA en runtime.

## Decisiones de arquitectura (acordadas en la jam de co-diseño)

1. **Formato pivote = property-graph JSON único** con `level` + `parent_id` y aristas tipadas.
   Un solo grafo con niveles de zoom (`package` → `module` → `function`) habilita el drill-down
   sin re-extraer. *(Claude r1 · agy convergió)*
2. **ID de nodo** = `file_rel::qualname::lineno` — robusto ante colisiones de lambdas/scopes;
   el dotted-path queda solo como label. *(Claude r2 · agy aceptó r3)*
3. **Extracción en 2 pasadas con `ast`**: pasada 1 = símbolos (defs/clases/imports);
   pasada 2 = llamadas, resueltas contra la tabla de símbolos del proyecto. *(Claude r2)*
4. **Resolución determinista, nunca adivina**: si una llamada no resuelve a un símbolo único del
   proyecto, la arista se marca `resolved:false` y se ancla al módulo padre. *(agy r2 · cierre Claude r3)*
   - *Ajuste de navigator:* la jam mencionó `jedi`; se baja a **`ast` puro (stdlib)** para no
     introducir dependencias externas. El fallback `resolved:false` cubre la ambigüedad.
5. **Pipeline de etapas puras** `extract → model → layout → serve`, cada una con contrato JSON
   estable y subcomando propio (`plomada extract|build|serve`). Hace el dogfood trivial: cada
   frontera es un `graph.json` inspeccionable. *(Claude r3)*
6. **UI = un solo HTML autocontenido**, Vanilla JS + SVG, sin CDNs. Jerarquía de módulos como
   cajas anidadas; dependencias/llamadas como aristas SVG dibujadas al hacer focus. *(agy r3)*

## Niveles del grafo (drill-down)

```
package  (carpeta con __init__.py o raíz)
  └─ module   (archivo .py)
       └─ function | class | method
```
Aristas: `import` (module→module), `call` (function→function), `contains` (jerarquía vía parent_id).

## Pipeline / componentes internos

```
plomada/
  extractor.py   # ruta de proyecto → property-graph JSON (ast, 2 pasadas)
  model.py       # normaliza/valida el grafo, deriva niveles y agrega aristas
  layout.py      # posiciones deterministas (cajas anidadas por nivel)
  render.py      # grafo+layout → un HTML autocontenido (vanilla JS/SVG, estilo Google)
  serve.py       # servidor local 127.0.0.1 para la vista
  cli.py         # `plomada /path` (todo) + subcomandos extract|build|serve
```

## Contrato del CLI

- `plomada /ruta`            → extrae, modela, renderiza y abre/sirve la vista.
- `plomada extract /ruta -o graph.json`
- `plomada build graph.json -o report.html`
- `plomada serve /ruta`      → 127.0.0.1

## Pendientes (de la jam, a resolver en co-desarrollo)

- Derivación del nivel intermedio `component` (por ahora: package/module/function).
- Algoritmo concreto de `layout` determinista (cajas anidadas + ruteo de aristas).
- Reconciliación fina entre `plomada /path` y los subcomandos.

## Limitaciones del MVP (Trabajo Futuro)

1. **Bypass Lineal de Estructuras de Control (`If`/Branches)**:
   - Al no construir un Grafo de Flujo de Control (CFG) completo o forma SSA, la extracción del DFD intra-procedural recorre las ramas condicionales de forma lineal (`body` seguido de `orelse`).
   - Esto implica que las variables redefinidas en múltiples ramas o definidas exclusivamente en una rama no resuelven mediante nodos phi/mezcla. Las lecturas subsiguientes apuntarán a la última definición registrada de manera lineal.

## Criterio de aceptación

`plomada ~/work/plomada` produce su **propia** vista (arquitectura → DFD). Dogfood.

