from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from psycopg2 import sql

from diagnostic_data import MAX_DEFECTS, MAX_SPANS, Defect, FormError, Span, parse_date, positive_int

SORT_COLUMNS = {
    "short_title": "short_title", "date": "survey_date", "diagnostic_type": "diagnostic_type",
    "type": "type", "diameter": "diameter", "material": "material", "distance": "distance",
}
ORDERS = {"asc": sql.SQL("ASC"), "desc": sql.SQL("DESC")}
# A PostgreSQL INTEGER area ID cannot match this value.
NO_ASSIGNED_AREA = 2_147_483_648


@dataclass(frozen=True)
class DiagnosticFilters:
    query: str
    areaid: int | None
    sort_by: str
    order: str
    start_date: date | None
    end_date: date | None
    page: int
    page_size: int

    @classmethod
    def from_args(cls, args, *, admin=False):
        raw_area = args.get("areaFilter", "")
        areaid = positive_int(raw_area, "Участок") if raw_area not in ("", "all") else None
        sort_by = args.get("sort_by", "date")
        order = args.get("order", "asc" if admin else "desc")
        if sort_by not in SORT_COLUMNS or order not in ORDERS:
            raise FormError("Выберите допустимый столбец и направление сортировки.")
        query = args.get("search_query", "").strip()
        if len(query) > 200 or "\0" in query:
            raise FormError("Сократите поисковый запрос до 200 символов.")
        start = parse_date(args["start_date"], "Начало периода") if args.get("start_date") else None
        end = parse_date(args["end_date"], "Конец периода") if args.get("end_date") else None
        if start and end and start > end:
            raise FormError("Начало периода должно предшествовать его окончанию.")
        page = positive_int(args.get("page", "1"), "Страница", 1_000_000)
        return cls(query, areaid, sort_by, order, start, end, page, 100 if admin else 50)


def visible_area(user):
    if user["role"] == "Viewer":
        return user["areaid"] if user["areaid"] is not None else NO_ASSIGNED_AREA
    return None


def list_diagnostics(cursor, filters, scope):
    conditions, values = [], []
    for area in (scope, filters.areaid):
        if area is not None:
            conditions.append("d.areaid = %s")
            values.append(area)
    if filters.query:
        conditions.append("""(
            d.short_title ILIKE %s OR d.address ILIKE %s OR d.material ILIKE %s
            OR d.type ILIKE %s OR d.diagnostic_type ILIKE %s OR d.author ILIKE %s
            OR d.survey_date::text ILIKE %s OR d.diameter::text ILIKE %s OR d.distance::text ILIKE %s
            OR EXISTS (SELECT 1 FROM diagnostic_defects f
                       WHERE f.diagnostic_id = d.id AND f.description ILIKE %s)
            OR (d.problems ILIKE %s AND EXISTS (SELECT 1 FROM diagnostic_migration_issues i
                       WHERE i.diagnostic_id = d.id AND i.field = 'defects'))
        )""")
        literal = filters.query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        values.extend([f"%{literal}%"] * 11)
    if filters.start_date:
        conditions.append("d.survey_date >= %s")
        values.append(filters.start_date)
    if filters.end_date:
        conditions.append("d.survey_date <= %s")
        values.append(filters.end_date)

    where = sql.SQL(" AND ".join(conditions) or "TRUE")
    order = sql.SQL("{} {} NULLS LAST, id {}").format(
        sql.Identifier(SORT_COLUMNS[filters.sort_by]), ORDERS[filters.order], ORDERS[filters.order],
    )
    cursor.execute(sql.SQL("""
        WITH filtered AS NOT MATERIALIZED (
            SELECT d.id, d.short_title, d.survey_date, d.diagnostic_type, d.type, d.diameter,
                   d.material, d.distance, d.author, COALESCE(a.name, '—') AS area_name
            FROM diagnostics d LEFT JOIN areas a ON a.id = d.areaid
            WHERE {}
        ), summary AS (
            SELECT GREATEST(1, CEIL(COUNT(*)::numeric / %s)::integer) AS total_pages,
                   COALESCE(SUM(distance), 0) AS total_distance FROM filtered
        ), paging AS (
            SELECT *, LEAST(total_pages, %s) AS page FROM summary
        )
        SELECT listed.*, paging.* FROM paging LEFT JOIN LATERAL (
            SELECT * FROM filtered ORDER BY {}
            LIMIT %s OFFSET ((SELECT page FROM paging)::bigint - 1) * %s
        ) listed ON TRUE
        ORDER BY {}
    """).format(where, order, order), (*values, filters.page_size, filters.page, filters.page_size, filters.page_size))
    rows = cursor.fetchall()
    summary = rows[0]
    return [row for row in rows if row["id"] is not None], summary


