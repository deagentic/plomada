# plomada

Visualiza un proyecto **Python** como una **vista dinámica con drill-down: arquitectura → módulos → DFD**.
Interfaz estilo Google, **offline** (sin CDNs ni dependencias), análisis **determinístico** (sin IA en runtime).

```bash
python3 -m plomada /ruta/de/proyecto          # extrae, renderiza y sirve en 127.0.0.1
python3 -m plomada /ruta --no-serve -o out.html
python3 -m plomada extract /ruta -o graph.json
python3 -m plomada build graph.json -o out.html
python3 -m plomada serve /ruta --port 8770
```

## Cómo funciona

Pipeline de etapas puras (cada frontera es un JSON inspeccionable):

```
extract → model → (layout client-side) → render/serve
```

- **extract** (`ast`, 2 pasadas): paquetes/módulos/funciones como nodos; aristas `contains`,
  `import` (arquitectura) y `call` (DFD). Resolución determinista: lo que no resuelve de forma
  única queda `resolved:false` anclado al módulo padre — **nunca adivina**.
- **model**: valida, deriva `children` y métricas `fan_in/fan_out`, y stats.
- **render**: un único HTML autocontenido (Vanilla JS + SVG). Drill-down por niveles, aristas
  dibujadas al focus. Layout determinista (grid ordenado).

## Drill-down

`paquete → módulo → función/clase/método`. En el nivel de módulos ves las dependencias
(`import`); al entrar a un módulo ves el DFD de sus funciones (`call`).

## Dogfood

```bash
python3 -m plomada .       # plomada visualizándose a sí misma
```

## Autoría

Proyecto **co-diseñado y co-desarrollado (XP)** entre **Claude** y **agy** (Antigravity CLI).
Ver `docs/DESIGN.md` para las decisiones de arquitectura y a quién se originó cada una.
MVP: Python. Rust/Go quedan tras la misma frontera del grafo pivote.

## Licencia

[MIT](LICENSE) © 2026 Grupo Deacero. Proyecto open source.
