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


def test_detect_cycles():
    # Setup a complex graph with:
    # 1. Mutual recursion (func_a <-> func_b)
    # 2. Direct recursion (func_c -> func_c)
    # 3. Direct recursion inside mutual recursion (func_a -> func_a) - should be absorbed into 1 loop
    # 4. A normal call without cycle (func_d -> func_a)
    # 5. Unresolved call forming a potential loop (func_e -> func_e, resolved=False) - should be ignored
    graph = {
        "root": "test-cycles",
        "nodes": [
            {"id": "func_a", "level": "function", "parent_id": None, "label": "func_a", "kind": "function", "file": "f.py", "line": 1},
            {"id": "func_b", "level": "function", "parent_id": None, "label": "func_b", "kind": "function", "file": "f.py", "line": 2},
            {"id": "func_c", "level": "function", "parent_id": None, "label": "func_c", "kind": "function", "file": "f.py", "line": 3},
            {"id": "func_d", "level": "function", "parent_id": None, "label": "func_d", "kind": "function", "file": "f.py", "line": 4},
            {"id": "func_e", "level": "function", "parent_id": None, "label": "func_e", "kind": "function", "file": "f.py", "line": 5},
        ],
        "edges": [
            # Mutual recursion: a <-> b
            {"src": "func_a", "dst": "func_b", "type": "call", "resolved": True},
            {"src": "func_b", "dst": "func_a", "type": "call", "resolved": True},
            # Direct recursion inside mutual: a -> a
            {"src": "func_a", "dst": "func_a", "type": "call", "resolved": True},
            # Direct recursion: c -> c
            {"src": "func_c", "dst": "func_c", "type": "call", "resolved": True},
            # Normal call: d -> a
            {"src": "func_d", "dst": "func_a", "type": "call", "resolved": True},
            # Unresolved circular call: e -> e
            {"src": "func_e", "dst": "func_e", "type": "call", "resolved": False},
        ]
    }

    g = model.build_model(graph)

    # func_a, func_b, func_c should be recursive. func_d, func_e should not.
    nodes_map = {n["id"]: n for n in g["nodes"]}
    assert nodes_map["func_a"]["recursive"] is True
    assert nodes_map["func_b"]["recursive"] is True
    assert nodes_map["func_c"]["recursive"] is True
    assert nodes_map["func_d"]["recursive"] is False
    assert nodes_map["func_e"]["recursive"] is False

    # Check that in_cycle is set on edges correctly
    # we have 6 edges in input (unresolved one is kept because src/dst exist in nodes, but e.get("resolved") is False)
    # The build_model filters edges that don't exist. In our input, all nodes exist.
    # So we should have 6 edges.
    assert len(g["edges"]) == 6
    edges_map = {(e["src"], e["dst"], e.get("resolved")): e for e in g["edges"]}

    assert edges_map[("func_a", "func_b", True)]["in_cycle"] is True
    assert edges_map[("func_b", "func_a", True)]["in_cycle"] is True
    assert edges_map[("func_a", "func_a", True)]["in_cycle"] is True
    assert edges_map[("func_c", "func_c", True)]["in_cycle"] is True
    assert edges_map[("func_d", "func_a", True)]["in_cycle"] is False
    assert edges_map[("func_e", "func_e", False)].get("in_cycle") is not True

    # Stats:
    # 2 loops (1 mutual loop `{func_a, func_b}` which absorbs the self-call of func_a, and 1 self-call loop `{func_c}`)
    # 3 recursive functions (func_a, func_b, func_c)
    assert g["stats"]["loops"] == 2
    assert g["stats"]["recursive_functions"] == 3

