from contextlib import contextmanager
from uuid import uuid4

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extensions import make_dsn

import createdb
from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({
        "SECRET_KEY": "test-secret-" * 5,
        "TESTING": True,
        "SESSION_COOKIE_SECURE": False,
        "UPLOAD_FOLDER": tmp_path / "uploads",
        "LEGACY_UPLOAD_FOLDER": tmp_path / "legacy",
        "YANDEX_MAPS_API_KEY": "",
    })


@pytest.fixture
def diagnostic_form_data():
    return {
        "name": "Участок испытаний", "address": "Иркутск", "diagnostic_type": "Приемка",
        "date": "2024-03-03", "coordinates": "52.27,104.31", "type": "КК", "diameter": "110",
        "material": "Пластик", "distance": "20.5", "areaid": "1",
        "well_0": "А", "flow_0": "по течению", "slope_0": "отличный", "span_0": "10", "well2_0": "Б",
        "well_2": "Б", "flow_2": "против течения", "slope_2": "в норме", "span_2": "10.5", "well2_2": "В",
        "problem_0": "Трещина, скол; стык", "problemDistance_0": "3.2",
        "problem_3": "Смещение", "problemDistance_3": "20.5",
        "problem_5": "", "problemDistance_5": "",
    }


@pytest.fixture
def postgres(monkeypatch):
    import os

    dsn = os.environ.get("PLI_TEST_DSN")
    if not dsn:
        pytest.skip("Set PLI_TEST_DSN to run PostgreSQL integration tests.")
    schema = "pli_test_" + uuid4().hex
    owner = psycopg2.connect(dsn)
    owner.autocommit = True
    with owner.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    schema_dsn = make_dsn(dsn, options=f"-c search_path={schema}")

    @contextmanager
    def connect():
        connection = psycopg2.connect(schema_dsn)
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setattr(createdb, "migration_connection", connect)
    try:
        yield schema_dsn, connect
    finally:
        with owner.cursor() as cursor:
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        owner.close()
