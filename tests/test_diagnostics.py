from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage, MultiDict

from attachments import validate_uploads
from db_requests import NO_ASSIGNED_AREA, DiagnosticFilters, visible_area
from diagnostic_data import DiagnosticInput, FormError, Span, legacy_defects
from graph_generate import generate_diagnostic_plot


def test_form_pairs_by_index_and_preserves_punctuation(diagnostic_form_data):
    form = MultiDict(reversed(list(diagnostic_form_data.items())))
    data = DiagnosticInput.from_form(form)
    assert [span.last_well for span in data.spans] == ["Б", "В"]
    assert [span.flow for span in data.spans] == ["по течению", "против течения"]
    assert data.defects[0] == ("Трещина, скол; стык", Decimal("3.2"))
    assert len(data.defects) == 2


@pytest.mark.parametrize("change", [
    {"problem_5": "Без расстояния"}, {"problemDistance_5": "2"}, {"problemDistance_3": "21"},
    {"span_2": "0"}, {"distance": "20"}, {"coordinates": "90.1,104.31"}, {"slope_0": "неизвестно"},
])
def test_invalid_diagnostic_is_rejected(diagnostic_form_data, change):
    with pytest.raises(FormError):
        DiagnosticInput.from_form(MultiDict(diagnostic_form_data | change))


def test_legacy_defects_with_trailing_empty_fields_and_ambiguous_values():
    assert legacy_defects({"problems": "Трещина,Смещение,", "problems_distances": "2,3,"}) == (
        ("Трещина", 2), ("Смещение", 3),
    )
    assert legacy_defects({"problems": "Трещина, скол", "problems_distances": "2"})[0].description == "Трещина, скол"
    with pytest.raises(FormError):
        legacy_defects({"problems": "A,B;C", "problems_distances": "2,3"})


def test_filter_validation_and_viewer_without_area():
    assert DiagnosticFilters.from_args({"areaFilter": ""}, admin=True).areaid is None
    assert visible_area({"role": "Viewer", "areaid": None}) == NO_ASSIGNED_AREA
    for args in ({"sort_by": "unknown"}, {"order": "unknown"}, {"page": "0"}, {"areaFilter": "east"},
                 {"start_date": "2024-04-01", "end_date": "2024-03-01"}):
        with pytest.raises(FormError):
            DiagnosticFilters.from_args(args)


def test_graph_handles_legacy_categories_and_reuses_cached_pixels():
    spans = (Span("А", "по течению", "старый уклон", Decimal("1.2"), "Б"),)
    graph = generate_diagnostic_plot("КК", spans, ())
    assert graph.startswith(b"\x89PNG")
    assert generate_diagnostic_plot("КК", spans, ()) is graph


def sample_png():
    file = BytesIO()
    with Image.new("RGB", (3, 3), "blue") as image:
        image.save(file, format="PNG")
    return file.getvalue()


def test_attachment_checks_the_field_and_actual_format():
    photo = FileStorage(BytesIO(sample_png()), filename="camera.png")
    result = validate_uploads(MultiDict({"photos": photo}))
    assert result[0].media_type == "image/png"
    assert result[0].name != photo.filename
    for field, filename, payload in [
        ("photos", "x.png", b"broken image"),
        ("photos", "x.pdf", b"%PDF-1.4"),
        ("slope_graph", "x.png", sample_png()),
        ("slope_graph", "x.pdf", b"%PDF-1.4"),
    ]:
        with pytest.raises(FormError):
            validate_uploads(MultiDict({field: FileStorage(BytesIO(payload), filename=filename)}))


def test_public_routes_and_static_guard(app):
    client = app.test_client()
    for name in app.jinja_env.list_templates(extensions=['html']):
        app.jinja_env.get_template(name)
    for path in ("/", "/index", "/about", "/adm_login", "/static/favicon.ico"):
        assert client.get(path).status_code == 200
    for path in ("/static/secret_key.txt", "/static/uploads/example.png"):
        assert client.get(path).status_code == 404
    assert client.get("/map").status_code == 302
    assert client.get("/logout").status_code == 405
    assert client.post("/delete/1").status_code == 401
    assert client.post("/adm_login", data={"username": "guest"}).status_code == 400


def test_roles_and_csrf_are_checked_before_storage_access(app, monkeypatch):
    from flask import g

    from security import csrf_token

    account = {"role": "Viewer", "id": 1}
    monkeypatch.setattr("app.load_user", lambda: setattr(g, "user", account.copy()))
    client = app.test_client()
    assert client.post("/submit_form").status_code == 403
    assert client.post("/edit_form/1").status_code == 403
    assert client.post("/admin_delete_area/1").status_code == 403
    assert client.get("/admin_diagnostics").status_code == 403
    account["role"] = "User"
    assert client.post("/submit_form").status_code == 400
    assert client.post("/delete/1").status_code == 400
    with app.test_request_context():
        assert csrf_token() == csrf_token()


def test_render_edit_form_with_multiple_spans(app, diagnostic_form_data):
    from datetime import date

    from flask import g, render_template

    data = DiagnosticInput.from_form(MultiDict(diagnostic_form_data))
    with app.test_request_context():
        g.user = {"id": 1, "role": "User"}
        form = render_template(
            "add_panel.html", diagnostic_id=12, values={
                "name": data.short_title, "date": date(2024, 3, 3), "coordinates": "52.27,104.31", "version": 1,
            }, spans=data.spans, defects=data.defects, areas=[{"id": 1, "name": "Участок"}],
            flows=("против течения", "по течению"), slopes=("отличный", "в норме", "в горизонте", "в контруклоне"),
            max_spans=100, max_defects=200,
        )
    assert 'action="/add_diagnostic/12"' in form
    assert 'name="version" value="1"' in form
    assert 'name="well2_1" value="В"' in form
    assert "Трещина, скол; стык" in form


def test_private_attachment_storage_records_and_compensates_writes(app):
    from attachments import Upload

    store = app.extensions["attachments"]
    upload = Upload("photo", "a" * 32 + ".png", "image/png", sample_png())
    written = []
    store.write([upload], written)
    assert store.read({"stored_name": upload.name, "legacy": False}) == upload.data
    assert len(written) == 1
    store.discard(written)
    assert not written[0].exists()
