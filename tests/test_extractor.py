import os
import tempfile
from plomada import extractor

def test_package_collapse():
    # Crear un proyecto temporal con una estructura de paquetes anidada de un solo hijo:
    # root/
    #   my_pkg/
    #     __init__.py
    #     a.py
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_dir = os.path.join(tmpdir, "my_pkg")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
            f.write("# init\n")
        with open(os.path.join(pkg_dir, "a.py"), "w") as f:
            f.write("def func():\n    pass\n")

        # Ejecutar extractor
        res = extractor.extract(tmpdir)

        # Debería colapsar la raíz del proyecto (tmpdir) y dejar solo "my_pkg"
        # como el nodo de nivel package raíz, eliminando el nodo redundante de la raíz.
        package_nodes = [n for n in res["nodes"] if n["level"] == "package"]
        assert len(package_nodes) == 1
        assert package_nodes[0]["label"] == "my_pkg"
        assert package_nodes[0]["parent_id"] is None

        # El módulo a.py y __init__.py deberían tener como padre a "my_pkg"
        module_nodes = [n for n in res["nodes"] if n["level"] == "module"]
        assert len(module_nodes) == 2
        assert all(m["parent_id"] == package_nodes[0]["id"] for m in module_nodes)


def test_multiple_packages_no_collapse():
    # Crear un proyecto temporal con dos paquetes hermanos:
    # root/
    #   pkg1/
    #     __init__.py
    #   pkg2/
    #     __init__.py
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg1 = os.path.join(tmpdir, "pkg1")
        pkg2 = os.path.join(tmpdir, "pkg2")
        os.makedirs(pkg1)
        os.makedirs(pkg2)
        with open(os.path.join(pkg1, "__init__.py"), "w") as f:
            f.write("# pkg1\n")
        with open(os.path.join(pkg2, "__init__.py"), "w") as f:
            f.write("# pkg2\n")

        res = extractor.extract(tmpdir)

        # Debería haber 3 packages en total (la raíz, pkg1 y pkg2)
        package_nodes = {n["id"]: n for n in res["nodes"] if n["level"] == "package"}
        assert len(package_nodes) == 3

        root_node = next(n for n in package_nodes.values() if n["parent_id"] is None)
        assert root_node["label"] == os.path.basename(tmpdir)

        # pkg1 y pkg2 deben tener como parent_id el id del nodo raíz
        sub_nodes = [n for n in package_nodes.values() if n["parent_id"] == root_node["id"]]
        assert len(sub_nodes) == 2
        labels = {n["label"] for n in sub_nodes}
        assert labels == {"pkg1", "pkg2"}


def test_dfd_gane_sarson_roles():
    # Crear un proyecto temporal con un archivo que contiene una función compleja
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_dir = os.path.join(tmpdir, "pkg")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
            f.write("# init\n")
        with open(os.path.join(pkg_dir, "calc.py"), "w") as f:
            f.write("""
def other_func(x):
    return x + 1

def compute(a, b):
    x = a + b             # assign con computo -> process
    y = x                 # assign sin computo -> store
    for item in [1, 2]:   # loop -> no node, but item source
        print(item)       # call external -> external
        other_func(y)     # call local -> process
    if x > 0:             # branch -> no node
        return y          # return -> external
""")

        res = extractor.extract(tmpdir)
        
        # Verificar que paquetes, módulos y funciones NO tienen dfd_role (sólo nivel statement)
        pkg_node = next(n for n in res["nodes"] if n["kind"] == "package")
        assert "dfd_role" not in pkg_node

        mod_node = next(n for n in res["nodes"] if n["kind"] == "module")
        assert "dfd_role" not in mod_node

        func_nodes = [n for n in res["nodes"] if n["kind"] == "function"]
        assert len(func_nodes) == 2
        assert all("dfd_role" not in f for f in func_nodes)

        # Buscar el ID de la función compute
        compute_id = next(f["id"] for f in func_nodes if f["label"] == "compute")
        
        # Obtener los statement nodes de compute
        stmt_nodes = [n for n in res["nodes"] if n["level"] == "statement" and n["parent_id"] == compute_id and n.get("graph_type") == "dfd"]
        
        # Verificar que no hay nodos de tipo loop/branch
        assert not any(n["kind"] in ("loop", "branch") for n in stmt_nodes)
        
        # Verificar parámetros como external
        param_nodes = [n for n in stmt_nodes if n["kind"] == "parameter"]
        assert len(param_nodes) == 2
        assert {p["label"] for p in param_nodes} == {"a", "b"}
        assert all(p["dfd_role"] == "external" for p in param_nodes)

        # Modelo Gane-Sarson estricto (Fallo 1 acordado): TODA asignación es un
        # PROCESO; las variables locales son nodos STORE únicos (uno por nombre).
        x_assign = next(n for n in stmt_nodes if n["kind"] == "assign" and n["label"].startswith("x ="))
        assert x_assign["dfd_role"] == "process"
        assert "in_loop" not in x_assign

        y_assign = next(n for n in stmt_nodes if n["kind"] == "assign" and n["label"].startswith("y ="))
        assert y_assign["dfd_role"] == "process"

        # almacenes: una variable = un único nodo store (dedup por nombre)
        stores = [n for n in stmt_nodes if n["dfd_role"] == "store"]
        store_names = [n["label"] for n in stores]
        assert {"x", "y"} <= set(store_names)
        assert len(store_names) == len(set(store_names)) and all(n["kind"] == "store" for n in stores)

        # print(item): call external -> external (dentro de loop)
        print_call = next(n for n in stmt_nodes if n["kind"] == "call" and n["label"].startswith("print"))
        assert print_call["dfd_role"] == "external"
        assert print_call.get("in_loop") is True

        # other_func(y): call local -> process (dentro de loop)
        other_call = next(n for n in stmt_nodes if n["kind"] == "call" and n["label"].startswith("other_func"))
        assert other_call["dfd_role"] == "process"
        assert other_call.get("in_loop") is True

        # return y -> external
        ret_stmt = next(n for n in stmt_nodes if n["kind"] == "return")
        assert ret_stmt["dfd_role"] == "external"
        assert "in_loop" not in ret_stmt