def get_diagnostic(cursor, diagnostic_id, scope=None, *, lock=None):
    statement = """
        SELECT d.*, a.name AS area_name FROM diagnostics d
        LEFT JOIN areas a ON a.id = d.areaid WHERE d.id = %s
    """
    values = [diagnostic_id]
    if scope is not None:
        statement += " AND d.areaid = %s"
        values.append(scope)
    if lock == "update":
        statement += " FOR UPDATE OF d"
    elif lock == "share":
        statement += " FOR SHARE OF d"
    cursor.execute(statement, values)
    return cursor.fetchone()


def get_graph_data(cursor, diagnostic_id, scope):
    query = """
        SELECT d.type,
               ARRAY(SELECT json_build_array(s.first_well, s.flow, s.slope, s.length::text, s.last_well)
                     FROM diagnostic_spans s WHERE s.diagnostic_id=d.id ORDER BY s.position LIMIT %s) AS spans,
               ARRAY(SELECT json_build_array(f.description, f.distance::text)
                     FROM diagnostic_defects f WHERE f.diagnostic_id=d.id ORDER BY f.position LIMIT %s) AS defects
        FROM diagnostics d WHERE d.id=%s
    """
    values = [MAX_SPANS + 1, MAX_DEFECTS + 1, diagnostic_id]
    if scope is not None:
        query += " AND d.areaid=%s"
        values.append(scope)
    cursor.execute(query, values)
    row = cursor.fetchone()
    if row is None:
        return None
    spans = tuple(Span(first, flow, slope, Decimal(length), last) for first, flow, slope, length, last in row["spans"])
    defects = tuple(Defect(description, Decimal(distance)) for description, distance in row["defects"])
    return row["type"], spans, defects


def get_spans(cursor, diagnostic_id):
    cursor.execute("""
        SELECT first_well, flow, slope, length, last_well FROM diagnostic_spans
        WHERE diagnostic_id = %s ORDER BY position
    """, (diagnostic_id,))
    return tuple(Span(**row) for row in cursor.fetchall())


def get_attachments(cursor, diagnostic_id):
    cursor.execute("""
        SELECT id, kind, stored_name, media_type, legacy FROM diagnostic_attachments
        WHERE diagnostic_id = %s ORDER BY id
    """, (diagnostic_id,))
    return cursor.fetchall()


def get_attachment(cursor, diagnostic_id, attachment_id, scope):
    query = """SELECT f.* FROM diagnostic_attachments f JOIN diagnostics d ON d.id = f.diagnostic_id
               WHERE f.diagnostic_id = %s AND f.id = %s"""
    values = [diagnostic_id, attachment_id]
    if scope is not None:
        query += " AND d.areaid = %s"
        values.append(scope)
    cursor.execute(query, values)
    return cursor.fetchone()


def diagnostic_details(cursor, diagnostic):
    diagnostic_id = diagnostic["id"]
    spans = get_spans(cursor, diagnostic_id)
    cursor.execute("""
        SELECT description, distance FROM diagnostic_defects WHERE diagnostic_id = %s ORDER BY position
    """, (diagnostic_id,))
    defects = tuple(Defect(**row) for row in cursor.fetchall())
    cursor.execute("""
        SELECT field, reason FROM diagnostic_migration_issues WHERE diagnostic_id = %s ORDER BY field
    """, (diagnostic_id,))
    issues = cursor.fetchall()
    return {
        "diagnostic": diagnostic,
        "format_date": display_date(diagnostic),
        "wells_details": spans,
        "problem_details": defects,
        "attachments": get_attachments(cursor, diagnostic_id),
        "migration_issues": issues,
    }


