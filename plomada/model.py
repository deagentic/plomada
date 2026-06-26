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


def _tarjan_sccs(adj):
    """Componentes fuertemente conexas (Tarjan, iterativo → sin límite de recursión)."""
    index, low, onstack, stack, out = {}, {}, {}, [], []
    counter = [0]
    for start in adj:
        if start in index:
            continue
        work = [(start, iter(adj[start]))]
        index[start] = low[start] = counter[0]; counter[0] += 1
        stack.append(start); onstack[start] = True
        while work:
            node, it = work[-1]
            pushed = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1
                    stack.append(w); onstack[w] = True
                    work.append((w, iter(adj[w])))
                    pushed = True
                    break
                elif onstack.get(w):
                    low[node] = min(low[node], index[w])
            if pushed:
                continue
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop(); onstack[w] = False; comp.append(w)
                    if w == node:
                        break
                out.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
    return out


def _detect_cycles(g, nodes, edges):
    """Marca loops en el grafo de llamadas: recursión directa (self-call) y
    recursión mutua (SCC>1). Añade node['recursive'] y edge['in_cycle']."""
    adj = {nid: [] for nid in nodes}
    for e in edges:
        if e["type"] == "call" and e.get("resolved") and e["src"] in nodes and e["dst"] in nodes:
            adj[e["src"]].append(e["dst"])
    sccs = _tarjan_sccs(adj)
    scc_id = {nid: i for i, comp in enumerate(sccs) for nid in comp}
    cyclic = {i for i, comp in enumerate(sccs) if len(comp) > 1}
    self_rec = {e["src"] for e in edges
                if e["type"] == "call" and e.get("resolved") and e["src"] == e["dst"]}

    in_cycle_nodes = {nid for nid in nodes if scc_id.get(nid) in cyclic} | self_rec
    for n in g["nodes"]:
        n["recursive"] = n["id"] in in_cycle_nodes
    for e in edges:
        if e["type"] == "call" and e.get("resolved"):
            same_scc = (scc_id.get(e["src"]) == scc_id.get(e["dst"])
                        and scc_id.get(e["src"]) in cyclic)
            e["in_cycle"] = bool(same_scc or e["src"] == e["dst"])
    cyclic_scc_nodes = {n for i in cyclic for n in sccs[i]}
    pure_self = self_rec - cyclic_scc_nodes        # recursión directa fuera de un SCC mayor
    return {"loops": len(cyclic) + len(pure_self),
            "recursive_functions": len(in_cycle_nodes)}


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

    # loops/ciclos en el grafo de llamadas (recursión directa y mutua)
    cycle_stats = _detect_cycles(g, nodes, edges)

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
        **cycle_stats,
    }

    # orden estable
    g["nodes"].sort(key=lambda n: n["id"])
    g["edges"].sort(key=lambda e: (e["src"], e["dst"], e["type"], e.get("callee") or ""))
    return g
