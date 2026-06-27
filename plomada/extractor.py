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
import re
import tokenize

_ADR_RE = re.compile(r"ADR[-\s]?\d{1,5}", re.I)


def _find_adrs(*texts):
    out = []
    for t in texts:
        if t:
            for m in _ADR_RE.findall(t):
                tag = re.sub(r"[\s_]", "-", m.upper())
                if tag not in out:
                    out.append(tag)
    return out


def _signature(func):
    """Firma de tipos: params [{name,type,default}] + returns (desde anotaciones)."""
    a = func.args
    pos = getattr(a, "posonlyargs", []) + a.args
    defaults = list(a.defaults)
    pad = [None] * (len(pos) - len(defaults))
    params = []
    for arg, dflt in zip(pos, pad + defaults):
        params.append({"name": arg.arg,
                       "type": _safe_unparse(arg.annotation) if arg.annotation else None,
                       "default": _safe_unparse(dflt) if dflt is not None else None})
    if a.vararg:
        params.append({"name": "*" + a.vararg.arg,
                       "type": _safe_unparse(a.vararg.annotation) if a.vararg.annotation else None,
                       "default": None})
    for arg, dflt in zip(a.kwonlyargs, a.kw_defaults):
        params.append({"name": arg.arg,
                       "type": _safe_unparse(arg.annotation) if arg.annotation else None,
                       "default": _safe_unparse(dflt) if dflt is not None else None})
    if a.kwarg:
        params.append({"name": "**" + a.kwarg.arg,
                       "type": _safe_unparse(a.kwarg.annotation) if a.kwarg.annotation else None,
                       "default": None})
    return {"params": params,
            "returns": _safe_unparse(func.returns) if func.returns else None}


def _extract_comments(path):
    """Comentarios vía tokenize (ast los descarta). Devuelve (full, inline):
    full[lineno]=texto (comentario de línea completa), inline[lineno]=texto (al final de código)."""
    full, inline = {}, {}
    try:
        src = open(path, encoding="utf-8").read().splitlines()
        with open(path, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type == tokenize.COMMENT:
                    ln = tok.start[0]
                    txt = tok.string.lstrip("#").strip()
                    line = src[ln - 1] if 0 <= ln - 1 < len(src) else ""
                    (full if line.lstrip().startswith("#") else inline)[ln] = txt
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError, OSError):
        pass
    return full, inline


def _comment_for(full, inline, line, src=None):
    """Comentario asociado a una línea: bloque de cabecera contiguo arriba + inline."""
    parts, L = [], line - 1
    block = []
    blanks = 0
    while L > 0:
        if L in full:
            block.append(full[L])
            blanks = 0
        else:
            line_str = src[L - 1].strip() if src and 0 <= L - 1 < len(src) else ""
            if line_str == "":
                blanks += 1
                if blanks > 1:  # límite de 1 línea vacía
                    break
            else:
                break
        L -= 1
    parts += reversed(block)
    if line in inline:
        parts.append(inline[line])
    return " · ".join(parts) if parts else None


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

    def _add(self, name, kind, lineno, doc=None, signature=None):
        q = ".".join([n for n, _ in self._stack] + [name])
        parent_qual = ".".join(n for n, _ in self._stack) or None
        self.defs[q] = {"id": _node_id(self.file_rel, q, lineno), "kind": kind,
                        "qualname": q, "line": lineno, "parent_qual": parent_qual,
                        "doc": doc, "signature": signature}

    def visit_FunctionDef(self, node):
        container_kind = self._stack[-1][1] if self._stack else None
        kind = "method" if container_kind == "class" else "function"
        self._add(node.name, kind, node.lineno,
                  doc=ast.get_docstring(node), signature=_signature(node))
        self._stack.append((node.name, kind))
        self.generic_visit(node)
        self._stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._add(node.name, "class", node.lineno, doc=ast.get_docstring(node))
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


def _safe_unparse(node, n=None):
    try:
        s = ast.unparse(node)
    except Exception:
        s = "…"
    return s[:n] if n is not None else s


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
                if isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                    continue                       # docstring / string suelto → no es nodo del grafo
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


def _classify_stmt(st, name_index):
    """Clasifica una sentencia secuencial en su símbolo de flowchart."""
    if isinstance(st, (ast.Assign, ast.AnnAssign)) and isinstance(getattr(st, "value", None), ast.Call):
        fn = st.value.func
        nm = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if nm == "input":
            return "read", "leer " + (", ".join(_stmt_targets(st)) or "")
        if nm in name_index:
            return "call", _safe_unparse(st.value, 26)
    if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
        fn = st.value.func
        nm = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
        if nm == "print":
            return "write", "escribir " + _safe_unparse(st.value, 20)
        if nm in name_index:
            return "call", _safe_unparse(st.value, 26)
        return "process", _safe_unparse(st.value, 28)
    if isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        tg = ", ".join(_stmt_targets(st)) or "?"
        val = getattr(st, "value", None)
        return "assign", tg + (" = " + _safe_unparse(val, 16) if val else "")
    return "process", _safe_unparse(st, 26)


