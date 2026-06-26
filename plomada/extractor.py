"""extractor — ruta de proyecto Python → property-graph JSON (ast, 2 pasadas).

Determinista, stdlib pura (sin jedi/deps). Formato pivote acordado:
  nodes: {id, level, parent_id, label, kind, file, line}
  edges: {src, dst, type, resolved}
Niveles: package → module → function/class/method. Aristas: contains, import, call.
ID de nodo: "<file_rel>::<qualname>::<lineno>".

Revisión de navigator (agy) integrada: jerarquía real vía parent_qual; método solo si el
contenedor inmediato es clase; imports relativos resueltos; desambiguación por tabla de
imports antes del índice global; se ignoran llamadas a parámetros locales.
"""
import ast
import os


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _module_id(file_rel):
    return f"{file_rel}::<module>::0"


def _package_id(pkg_rel):
    return f"{pkg_rel or '.'}::<package>::0"


def _node_id(file_rel, qualname, lineno):
    return f"{file_rel}::{qualname}::{lineno}"


def _dotted(file_rel):
    p = file_rel[:-3] if file_rel.endswith(".py") else file_rel
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


class _ModuleVisitor(ast.NodeVisitor):
    """Pasada 1: símbolos (con jerarquía y tipo de contenedor) + imports."""

    def __init__(self, file_rel, dotted):
        self.file_rel = file_rel
        self.dotted = dotted
        self.defs = {}          # qualname -> {id, kind, qualname, line, parent_qual}
        self.imports = []       # (target_dotted, local_name)
        self._stack = []        # [(name, kind)]

    def _add(self, name, kind, lineno):
        q = ".".join([n for n, _ in self._stack] + [name])
        parent_qual = ".".join(n for n, _ in self._stack) or None
        self.defs[q] = {"id": _node_id(self.file_rel, q, lineno), "kind": kind,
                        "qualname": q, "line": lineno, "parent_qual": parent_qual}

    def visit_FunctionDef(self, node):
        container_kind = self._stack[-1][1] if self._stack else None
        kind = "method" if container_kind == "class" else "function"
        self._add(node.name, kind, node.lineno)
        self._stack.append((node.name, kind))
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._add(node.name, "class", node.lineno)
        self._stack.append((node.name, "class"))
        self.generic_visit(node)
        self._stack.pop()

    def visit_Import(self, node):
        for a in node.names:
            self.imports.append((a.name, a.asname or a.name.split(".")[0]))

    def _relative_base(self, level):
        """from .x import y  →  base dotted del paquete actual según `level`."""
        pkg = self.dotted.rsplit(".", 1)[0] if "." in self.dotted else ""
        parts = pkg.split(".") if pkg else []
        up = level - 1
        return ".".join(parts[: len(parts) - up]) if up <= len(parts) else ""

    def visit_ImportFrom(self, node):
        if node.level:                       # import relativo
            base = self._relative_base(node.level)
            mod = f"{base}.{node.module}" if node.module else base
        else:
            mod = node.module
        if not mod:
            return
        for a in node.names:
            self.imports.append((f"{mod}.{a.name}", a.asname or a.name))


class _CallVisitor(ast.NodeVisitor):
    """Pasada 2: resuelve llamadas (tabla de imports → índice global → módulo padre)."""

    def __init__(self, file_rel, defs, name_index, symbol_by_dotted, alias_map, edges):
        self.file_rel = file_rel
        self.defs = defs
        self.name_index = name_index
        self.symbol_by_dotted = symbol_by_dotted
        self.alias_map = alias_map          # local_name -> target_dotted
        self.edges = edges
        self._stack = []
        self._params = []                   # params/locals por nivel (sombra)

    def _cur_def(self):
        if not self._stack:
            return _module_id(self.file_rel)
        q = ".".join(self._stack)
        d = self.defs.get(q)
        return d["id"] if d else _module_id(self.file_rel)

    def _enter_func(self, node):
        params = {a.arg for a in node.args.args + node.args.kwonlyargs}
        if node.args.vararg:
            params.add(node.args.vararg.arg)
        if node.args.kwarg:
            params.add(node.args.kwarg.arg)
        self._stack.append(node.name)
        self._params.append(params)
        self.generic_visit(node)
        self._params.pop()
        self._stack.pop()

    visit_FunctionDef = _enter_func
    visit_AsyncFunctionDef = _enter_func

    def visit_ClassDef(self, node):
        self._stack.append(node.name)
        self.generic_visit(node)
        self._stack.pop()

    def visit_Call(self, node):
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
        if name:
            shadowed = any(name in p for p in self._params)
            if not shadowed:
                src = self._cur_def()
                dst = None
                # 1) desambiguación por import explícito del módulo
                if name in self.alias_map:
                    dst = self.symbol_by_dotted.get(self.alias_map[name])
                # 2) índice global por nombre simple, solo si es único
                if dst is None:
                    targets = self.name_index.get(name, [])
                    if len(targets) == 1:
                        dst = targets[0]
                if dst:
                    self.edges.append({"src": src, "dst": dst, "type": "call", "resolved": True})
                else:
                    self.edges.append({"src": src, "dst": _module_id(self.file_rel),
                                       "type": "call", "resolved": False, "callee": name})
        self.generic_visit(node)


