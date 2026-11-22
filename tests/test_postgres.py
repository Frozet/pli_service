import json
import re
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter

import createdb
from database import Database
from security import password_hasher
from tests.test_diagnostics import sample_png

PASSWORD = "example-password-long"


def token(client, path):
    assert client.get(path).status_code == 200
    with client.session_transaction() as session:
        return session["csrf_token"]


def login(app, username):
    client = app.test_client()
    csrf = token(client, "/adm_login")
    response = client.post("/adm_login", data={"username": username, "password": PASSWORD, "csrf_token": csrf})
    assert response.status_code == 303
    return client


@pytest.fixture
def installed(app, postgres):
    dsn, _ = postgres
    createdb.migrate()
    createdb.migrate()
    database = Database(dsn)
    app.extensions["db"] = database
    app.config["YANDEX_MAPS_API_KEY"] = "test-public-map-key"
    hashed = password_hasher.hash(PASSWORD)
    with database.transaction() as cursor:
        cursor.execute("INSERT INTO areas (name) VALUES ('Первый'), ('Второй')")
        cursor.execute("""
            INSERT INTO users (username, full_name, role, password, areaid) VALUES
              ('owner', 'Администратор', 'Admin', %s, NULL),
              ('editor', 'Редактор', 'User', %s, NULL),
              ('viewer', 'Наблюдатель', 'Viewer', %s, 1)
        """, (hashed, sha256(PASSWORD.encode()).hexdigest(), hashed))
    yield app, database
    if database.pool is not None:
        database.pool.closeall()


def new_diagnostic(editor, data, **overrides):
    csrf = token(editor, "/add_diagnostic/0")
    response = editor.post("/submit_form", data=data | overrides | {"csrf_token": csrf})
    assert response.status_code == 303, response.text
    return int(response.location.rsplit("/", 1)[1])


def test_scope_validation_and_session_revocation(installed, diagnostic_form_data):
    app, db = installed
    editor = login(app, "editor")
    assert app.test_client().get("/ready").status_code == 200
    first = new_diagnostic(editor, diagnostic_form_data, name="Доступная запись")
    second = new_diagnostic(editor, diagnostic_form_data, areaid="2", name="Чужая запись",
                            photos=(BytesIO(sample_png()), "photo.png"))

    with db.transaction() as cursor:
        cursor.execute("SELECT password FROM users WHERE username='editor'")
        assert cursor.fetchone()["password"].startswith("$argon2id$")
        cursor.execute("SELECT id FROM diagnostic_attachments WHERE diagnostic_id=%s", (second,))
        file_id = cursor.fetchone()["id"]

    assert editor.get(f"/diagnostic/{second}/attachments/{file_id}").data == sample_png()
    viewer = login(app, "viewer")
    for path in ["/view_diagnostics?search_query=запись", "/annual_report?year=2024"]:
        page = viewer.get(path)
        assert page.status_code == 200
        assert "Доступная запись" in page.text
        assert "Чужая запись" not in page.text

    map_page = viewer.get("/map")
    assert map_page.status_code == 200
    payload = re.search(r'<script\b[^>]*\bid="map-diagnostics"[^>]*>(.*?)</script>', map_page.text, flags=re.DOTALL)
    assert payload is not None
    records = json.loads(payload.group(1))
    assert [(record["id"], record["short_title"]) for record in records] == [(first, "Доступная запись")]

    page = viewer.get("/view_diagnostics?start_date=2024-03-01&end_date=2024-03-10")
    assert "20.5 м" in page.text and "start_date=2024-03-01" in page.text
    assert viewer.get(f"/diagnostic_page/{first}").status_code == 200
    assert viewer.get(f"/diagnostic/{first}/graph.png").mimetype == "image/png"
    assert editor.get("/add_diagnostic/999").status_code == 404
    for path in [f"/diagnostic_page/{second}", f"/diagnostic/{second}/graph.png",
                 f"/diagnostic/{second}/generate_pdf", f"/diagnostic/{second}/attachments/{file_id}"]:
        assert viewer.get(path).status_code == 404
    assert viewer.post(f"/delete/{first}").status_code == 403
    assert viewer.post("/submit_form").status_code == 403
    assert viewer.get("/admin_diagnostics").status_code == 403
    assert editor.get("/view_diagnostics?sort_by=unknown").status_code == 400
    with db.transaction() as cursor:
        cursor.execute("UPDATE users SET areaid=2 WHERE username='viewer'")
    assert viewer.get(f"/diagnostic_page/{first}").status_code == 302


