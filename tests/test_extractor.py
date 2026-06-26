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