def test_dfd_edge_cases():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg_dir = os.path.join(tmpdir, "pkg")
        os.makedirs(pkg_dir)
        with open(os.path.join(pkg_dir, "__init__.py"), "w") as f:
            f.write("# init\n")
        with open(os.path.join(pkg_dir, "edge_cases.py"), "w") as f:
            f.write("""
def test_func(self, data):
    if (x := 42) > 0:
        self.value = x
    data["key"] = x
""")

        res = extractor.extract(tmpdir)
        func_node = next(n for n in res["nodes"] if n["kind"] == "function" and n["label"] == "test_func")
        func_id = func_node["id"]
        
        stmt_nodes = [n for n in res["nodes"] if n["parent_id"] == func_id and n["level"] == "statement" and n.get("graph_type") == "dfd"]
        
        # 1. Walrus operator
        # Debe haber un proceso assign para 'x := 42'
        walrus_assign = next(n for n in stmt_nodes if n["kind"] == "assign" and "x :=" in n["label"])
        assert walrus_assign["dfd_role"] == "process"
        
        # Debe haber un almacén 'x'
        x_store = next(n for n in stmt_nodes if n["kind"] == "store" and n["label"] == "x")
        assert x_store["dfd_role"] == "store"
        
        # Arista del proceso assign walrus al store 'x'
        walrus_to_store = next(e for e in res["edges"] if e["src"] == walrus_assign["id"] and e["dst"] == x_store["id"])
        assert walrus_to_store["var"] == "x"
        
        # 2. Asignación a atributos (self.value = x)
        # El target base debe ser 'self'
        attr_assign = next(n for n in stmt_nodes if n["kind"] == "assign" and "self.value" in n["label"])
        
        # 'self' es un parámetro -> external
        self_param = next(n for n in stmt_nodes if n["kind"] == "parameter" and n["label"] == "self")
        
        # Debe haber una arista desde attr_assign al parámetro self (como escritura)
        attr_to_self = next(e for e in res["edges"] if e["src"] == attr_assign["id"] and e["dst"] == self_param["id"])
        assert attr_to_self["var"] == "self"
        
        # 3. Asignación a subíndices (data["key"] = x)
        # El target base debe ser 'data'
        sub_assign = next(n for n in stmt_nodes if n["kind"] == "assign" and ('data["key"]' in n["label"] or "data['key']" in n["label"]))
        
        # 'data' es un parámetro -> external
        data_param = next(n for n in stmt_nodes if n["kind"] == "parameter" and n["label"] == "data")
        
        sub_to_data = next(e for e in res["edges"] if e["src"] == sub_assign["id"] and e["dst"] == data_param["id"])
        assert sub_to_data["var"] == "data"


def test_function_flowchart_control_flow():
    # Vista Flowchart (control de flujo): if->rombo Sí/No, for->ciclo, return->fin
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg = os.path.join(tmpdir, "pkg"); os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").write("# init\n")
        open(os.path.join(pkg, "f.py"), "w").write(
            "def compute(items):\n"
            "    total = 0\n"
            "    for x in items:\n"
            "        if x > 0:\n"
            "            total = total + x\n"
            "    return total\n")
        res = extractor.extract(tmpdir)
        fid = next(n["id"] for n in res["nodes"] if n["kind"] == "function" and n["label"] == "compute")
        flow = [n for n in res["nodes"] if n["parent_id"] == fid and n.get("graph_type") == "flow"]
        dfd = [n for n in res["nodes"] if n["parent_id"] == fid and n.get("graph_type") == "dfd"]

        # ambas vistas coexisten (toggle)
        assert flow and dfd
        kinds = {n["kind"] for n in flow}
        assert {"start", "end", "decision", "loop"} <= kinds      # símbolos de control
        # aristas de control con etiquetas Sí/No en la decisión
        fids = {n["id"] for n in flow}
        cf = [e for e in res["edges"] if e.get("type") == "control_flow" and e["src"] in fids]
        labels = {e.get("label") for e in cf}
        assert "Sí" in labels and "No" in labels
        # la decisión tiene exactamente dos salidas etiquetadas
        dec = next(n for n in flow if n["kind"] == "decision")
        dec_out = [e.get("label") for e in cf if e["src"] == dec["id"]]
        assert set(dec_out) == {"Sí", "No"}


