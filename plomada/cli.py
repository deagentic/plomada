"""cli — punto de entrada de plomada.

  plomada /ruta/de/proyecto         extrae → modela → renderiza → sirve la vista
  plomada extract /ruta -o g.json   solo extracción (formato pivote)
  plomada build g.json -o out.html  grafo → HTML autocontenido
  plomada serve /ruta [--port]      genera y sirve en 127.0.0.1
"""
import argparse
import json
import os
import sys

from . import extractor, render, serve

try:
    from . import model as _model
except Exception:
    _model = None


def _build_graph(path):
    graph = extractor.extract(path)
    if _model and hasattr(_model, "build_model"):
        graph = _model.build_model(graph)
    return graph


def _load(graph_json):
    with open(graph_json, encoding="utf-8") as fh:
        graph = json.load(fh)
    if _model and hasattr(_model, "build_model") and "stats" not in graph:
        graph = _model.build_model(graph)
    return graph


def _subcommand(argv):
    ap = argparse.ArgumentParser(prog="plomada")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_ex = sub.add_parser("extract", help="proyecto → grafo JSON")
    p_ex.add_argument("path")
    p_ex.add_argument("-o", "--out", default="graph.json")
    p_bd = sub.add_parser("build", help="grafo JSON → HTML")
    p_bd.add_argument("graph")
    p_bd.add_argument("-o", "--out", default="report.html")
    p_sv = sub.add_parser("serve", help="proyecto → servir en 127.0.0.1")
    p_sv.add_argument("path")
    p_sv.add_argument("--port", type=int, default=8770)
    a = ap.parse_args(argv)

    if a.cmd == "extract":
        graph = _build_graph(a.path)
        with open(a.out, "w", encoding="utf-8") as fh:
            json.dump(graph, fh, ensure_ascii=False, indent=2)
        print(f"✓ grafo: {a.out}  ({len(graph['nodes'])} nodos, {len(graph['edges'])} aristas)")
    elif a.cmd == "build":
        graph = _load(a.graph)
        open(a.out, "w", encoding="utf-8").write(render.render_html(graph, graph.get("root", "plomada")))
        print(f"✓ HTML: {a.out}")
    elif a.cmd == "serve":
        graph = _build_graph(a.path)
        serve.serve_html(render.render_html(graph, graph.get("root", "plomada")), port=a.port)
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"extract", "build", "serve"}:
        return _subcommand(argv)

    # modo por defecto: plomada /ruta [-o] [--no-serve] [--port]
    ap = argparse.ArgumentParser(
        prog="plomada",
        description="Vista dinámica arquitectura→DFD de un proyecto Python (sin IA). "
                    "Subcomandos: extract | build | serve.")
    ap.add_argument("path", nargs="?", help="ruta del proyecto a visualizar")
    ap.add_argument("-o", "--out", default="report.html")
    ap.add_argument("--no-serve", action="store_true", help="solo escribir el HTML")
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args(argv)

    if not a.path:
        ap.print_help()
        return 1
    if not os.path.isdir(a.path):
        print(f"error: no es un directorio: {a.path}", file=sys.stderr)
        return 2
    graph = _build_graph(a.path)
    html_text = render.render_html(graph, graph.get("root", "plomada"))
    open(a.out, "w", encoding="utf-8").write(html_text)
    print(f"✓ HTML: {a.out}  ({len(graph['nodes'])} nodos, {len(graph['edges'])} aristas)")
    if not a.no_serve:
        serve.serve_html(html_text, port=a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