def test_edit_roundtrip_and_upload_rollback(installed, diagnostic_form_data, monkeypatch):
    app, db = installed
    editor = login(app, "editor")
    diagnostic_id = new_diagnostic(editor, diagnostic_form_data, photos=(BytesIO(sample_png()), "photo.png"))
    path = f"/add_diagnostic/{diagnostic_id}"
    csrf = token(editor, path)
    form = editor.get(path)
    assert "Трещина, скол; стык" in form.text and 'name="well2_1"' in form.text
    with db.transaction() as cursor:
        cursor.execute("SELECT id, stored_name FROM diagnostic_attachments WHERE diagnostic_id=%s", (diagnostic_id,))
        file = cursor.fetchone()

    stored = app.extensions["attachments"].root / file["stored_name"]
    assert stored.is_file()
    data = diagnostic_form_data | {"name": "Исправленное название", "version": "1", "csrf_token": csrf,
                                   "remove_attachment": str(file["id"])}
    store = app.extensions["attachments"]
    write = store.write

    def fail_after_write(uploads, written):
        write(uploads, written)
        raise OSError("simulated storage failure")

    with monkeypatch.context() as patch:
        patch.setattr(store, "write", fail_after_write)
        response = editor.post(path, data=data | {"photos": (BytesIO(sample_png()), "new.png")})
    assert response.status_code == 503
    assert [path.name for path in store.root.iterdir()] == [stored.name]

    assert editor.post(path, data=data).status_code == 303
    assert not stored.exists()
    assert editor.post(path, data=data).status_code == 409
    assert editor.get(f"/delete/{diagnostic_id}").status_code == 405
    assert editor.post(f"/delete/{diagnostic_id}").status_code == 400
    detail = editor.get(f"/diagnostic_page/{diagnostic_id}")
    assert "Трещина, скол; стык" in detail.text and "Смещение" in detail.text
    assert "Исправленное название" in editor.get("/annual_report?year=2024").text


def test_migrate_legacy_data_preserves_raw_values(postgres):
    _, connect = postgres
    with connect() as connection, connection, connection.cursor() as cursor:
        cursor.execute((Path(createdb.MIGRATIONS) / "001_initial.sql").read_text())
        cursor.execute("""
            INSERT INTO diagnostics (date, coordinates, distance, count_of_well, flow,
                       slope_between_wells, distance_between_wells, problems, problems_distances,
                       timestampdata, photo_path)
            VALUES ('2024-03-03', '52,104', 20, 'А,Б,Б,В', 'по течению,по течению',
                    'в норме,в норме', '10,10', 'A,B;C', '2,3', '2026-01-01', 'uploads/legacy.png')
        """)
    createdb.migrate()
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT survey_date::text, problems FROM diagnostics")
        assert cursor.fetchone() == ("2024-03-03", "A,B;C")
        cursor.execute("SELECT count(*) FROM diagnostic_spans")
        assert cursor.fetchone() == (2,)
        cursor.execute("SELECT field FROM diagnostic_migration_issues")
        assert cursor.fetchall() == [("defects",)]
        cursor.execute("SELECT legacy, stored_name FROM diagnostic_attachments")
        assert cursor.fetchone() == (True, "legacy.png")


def test_pdf_report_contains_russian_text_and_appendix(installed, diagnostic_form_data):
    pytest.importorskip("weasyprint")
    from pypdf import PdfReader

    app, _ = installed
    editor = login(app, "editor")
    appendix = BytesIO()
    with PdfWriter() as writer:
        writer.add_blank_page(width=100, height=100)
        writer.write(appendix)
    diagnostic_id = new_diagnostic(
        editor, diagnostic_form_data, photos=(BytesIO(sample_png()), "photo.png"),
        slope_graph=(BytesIO(appendix.getvalue()), "profile.pdf"),
    )
    report = editor.get(f"/diagnostic/{diagnostic_id}/generate_pdf")
    assert report.status_code == 200
    reader = PdfReader(BytesIO(report.data))
    assert len(reader.pages) >= 2
    assert "Иркутск" in reader.pages[0].extract_text()