def test_function_flowchart_enhanced_control_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg = os.path.join(tmpdir, "pkg"); os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").write("# init\n")
        open(os.path.join(pkg, "f_enhanced.py"), "w").write(
            "def complex_flow(items):\n"
            "    # Bucle con break, continue, else\n"
            "    for x in items:\n"
            "        if x == 0:\n"
            "            continue\n"
            "        elif x == 999:\n"
            "            break\n"
            "    else:\n"
            "        print('natural_end')\n"
            "    \n"
            "    # Código inalcanzable\n"
            "    return 42\n"
            "    unreachable_val = 100\n"
        )
        res = extractor.extract(tmpdir)
        fid = next(n["id"] for n in res["nodes"] if n["kind"] == "function" and n["label"] == "complex_flow")
        flow = [n for n in res["nodes"] if n["parent_id"] == fid and n.get("graph_type") == "flow"]
        fids = {n["id"] for n in flow}
        
        # Verificar que no hay ningún nodo para 'unreachable_val = 100'
        assert not any("unreachable" in (n.get("label") or "") for n in flow)
        
        # Verificar que hay un nodo break y continue en los kind de statements
        # Aunque sus kinds son process, sus etiquetas son "break" y "continue"
        break_node = next(n for n in flow if n["label"] == "break")
        continue_node = next(n for n in flow if n["label"] == "continue")
        
        cf = [e for e in res["edges"] if e.get("type") == "control_flow" and e["src"] in fids]
        
        # El continue debe enlazarse de vuelta al loop
        loop_node = next(n for n in flow if n["kind"] == "loop")
        continue_edge = next(e for e in cf if e["src"] == continue_node["id"])
        assert continue_edge["dst"] == loop_node["id"]
        
        # El break debe saltar el else (su salida va directo a la salida del loop/siguiente sentencia o fin)
        # O en este caso, se enruta a la cola de salida y va hacia 'return 42'
        return_node = next(n for n in flow if n["kind"] == "return")
        break_edge = next(e for e in cf if e["src"] == break_node["id"])
        assert break_edge["dst"] == return_node["id"]






def test_docs_types_comments_url():
    # docstrings + firma de tipos + comentarios/ADR + url_id
    with tempfile.TemporaryDirectory() as tmpdir:
        pkg = os.path.join(tmpdir, "pkg"); os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").write("# init\n")
        open(os.path.join(pkg, "m.py"), "w").write(
            '"""Módulo demo. Ver ADR-0001."""\n'
            "def saluda(nombre: str, veces: int = 1) -> str:\n"
            '    """Devuelve un saludo."""\n'
            "    # implementa ADR-0042\n"
            "    msg = nombre * veces  # arma el mensaje\n"
            "    return msg\n")
        res = extractor.extract(tmpdir)

        mod = next(n for n in res["nodes"] if n.get("url_id") == "pkg.m")
        assert mod["doc"].startswith("Módulo demo")
        assert "ADR-0001" in mod.get("adrs", [])
        assert mod["url_id"] == "pkg.m"

        fn = next(n for n in res["nodes"] if n["label"] == "saluda")
        assert fn["doc"] == "Devuelve un saludo."
        assert fn["url_id"] == "pkg.m.saluda"
        sig = fn["signature"]
        assert sig["returns"] == "str"
        params = {p["name"]: p for p in sig["params"]}
        assert params["nombre"]["type"] == "str"
        assert params["veces"]["type"] == "int" and params["veces"]["default"] == "1"
        # comentario (cabecera + inline) y ADR anclados a la sentencia msg
        msg_nodes = [n for n in res["nodes"] if n["level"] == "statement"
                     and n.get("comment") and "ADR-0042" in n.get("adrs", [])]
        assert msg_nodes, "el comentario/ADR debe anclarse a la sentencia"


def test_url_id_collision():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Crear estructura que colisione:
        # tmpdir/
        #   coll/             -> paquete coll (su url_id será "coll")
        #     __init__.py
        #   coll.py           -> módulo coll (su url_id colisionará y será "coll-1")
        pkg = os.path.join(tmpdir, "coll")
        os.makedirs(pkg)
        open(os.path.join(pkg, "__init__.py"), "w").write("# init\n")
        open(os.path.join(tmpdir, "coll.py"), "w").write(
            "def foo():\n"
            "    pass\n"
        )
        res = extractor.extract(tmpdir)
        nodes_by_url = {n["url_id"]: n for n in res["nodes"] if "url_id" in n}
        assert "coll" in nodes_by_url
        assert "coll-1" in nodes_by_url
