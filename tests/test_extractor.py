import os
import tempfile
import shutil
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
        stmt_nodes = [n for n in res["nodes"] if n["level"] == "statement" and n["parent_id"] == compute_id]
        
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
        
        stmt_nodes = [n for n in res["nodes"] if n["parent_id"] == func_id and n["level"] == "statement"]
        
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