def _get_base_name(node):
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return None


def _stmt_targets(node):
    nodes_to_walk = []
    if isinstance(node, ast.Assign):
        nodes_to_walk = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor)):
        nodes_to_walk = [node.target]
    elif hasattr(node, "target"):
        nodes_to_walk = [node.target]
    else:
        nodes_to_walk = [node]

    found = set()
    for item in nodes_to_walk:
        for x in ast.walk(item):
            if isinstance(x, ast.Name):
                if isinstance(x.ctx, ast.Store):
                    found.add(x.id)
            elif isinstance(x, (ast.Attribute, ast.Subscript)):
                if isinstance(x.ctx, ast.Store):
                    base = _get_base_name(x)
                    if base:
                        found.add(base)
    return sorted(found)


def _names_loaded(node):
    names = set()
    for x in ast.walk(node):
        if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load):
            names.add(x.id)
        elif isinstance(x, ast.NamedExpr):
            for t in _stmt_targets(x.target):
                names.add(t)
    return names


def _find_named_exprs(node):
    exprs = []
    def visit(n):
        if isinstance(n, ast.NamedExpr):
            exprs.append(n)
        for field, value in ast.iter_fields(n):
            if field in ("body", "orelse", "finalbody"):
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        visit(item)
            elif isinstance(value, ast.AST):
                visit(value)
    visit(node)
    return exprs


def _safe_unparse(node, n=26):
    try:
        s = ast.unparse(node)
    except Exception:
        s = "…"
    return s[:n]


def _function_dfd(func, file_rel, func_id, name_index):
    """DFD intra-procedural Gane-Sarson ESTRICTO (Fallo 1, modelo variable=almacén):
      - parámetro      → entidad externa (fuente)           dfd_role='external'
      - variable local → UN almacén único (dedup por nombre) dfd_role='store'
      - cómputo/asig.  → proceso numerado                    dfd_role='process'
      - return         → entidad externa (sumidero)          dfd_role='external'
    Flujos store↔process etiquetados con el dato; NO hay process→process directo ni
    nodos de control (loops/condicionales) — se anota in_loop (ver DESIGN.md, Fallo 3
    sobre el bypass lineal de ramas).
    """
    nodes, edges = [], []
    counter = [0]
    param_ids, store_ids = {}, {}

    def _add(nid, kind, label, line, role, in_loop):
        node = {"id": nid, "level": "statement", "parent_id": func_id, "label": label,
                "kind": kind, "file": file_rel, "line": line, "dfd_role": role}
        if in_loop:
            node["in_loop"] = True
        nodes.append(node)
        edges.append({"src": func_id, "dst": nid, "type": "contains", "resolved": True})

    def param_node(name):
        if name not in param_ids:
            param_ids[name] = f"{func_id}#param:{name}"
            _add(param_ids[name], "parameter", name, func.lineno, "external", False)
        return param_ids[name]

    def store_node(name, line, in_loop):
        if name not in store_ids:
            store_ids[name] = f"{func_id}#store:{name}"
            _add(store_ids[name], "store", name, line, "store", in_loop)
        return store_ids[name]

    def source_of(name):                       # de dónde se LEE un nombre
        if name in store_ids:
            return store_ids[name]
        if name in param_ids:
            return param_ids[name]
        return None                            # global/builtin/free → no se rastrea

    def process(kind, label, line, reads, writes, role="process", in_loop=False):
        counter[0] += 1
        pid = f"{func_id}#p{counter[0]}@{line}"
        _add(pid, kind, label, line, role, in_loop)
        for r in sorted(reads):                # store/param → process
            s = source_of(r)
            if s:
                edges.append({"src": s, "dst": pid, "type": "data_flow", "resolved": True, "var": r})
        for w in writes:                       # process → store/param
            dst_id = param_ids[w] if w in param_ids else store_node(w, line, in_loop)
            edges.append({"src": pid, "dst": dst_id,
                          "type": "data_flow", "resolved": True, "var": w})
        return pid

    # parámetros = entidades externas (fuentes)
    if hasattr(func, "args"):
        a = func.args
        for arg in getattr(a, "posonlyargs", []) + a.args + a.kwonlyargs:
            param_node(arg.arg)
        if a.vararg:
            param_node(a.vararg.arg)
        if a.kwarg:
            param_node(a.kwarg.arg)

    def walk(stmts, in_loop=False):
        for st in stmts:
            line = getattr(st, "lineno", func.lineno)
            # Buscar NamedExprs en la sentencia actual ANTES de procesarla
            for ne in _find_named_exprs(st):
                ne_line = getattr(ne, "lineno", line)
                ne_tgts = _stmt_targets(ne)
                ne_reads = _names_loaded(ne.value)
                ne_lbl = f"{', '.join(ne_tgts) or '?'} := {_safe_unparse(ne.value, 18)}"
                process("assign", ne_lbl, ne_line, ne_reads, ne_tgts, in_loop=in_loop)

            if isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                val = getattr(st, "value", None)
                tgts = _stmt_targets(st)
                reads = _names_loaded(val) if val else set()
                if isinstance(st, ast.AugAssign):
                    reads = reads | set(tgts)          # x += y también lee x
                lbl = _safe_unparse(st, 30)
                process("assign", lbl, line, reads, tgts, in_loop=in_loop)
            elif isinstance(st, (ast.For, ast.AsyncFor)):
                tgts = _stmt_targets(st.target)
                process("iterate", f"for {', '.join(tgts) or '_'} in {_safe_unparse(st.iter, 16)}",
                        line, _names_loaded(st.iter), tgts, in_loop=in_loop)
                walk(st.body, True); walk(st.orelse, in_loop)
            elif isinstance(st, ast.While):
                walk(st.body, True); walk(st.orelse, in_loop)      # control → sin nodo
            elif isinstance(st, ast.If):
                walk(st.body, in_loop); walk(st.orelse, in_loop)   # control → sin nodo (bypass lineal)
            elif isinstance(st, ast.Return):
                process("return", "return " + (_safe_unparse(st.value, 18) if st.value else ""),
                        line, _names_loaded(st.value) if st.value else set(), (),
                        role="external", in_loop=in_loop)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            elif isinstance(st, ast.Expr):
                if isinstance(st.value, ast.NamedExpr):
                    continue
                kind = "call" if isinstance(st.value, ast.Call) else "expr"
                role = "process"
                if kind == "call":
                    f = st.value.func
                    nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
                    if nm not in name_index:
                        role = "external"          # stdlib/I-O cruza la frontera
                process(kind, _safe_unparse(st.value, 30), line, _names_loaded(st.value), (),
                        role=role, in_loop=in_loop)
            else:
                for field in ("body", "orelse", "finalbody"):
                    sub = getattr(st, field, None)
                    if isinstance(sub, list):
                        walk(sub, in_loop)

    walk(func.body)
    return nodes, edges


