from pathlib import Path

from app import create_app


def test_base_layout_includes_dark_mode_toggle():
    app = create_app()
    app.testing = True
    client = app.test_client()

    response = client.get("/weekly-planner")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'darkMode: "class"' in html
    assert 'localStorage.getItem("appTheme")' in html
    assert "data-theme-toggle" in html


def test_common_js_saves_dark_mode_preference():
    common_js = (Path(__file__).resolve().parents[1] / "static/assets/js/common.js").read_text(encoding="utf-8")

    assert "data-theme-toggle" in common_js
    assert 'localStorage.setItem("appTheme"' in common_js