def _function_flowchart(func, file_rel, func_id, name_index):
    """Diagrama de FLUJO (control) estilo ISO 5807 / DFD-SMART: inicio/fin (óvalo),
    asignación/proceso (rectángulo), decisión (rombo), lectura/escritura (paralelogramo),
    llamada (subprograma), ciclo. Aristas = control de flujo con etiquetas Sí/No.
    walk(stmts, incoming) devuelve las colas [(src_id,label)] pendientes de enlazar."""
    nodes, edges = [], []
    counter = [0]

    def add(kind, label, line):
        counter[0] += 1
        i = f"{func_id}#c{counter[0]}@{line}"
        nodes.append({"id": i, "level": "statement", "parent_id": func_id, "label": label,
                      "kind": kind, "file": file_rel, "line": line, "graph_type": "flow"})
        edges.append({"src": func_id, "dst": i, "type": "contains", "resolved": True,
                      "graph_type": "flow"})
        return i

    def link(src, dst, label=None):
        e = {"src": src, "dst": dst, "type": "control_flow", "resolved": True, "graph_type": "flow"}
        if label:
            e["label"] = label
        edges.append(e)

    start = add("start", "inicio", func.lineno)
    end = add("end", "fin", func.lineno)

    def walk(stmts, incoming, break_targets=None, continue_target=None):
        cur = list(incoming)                         # [(src_id, label)]
        for st in stmts:
            if not cur:
                return []                            # Código inalcanzable
            line = getattr(st, "lineno", func.lineno)
            if isinstance(st, ast.Return):
                r = add("return", "return " + (_safe_unparse(st.value, 16) if st.value else ""), line)
                for s, lbl in cur:
                    link(s, r, lbl)
                link(r, end)
                return []                            # lo siguiente es inalcanzable
            elif isinstance(st, ast.Break):
                b = add("process", "break", line)
                for s, lbl in cur:
                    link(s, b, lbl)
                if break_targets is not None:
                    break_targets.append((b, None))
                return []
            elif isinstance(st, ast.Continue):
                c = add("process", "continue", line)
                for s, lbl in cur:
                    link(s, c, lbl)
                if continue_target is not None:
                    link(c, continue_target)
                return []
            elif isinstance(st, ast.If):
                d = add("decision", _safe_unparse(st.test, 22) + " ?", line)
                for s, lbl in cur:
                    link(s, d, lbl)
                t_true = walk(st.body, [(d, "Sí")], break_targets, continue_target)
                t_false = walk(st.orelse, [(d, "No")], break_targets, continue_target) if st.orelse else [(d, "No")]
                cur = t_true + t_false
            elif isinstance(st, ast.While):
                d = add("decision", "mientras " + _safe_unparse(st.test, 16) + " ?", line)
                for s, lbl in cur:
                    link(s, d, lbl)
                my_breaks = []
                body_exits = walk(st.body, [(d, "Sí")], break_targets=my_breaks, continue_target=d)
                for s, lbl in body_exits:
                    link(s, d, lbl)
                normal_exit = [(d, "No")]
                if st.orelse:
                    normal_exit = walk(st.orelse, normal_exit, break_targets, continue_target)
                cur = normal_exit + my_breaks
            elif isinstance(st, (ast.For, ast.AsyncFor)):
                lp = add("loop", "para " + (", ".join(_stmt_targets(st.target)) or "_")
                         + " en " + _safe_unparse(st.iter, 12), line)
                for s, lbl in cur:
                    link(s, lp, lbl)
                my_breaks = []
                body_exits = walk(st.body, [(lp, "ciclo")], break_targets=my_breaks, continue_target=lp)
                for s, lbl in body_exits:
                    link(s, lp, lbl)
                normal_exit = [(lp, "fin")]
                if st.orelse:
                    normal_exit = walk(st.orelse, normal_exit, break_targets, continue_target)
                cur = normal_exit + my_breaks
            elif isinstance(st, (ast.With, ast.AsyncWith)):
                cur = walk(st.body, cur, break_targets, continue_target)
            elif isinstance(st, ast.Try):
                body_exits = walk(st.body, cur, break_targets, continue_target)
                if st.orelse:
                    body_exits = walk(st.orelse, body_exits, break_targets, continue_target)
                handler_exits = []
                for handler in st.handlers:
                    handler_exits.extend(walk(handler.body, cur, break_targets, continue_target))
                combined_exits = body_exits + handler_exits
                if st.finalbody:
                    cur = walk(st.finalbody, combined_exits, break_targets, continue_target)
                else:
                    cur = combined_exits
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
                continue                           # docstring / string suelto → no es nodo del flowchart
            else:
                kind, label = _classify_stmt(st, name_index)
                n = add(kind, label, line)
                for s, lbl in cur:
                    link(s, n, lbl)
                cur = [(n, None)]
        return cur

    for s, lbl in walk(func.body, [(start, None)]):
        link(s, end, lbl)
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

    comments_by_file = {}                     # file_rel -> (full, inline)
    used_url_ids = set()

    def get_url_id(base_str):
        clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", base_str)
        if clean not in used_url_ids:
            used_url_ids.add(clean)
            return clean
        i = 1
        while f"{clean}-{i}" in used_url_ids:
            i += 1
        res = f"{clean}-{i}"
        used_url_ids.add(res)
        return res

    def add_node(nid, level, parent, label, kind, file, line, dfd_role=None, in_loop=None,
                 graph_type=None, extra=None):
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
        if graph_type:                       # "dfd" (flujo de datos) | "flow" (control/flowchart)
            node["graph_type"] = graph_type
        if extra:                            # doc, signature, comment, adrs, url_id, …
            for k, v in extra.items():
                if v:
                    node[k] = v
        nodes.setdefault(nid, node)

    add_node(_package_id(""), "package", None, os.path.basename(project_root), "package", ".", 0,
             extra={"url_id": get_url_id(os.path.basename(project_root))})

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
            add_node(_package_id(sub), "package", parent, parts[i], "package", sub, 0,
                     extra={"url_id": get_url_id(sub.replace("/", "."))})
            edges.append({"src": parent, "dst": _package_id(sub), "type": "contains", "resolved": True})

    # PASADA 1: símbolos
    for f in py_files:
        file_rel = _rel(f, project_root)
        try:
            src_content = open(f, encoding="utf-8").read()
            tree = ast.parse(src_content, filename=file_rel)
            src_lines = src_content.splitlines()
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        dotted = _dotted(file_rel)
        mv = _ModuleVisitor(file_rel, dotted)
        mv.visit(tree)
        full, inline = _extract_comments(f)              # comentarios vía tokenize
        comments_by_file[file_rel] = (full, inline)
        mod_doc = ast.get_docstring(tree)
        pkg_rel = _rel(os.path.dirname(f), project_root)
        pkg_parent = _package_id("" if pkg_rel == "." else pkg_rel)
        mid = _module_id(file_rel)
        add_node(mid, "module", pkg_parent, dotted, "module", file_rel, 0,
                 extra={"url_id": get_url_id(dotted), "doc": mod_doc, "adrs": _find_adrs(mod_doc)})
        edges.append({"src": pkg_parent, "dst": mid, "type": "contains", "resolved": True})
        for q, d in mv.defs.items():
            cmt = _comment_for(full, inline, d["line"], src_lines)
            add_node(d["id"], "function", mid, q, d["kind"], file_rel, d["line"],
                     extra={"url_id": get_url_id(f"{dotted}.{q}"), "doc": d.get("doc"),
                            "signature": d.get("signature"), "comment": cmt,
                            "adrs": _find_adrs(d.get("doc"), cmt)})
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

    # PASADA 3: vistas intra-función — DFD (datos) y Flowchart (control de flujo)
    for file_rel, mv in modules:
        try:
            src_content = open(os.path.join(project_root, file_rel), encoding="utf-8").read()
            tree = ast.parse(src_content, filename=file_rel)
            src_lines = src_content.splitlines()
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        full, inline = comments_by_file.get(file_rel, ({}, {}))

        def _stmt_extra(line):                  # comentario/ADR anclado a la línea
            cmt = _comment_for(full, inline, line, src_lines)   # bloque full-line arriba + inline
            return {"comment": cmt, "adrs": _find_adrs(cmt)} if cmt else None

        for qual, fnode in _walk_funcs(tree):
            d = mv.defs.get(qual)
            if not d:
                continue
            # vista DFD (flujo de datos)
            sn, se = _function_dfd(fnode, file_rel, d["id"], name_index)
            for n in sn:
                add_node(n["id"], n["level"], n["parent_id"], n["label"], n["kind"], n["file"],
                         n["line"], n.get("dfd_role"), n.get("in_loop"), graph_type="dfd",
                         extra=_stmt_extra(n["line"]))
            for e in se:
                e.setdefault("graph_type", "dfd")
            edges.extend(se)
            # vista Flowchart (control de flujo)
            fn_, fe = _function_flowchart(fnode, file_rel, d["id"], name_index)
            for n in fn_:
                add_node(n["id"], n["level"], n["parent_id"], n["label"], n["kind"], n["file"],
                         n["line"], graph_type="flow", extra=_stmt_extra(n["line"]))
            edges.extend(fe)

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