def _walk_funcs(tree):
    """(qualname, FunctionDef) con stack de qualname, igual que _ModuleVisitor."""
    out = []

    def rec(body, stack):
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((".".join(stack + [st.name]), st))
                rec(st.body, stack + [st.name])
            elif isinstance(st, ast.ClassDef):
                rec(st.body, stack + [st.name])
    rec(tree.body, [])
    return out


def _iter_py(project_root):
    files = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in {".git", "__pycache__", ".venv", "venv",
                                          "node_modules", ".mypy_cache", ".pytest_cache"})
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                files.append(os.path.join(dirpath, fn))
    return files


def extract(project_root):
    project_root = os.path.realpath(project_root)
    nodes, edges = {}, []
    modules = []        # (file_rel, mv)
    name_index = {}     # nombre simple -> [ids]
    symbol_by_dotted = {}   # "pkg.mod.Clase.metodo" -> id

    def add_node(nid, level, parent, label, kind, file, line, dfd_role=None, in_loop=None):
        node = {
            "id": nid,
            "level": level,
            "parent_id": parent,
            "label": label,
            "kind": kind,
            "file": file,
            "line": line,
        }
        if level == "statement" and dfd_role is not None:
            node["dfd_role"] = dfd_role
        if in_loop:
            node["in_loop"] = True
        nodes.setdefault(nid, node)

    add_node(_package_id(""), "package", None, os.path.basename(project_root), "package", ".", 0)

    py_files = _iter_py(project_root)

    # paquetes (carpetas) como jerarquía
    for f in py_files:
        pkg_rel = _rel(os.path.dirname(f), project_root)
        if pkg_rel == ".":
            continue
        parts = pkg_rel.split("/")
        for i in range(len(parts)):
            sub = "/".join(parts[: i + 1])
            parent = _package_id("/".join(parts[:i])) if i else _package_id("")
            add_node(_package_id(sub), "package", parent, parts[i], "package", sub, 0)
            edges.append({"src": parent, "dst": _package_id(sub), "type": "contains", "resolved": True})

    # PASADA 1: símbolos
    for f in py_files:
        file_rel = _rel(f, project_root)
        try:
            tree = ast.parse(open(f, encoding="utf-8").read(), filename=file_rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        dotted = _dotted(file_rel)
        mv = _ModuleVisitor(file_rel, dotted)
        mv.visit(tree)
        pkg_rel = _rel(os.path.dirname(f), project_root)
        pkg_parent = _package_id("" if pkg_rel == "." else pkg_rel)
        mid = _module_id(file_rel)
        add_node(mid, "module", pkg_parent, dotted, "module", file_rel, 0)
        edges.append({"src": pkg_parent, "dst": mid, "type": "contains", "resolved": True})
        for q, d in mv.defs.items():
            add_node(d["id"], "function", mid, q, d["kind"], file_rel, d["line"])
            name_index.setdefault(q.split(".")[-1], []).append(d["id"])
            symbol_by_dotted[f"{dotted}.{q}"] = d["id"]
        modules.append((file_rel, mv))

    # contains con jerarquía real (parent = clase/función contenedora, no el módulo)
    for file_rel, mv in modules:
        mid = _module_id(file_rel)
        for q, d in mv.defs.items():
            parent = mv.defs[d["parent_qual"]]["id"] if d["parent_qual"] in mv.defs else mid
            nodes[d["id"]]["parent_id"] = parent
            edges.append({"src": parent, "dst": d["id"], "type": "contains", "resolved": True})

    # imports entre módulos del proyecto
    dotted_to_module = {_dotted(fr): _module_id(fr) for fr, _ in modules}
    for file_rel, mv in modules:
        mid = _module_id(file_rel)
        for target, _local in mv.imports:
            for cand in (target, target.rsplit(".", 1)[0]):
                if cand in dotted_to_module and dotted_to_module[cand] != mid:
                    edges.append({"src": mid, "dst": dotted_to_module[cand],
                                  "type": "import", "resolved": True})
                    break

    # PASADA 2: llamadas
    for file_rel, mv in modules:
        alias_map = {local: target for target, local in mv.imports}
        try:
            tree = ast.parse(open(os.path.join(project_root, file_rel), encoding="utf-8").read(),
                             filename=file_rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        _CallVisitor(file_rel, mv.defs, name_index, symbol_by_dotted, alias_map, edges).visit(tree)

    # PASADA 3: DFD intra-función (sentencias + data_flow + loops for/while)
    for file_rel, mv in modules:
        try:
            tree = ast.parse(open(os.path.join(project_root, file_rel), encoding="utf-8").read(),
                             filename=file_rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for qual, fnode in _walk_funcs(tree):
            d = mv.defs.get(qual)
            if not d:
                continue
            sn, se = _function_dfd(fnode, file_rel, d["id"], name_index)
            for n in sn:
                add_node(n["id"], n["level"], n["parent_id"], n["label"], n["kind"], n["file"], n["line"], n.get("dfd_role"), n.get("in_loop"))
            edges.extend(se)

    # Colapsar cadenas de paquetes de un solo hijo
    while True:
        # 1. Contar hijos por cada nodo basándonos en parent_id
        parent_to_children = {}
        for nid, node in nodes.items():
            pid = node.get("parent_id")
            if pid:
                parent_to_children.setdefault(pid, []).append(nid)
        
        # 2. Buscar un paquete que tenga exactamente un hijo y ese hijo sea paquete
        to_collapse = None
        for nid, node in nodes.items():
            if node["level"] == "package":
                children = parent_to_children.get(nid, [])
                if len(children) == 1:
                    child_id = children[0]
                    child_node = nodes[child_id]
                    if child_node["level"] == "package":
                        to_collapse = (nid, child_id)
                        break
        
        if not to_collapse:
            break
            
        parent_id, child_id = to_collapse
        grandparent_id = nodes[parent_id].get("parent_id")
        nodes[child_id]["parent_id"] = grandparent_id
        del nodes[parent_id]
        
        # Actualizar las aristas que se referían a parent_id
        new_edges = []
        for e in edges:
            src, dst = e["src"], e["dst"]
            if src == parent_id and dst == child_id:
                continue
            if src == parent_id:
                e["src"] = child_id
            if dst == parent_id:
                e["dst"] = child_id
            new_edges.append(e)
        edges = new_edges

    # dedup y combinación de flujos paralelos de datos
    merged = {}
    for e in edges:
        k = (e["src"], e["dst"], e["type"], e.get("callee") or "")
        if k not in merged:
            merged[k] = dict(e)
        else:
            if e["type"] == "data_flow" and "var" in e and "var" in merged[k]:
                curr_vars = [v.strip() for v in merged[k]["var"].split(",")]
                if e["var"] not in curr_vars:
                    curr_vars.append(e["var"])
                    merged[k]["var"] = ", ".join(sorted(curr_vars))
    uniq = list(merged.values())

    return {"root": os.path.basename(project_root), "nodes": list(nodes.values()), "edges": uniq}
