"""model — normaliza/valida el property-graph y deriva métricas para el drill-down.

Contrato (co-acordado en la jam; autoría: Claude, por bloqueo del harness para que agy
lo dirigiera — ver docs/DESIGN.md). No muta la entrada: trabaja sobre una copia.
  - valida aristas (descarta las que apunten a nodos inexistentes); parent_id huérfano → None
  - children: [ids] ordenados por aristas 'contains'
  - metrics: {fan_in, fan_out} por nodo (aristas 'call')
  - stats globales
  - orden estable de nodes y edges
"""
import copy


def build_model(graph):
    g = copy.deepcopy(graph)
    nodes = {n["id"]: n for n in g["nodes"]}

    # validar aristas
    edges = []
    for e in g["edges"]:
        if e.get("src") in nodes and e.get("dst") in nodes:
            edges.append(e)
    g["edges"] = edges

    # parent_id huérfano → None
    for n in g["nodes"]:
        if n.get("parent_id") and n["parent_id"] not in nodes:
            n["parent_id"] = None

    # children (vía 'contains'), métricas (vía 'call')
    children = {nid: [] for nid in nodes}
    fan_in = {nid: 0 for nid in nodes}
    fan_out = {nid: 0 for nid in nodes}
    for e in edges:
        if e["type"] == "contains":
            children[e["src"]].append(e["dst"])
        elif e["type"] == "call":
            fan_out[e["src"]] += 1
            fan_in[e["dst"]] += 1
    for n in g["nodes"]:
        n["children"] = sorted(children[n["id"]])
        n["metrics"] = {"fan_in": fan_in[n["id"]], "fan_out": fan_out[n["id"]]}

    # stats
    lvl = lambda L: sum(1 for n in g["nodes"] if n["level"] == L)
    typ = lambda T: sum(1 for e in edges if e["type"] == T)
    g["stats"] = {
        "packages": lvl("package"),
        "modules": lvl("module"),
        "functions": lvl("function"),
        "calls": typ("call"),
        "imports": typ("import"),
        "unresolved_calls": sum(1 for e in edges if e["type"] == "call" and e.get("resolved") is False),
    }

    # orden estable
    g["nodes"].sort(key=lambda n: n["id"])
    g["edges"].sort(key=lambda e: (e["src"], e["dst"], e["type"], e.get("callee") or ""))
    return g
