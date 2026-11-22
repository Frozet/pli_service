"""Apply ordered migrations explicitly, to an empty database or a restored copy."""

import argparse
import hashlib
from pathlib import Path

from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from database import migration_connection, setting
from db_requests import save_children
from diagnostic_data import (
    FLOWS,
    MAX_DEFECTS,
    MAX_SPANS,
    SLOPES,
    FormError,
    coordinate_pair,
    legacy_defects,
    legacy_spans,
    parse_date,
)

MIGRATIONS = Path(__file__).with_name("migrations")
LEGACY_IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
}


def legacy_attachments(row):
    for column, kind in (("photo_path", "photo"), ("slope_graph_path", "slope")):
        for path in (row[column] or "").split(","):
            if not path:
                continue
            prefix, separator, name = path.strip().partition("/")
            suffix = Path(name).suffix.lower()
            media_type = (
                LEGACY_IMAGE_TYPES.get(suffix) if kind == "photo"
                else "application/pdf" if suffix == ".pdf" else None
            )
            if (separator and prefix == "uploads" and media_type and name not in (".", "..")
                    and "/" not in name and "\\" not in name):
                yield kind, name, media_type
            else:
                yield kind, None, None


def convert_legacy(cursor):
    last_id = -2_147_483_649
    while True:
        cursor.execute("SELECT * FROM diagnostics WHERE id > %s ORDER BY id LIMIT 500", (last_id,))
        rows = cursor.fetchall()
        if not rows:
            break
        for row in rows:
            convert_diagnostic(cursor, row)
        last_id = rows[-1]["id"]


def convert_diagnostic(cursor, row):
    issues = {}
    day = latitude = longitude = None
    spans = defects = ()
    try:
        day = parse_date(row["date"])
    except FormError as error:
        issues["date"] = str(error)
    try:
        latitude, longitude = coordinate_pair(row["coordinates"])
    except FormError as error:
        issues["coordinates"] = str(error)
    try:
        spans = legacy_spans(row)
        if (not spans or len(spans) > MAX_SPANS or sum(span.length for span in spans) != row["distance"]
                or any(span.flow not in FLOWS or span.slope not in SLOPES
                       or not span.first_well or not span.last_well for span in spans)):
            issues["spans"] = "Проверьте длины, колодцы, направления и уклоны старых пролётов."
    except FormError as error:
        issues["spans"] = str(error)
    try:
        defects = legacy_defects(row)
        if (len(defects) > MAX_DEFECTS or any(row["distance"] is None or defect.distance > row["distance"]
                                              for defect in defects)):
            issues["defects"] = "Проверьте количество и расстояния старых дефектов."
    except FormError as error:
        issues["defects"] = str(error)

    cursor.execute("UPDATE diagnostics SET survey_date=%s, latitude=%s, longitude=%s WHERE id=%s",
                   (day, latitude, longitude, row["id"]))
    save_children(cursor, row["id"], spans, defects)
    for kind, name, media_type in legacy_attachments(row):
        if name is None:
            issues["attachments"] = "Часть старых файлов имеет неподдерживаемый путь или тип."
            continue
        cursor.execute("""
            INSERT INTO diagnostic_attachments (diagnostic_id, kind, stored_name, media_type, legacy)
            VALUES (%s, %s, %s, %s, TRUE) ON CONFLICT DO NOTHING
        """, (row["id"], kind, name, media_type))
    if issues:
        cursor.executemany("""
            INSERT INTO diagnostic_migration_issues (diagnostic_id, field, reason) VALUES (%s, %s, %s)
        """, [(row["id"], field, reason) for field, reason in issues.items()])


def grant_app_role(cursor, role, password):
    if not role or not password:
        raise ValueError("Set PLI_APP_USER and PLI_APP_PASSWORD_FILE.")
    cursor.execute("SELECT current_user AS name")
    if cursor.fetchone()["name"] == role:
        raise ValueError("Use distinct database roles for migrations and the application.")
    cursor.execute("""
        SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls
               OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member = pg_roles.oid) AS privileged
        FROM pg_roles WHERE rolname = %s
    """, (role,))
    existing = cursor.fetchone()
    if existing and existing["privileged"]:
        raise ValueError("The application database role already has elevated privileges.")
    command = sql.SQL("ALTER ROLE" if existing else "CREATE ROLE")
    identifier = sql.Identifier(role)
    cursor.execute(command + sql.SQL(" {} LOGIN PASSWORD %s").format(identifier), (password,))
    cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(identifier))
    tables = sql.SQL(", ").join(map(sql.Identifier, (
        "areas", "users", "diagnostics", "diagnostic_spans", "diagnostic_defects",
        "diagnostic_attachments", "diagnostic_migration_issues", "pending_file_deletions", "login_attempts",
    )))
    cursor.execute(sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}").format(tables, identifier))
    cursor.execute(sql.SQL("GRANT SELECT ON pli_schema_migrations TO {}").format(identifier))
    cursor.execute(sql.SQL("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {}").format(identifier))


def migrate(provision=False):
    with migration_connection() as connection, connection, connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(284496716)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pli_schema_migrations (
                version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("SELECT version FROM pli_schema_migrations")
        applied = {row["version"] for row in cursor.fetchall()}
        for filename in sorted(MIGRATIONS.glob("*.sql")):
            if filename.stem in applied:
                continue
            cursor.execute(filename.read_text(encoding="utf-8"))
            if filename.stem == "002_structured_diagnostics":
                convert_legacy(cursor)
                cursor.execute(
                    "UPDATE users SET password = NULL WHERE username = %s AND password = %s",
                    ("admin", hashlib.sha256(b"admin").hexdigest()),
                )
            cursor.execute("INSERT INTO pli_schema_migrations (version) VALUES (%s)", (filename.stem,))
        if provision:
            grant_app_role(cursor, setting("PLI_APP_USER"), setting("PLI_APP_PASSWORD"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provision-app-role", action="store_true")
    migrate(parser.parse_args().provision_app_role)
