import pytest
from plomada import model

def test_build_model():
    graph = {
        "root": "test-project",
        "nodes": [
            {"id": "pkg::<package>::0", "level": "package", "parent_id": None, "label": "pkg", "kind": "package", "file": ".", "line": 0},
            {"id": "pkg/mod.py::<module>::0", "level": "module", "parent_id": "pkg::<package>::0", "label": "pkg.mod", "kind": "module", "file": "pkg/mod.py", "line": 0},
            {"id": "pkg/mod.py::func::10", "level": "function", "parent_id": "pkg/mod.py::<module>::0", "label": "func", "kind": "function", "file": "pkg/mod.py", "line": 10}
        ],
        "edges": [
            {"src": "pkg::<package>::0", "dst": "pkg/mod.py::<module>::0", "type": "contains"},
            {"src": "pkg/mod.py::<module>::0", "dst": "pkg/mod.py::func::10", "type": "contains"},
            {"src": "pkg/mod.py::func::10", "dst": "pkg/mod.py::func::10", "type": "call", "resolved": True},
            # Edge pointing to non-existent node (should be filtered out)
            {"src": "pkg/mod.py::func::10", "dst": "non_existent", "type": "call"}
        ]
    }

    g = model.build_model(graph)

    # Filtered edges check
    assert len(g["edges"]) == 3
    assert not any(e["dst"] == "non_existent" for e in g["edges"])

    # Metrics check
    func_node = next(n for n in g["nodes"] if n["id"] == "pkg/mod.py::func::10")
    assert func_node["metrics"]["fan_in"] == 1
    assert func_node["metrics"]["fan_out"] == 1

    # Stats check
    assert g["stats"]["packages"] == 1
    assert g["stats"]["modules"] == 1
    assert g["stats"]["functions"] == 1
    assert g["stats"]["calls"] == 1