def display_date(row):
    return row["survey_date"].strftime("%d.%m.%Y") if row["survey_date"] else row.get("date") or "—"


def save_diagnostic(cursor, data, author, diagnostic_id=None):
    values = (
        data.short_title, data.address, data.diagnostic_type, data.survey_date, data.latitude, data.longitude,
        data.pipe_type, data.diameter, data.material, data.distance, data.areaid, author,
    )
    fields = """short_title, address, diagnostic_type, survey_date, latitude, longitude,
                type, diameter, material, distance, areaid, author"""
    placeholders = ", ".join(["%s"] * len(values))
    if diagnostic_id is None:
        cursor.execute(f"INSERT INTO diagnostics ({fields}) VALUES ({placeholders}) RETURNING id", values)
        diagnostic_id = cursor.fetchone()["id"]
    else:
        cursor.execute(f"""
            UPDATE diagnostics SET ({fields}) = ({placeholders}),
                version = version + 1, updated_at = CURRENT_TIMESTAMP WHERE id = %s
        """, (*values, diagnostic_id))
        for table in ("diagnostic_spans", "diagnostic_defects"):
            cursor.execute(sql.SQL("DELETE FROM {} WHERE diagnostic_id = %s").format(sql.Identifier(table)),
                           (diagnostic_id,))
        cursor.execute("""
            DELETE FROM diagnostic_migration_issues WHERE diagnostic_id = %s
        """, (diagnostic_id,))
    save_children(cursor, diagnostic_id, data.spans, data.defects)
    return diagnostic_id


def save_children(cursor, diagnostic_id, spans, defects):
    cursor.executemany("""
        INSERT INTO diagnostic_spans (diagnostic_id, position, first_well, flow, slope, length, last_well)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, [(diagnostic_id, index, *span) for index, span in enumerate(spans)])
    cursor.executemany("""
        INSERT INTO diagnostic_defects (diagnostic_id, position, description, distance)
        VALUES (%s, %s, %s, %s)
    """, [(diagnostic_id, index, *defect) for index, defect in enumerate(defects)])


def map_diagnostics(cursor, scope):
    query = """
        SELECT id, short_title, diagnostic_type, latitude, longitude
        FROM diagnostics WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """
    if scope is not None:
        cursor.execute(query + " AND areaid = %s ORDER BY survey_date DESC NULLS LAST, id DESC LIMIT 30", (scope,))
    else:
        cursor.execute(query + " ORDER BY survey_date DESC NULLS LAST, id DESC LIMIT 30")
    return cursor.fetchall()


def diagnostics_for_year(cursor, year, scope):
    query = """
        SELECT d.survey_date, d.short_title, d.address, d.diagnostic_type, d.diameter, d.material, d.type,
            ARRAY(SELECT json_build_array(s.first_well, s.flow, s.slope, s.length::text, s.last_well)
                  FROM diagnostic_spans s WHERE s.diagnostic_id = d.id ORDER BY s.position) AS spans,
            ARRAY(SELECT json_build_array(f.description, f.distance::text)
                  FROM diagnostic_defects f WHERE f.diagnostic_id = d.id ORDER BY f.position) AS defects,
            EXISTS (SELECT 1 FROM diagnostic_migration_issues i WHERE i.diagnostic_id = d.id) AS needs_review
        FROM diagnostics d WHERE d.survey_date >= %s AND d.survey_date <= %s
    """
    params = [date(year, 1, 1), date(year, 12, 31)]
    if scope is not None:
        query += " AND d.areaid = %s"
        params.append(scope)
    cursor.execute(query + " ORDER BY d.survey_date, d.id", params)
    return cursor.fetchall()
