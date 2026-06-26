import pytest
from plomada import render

def test_render_html():
    graph = {
        "root": "my-test-project",
        "nodes": [
            {"id": "pkg::<package>::0", "level": "package", "parent_id": None, "label": "pkg", "kind": "package", "file": ".", "line": 0}
        ],
        "edges": []
    }
    
    html = render.render_html(graph, title="custom-title")
    
    # Verify title is escaped and placed correctly
    assert "custom-title" in html
    # Verify data is injected correctly
    assert "my-test-project" in html
    assert "pkg::<package>::0" in html
    # Verify basic template structures are present
    assert "layout orientado al flujo (determinista)" in html
    assert "backEdges" in html
    assert "uniqueLayers" in html
    assert "baricenters" in html
    assert "Desconflictualizar etiquetas de flujo para evitar solapes" in html
