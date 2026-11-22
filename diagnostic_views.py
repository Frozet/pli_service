from datetime import date
from io import BytesIO
from subprocess import CalledProcessError, TimeoutExpired

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_file, url_for
from psycopg2 import Error as DatabaseError
from psycopg2.errors import ForeignKeyViolation
from pypdf.errors import PdfReadError

from areas_requests import get_areas
from attachments import MAX_ATTACHMENTS_PER_KIND, add_attachments, remove_attachments, validate_uploads
from db_requests import (
    DiagnosticFilters,
    diagnostic_details,
    diagnostics_for_year,
    display_date,
    get_attachment,
    get_attachments,
    get_diagnostic,
    get_graph_data,
    list_diagnostics,
    map_diagnostics,
    save_diagnostic,
    visible_area,
)
from diagnostic_data import FLOWS, MAX_DEFECTS, MAX_SPANS, SLOPES, DiagnosticInput, FormError, positive_int
from pdf_report import generate_report, render_diagnostic_graph
from security import EDITORS, access

bp = Blueprint("diagnostics", __name__)

COLUMNS = (
    ("short_title", "Название"), ("date", "Дата"), ("diagnostic_type", "Диагностика"),
    ("type", "Тип"), ("diameter", "Диаметр"), ("material", "Материал"), ("distance", "Расстояние"),
)


@bp.get("/view_diagnostics")
@access()
def view_diagnostics():
    return diagnostics_table()


@bp.get("/admin_diagnostics")
@access("Admin")
def admin_diagnostics():
    return diagnostics_table(admin=True)


def diagnostics_table(*, admin=False):
    try:
        filters = DiagnosticFilters.from_args(request.args, admin=admin)
    except FormError as error:
        abort(400, description=str(error))

    scope = visible_area(g.user)
    with current_app.extensions["db"].transaction() as cursor:
        areas = get_areas(cursor, scope)
        diagnostics, summary = list_diagnostics(cursor, filters, scope)

    params = {
        "search_query": filters.query, "areaFilter": filters.areaid or "all",
        "start_date": filters.start_date, "end_date": filters.end_date,
        "sort_by": filters.sort_by, "order": filters.order,
    }

    def table_url(**overrides):
        return url_for(request.endpoint, **(params | overrides))

    template = "admin_diagnostics.html" if admin else "view_page.html"
    return render_template(
        template, areas=areas, diagnostics=diagnostics, filters=filters, summary=summary,
        columns=COLUMNS, table_url=table_url,
    )


def read_details(cursor, diagnostic_id):
    # The parent share lock keeps attachments and child rows from changing while read.
    diagnostic = get_diagnostic(cursor, diagnostic_id, visible_area(g.user), lock="share") or abort(404)
    return diagnostic_details(cursor, diagnostic)


@bp.get("/diagnostic_page/<int:diagnostic_id>")
@access()
def diagnostic_page(diagnostic_id):
    with current_app.extensions["db"].transaction() as cursor:
        details = read_details(cursor, diagnostic_id)
    return render_template("diagnostic_page.html", **details)


@bp.get("/diagnostic/<int:diagnostic_id>/graph.png")
@access()
def diagnostic_graph(diagnostic_id):
    with current_app.extensions["db"].transaction() as cursor:
        graph = get_graph_data(cursor, diagnostic_id, visible_area(g.user)) or abort(404)
    return send_file(BytesIO(render_diagnostic_graph(*graph)), mimetype="image/png")


@bp.get("/diagnostic/<int:diagnostic_id>/attachments/<int:attachment_id>")
@access()
def attachment_file(diagnostic_id, attachment_id):
    with current_app.extensions["db"].transaction() as cursor:
        attachment = get_attachment(cursor, diagnostic_id, attachment_id, visible_area(g.user)) or abort(404)
        try:
            data = current_app.extensions["attachments"].read(attachment)
        except (OSError, ValueError):
            current_app.logger.warning("Attachment %s is unavailable", attachment_id, exc_info=True)
            abort(404)
    return send_file(
        BytesIO(data), mimetype=attachment["media_type"], download_name=attachment["stored_name"],
        as_attachment=attachment["kind"] != "photo",
    )


@bp.get("/diagnostic/<int:diagnostic_id>/generate_pdf")
@access()
def generate_pdf(diagnostic_id):
    with current_app.extensions["db"].transaction() as cursor:
        details = read_details(cursor, diagnostic_id)
    try:
        report = generate_report(details, current_app.extensions["attachments"], date.today().strftime("%d.%m.%Y"))
    except (CalledProcessError, TimeoutExpired, OSError, PdfReadError, ValueError):
        current_app.logger.exception("Could not generate report for diagnostic %s", diagnostic_id)
        abort(503, description="Не удалось сформировать PDF. Попробуйте позже.")
    return send_file(report, as_attachment=True, download_name="diagnostic_report.pdf", mimetype="application/pdf")


@bp.get("/map")
@access()
def map_page():
    with current_app.extensions["db"].transaction() as cursor:
        diagnostics = map_diagnostics(cursor, visible_area(g.user))
    for diagnostic in diagnostics:
        diagnostic["url"] = url_for("diagnostics.diagnostic_page", diagnostic_id=diagnostic["id"])
    return render_template("map_page.html", diagnostics=diagnostics)


@bp.get("/annual_report")
@access()
def annual_report():
    try:
        year = positive_int(request.args.get("year", str(date.today().year)), "Год", 9999)
    except FormError as error:
        abort(400, description=str(error))

    with current_app.extensions["db"].transaction() as cursor:
        diagnostics = diagnostics_for_year(cursor, year, visible_area(g.user))
    for diagnostic in diagnostics:
        diagnostic["date"] = display_date(diagnostic)
        diagnostic["problems"] = diagnostic.pop("defects")
        diagnostic["count_of_well"] = diagnostic.pop("spans")
    return render_template("annual_report.html", diagnostics=diagnostics, year=year)


@bp.route("/add_diagnostic/<int:diagnostic_id>", methods=["GET", "POST"])
@bp.route("/edit_form/<int:diagnostic_id>", methods=["GET", "POST"], endpoint="legacy_edit")
@bp.post("/submit_form", defaults={"diagnostic_id": 0}, endpoint="legacy_submit")
@access(*EDITORS)
def add_diagnostic(diagnostic_id):
    if request.method == "POST":
        try:
            saved_id = save_from_form(diagnostic_id)
        except FormError as error:
            flash(str(error))
            return diagnostic_form(diagnostic_id, posted=True), 400
        except ForeignKeyViolation:
            flash("Выберите существующий участок.")
            return diagnostic_form(diagnostic_id, posted=True), 400
        except OSError:
            current_app.logger.exception("Could not write diagnostic attachments")
            flash("Не удалось сохранить вложения. Повторите попытку.")
            return diagnostic_form(diagnostic_id, posted=True), 503
        flash("Диагностика сохранена.")
        return redirect(url_for("diagnostics.diagnostic_page", diagnostic_id=saved_id), code=303)

    return diagnostic_form(diagnostic_id)


def diagnostic_form(diagnostic_id, *, posted=False):
    db = current_app.extensions["db"]
    details = {}
    with db.transaction() as cursor:
        if diagnostic_id:
            details = read_details(cursor, diagnostic_id)
        areas = get_areas(cursor, visible_area(g.user))
    row = details.get("diagnostic", {})
    coords = ""
    if row.get("latitude") is not None:
        coords = f'{row["latitude"]},{row["longitude"]}'
    values = dict(row)
    values.update(name=row.get("short_title", ""), date=row.get("survey_date") or "", coordinates=coords)
    spans = details.get("wells_details", ())
    defects = details.get("problem_details", ())
    removed = []
    if posted:
        values.update(request.form)
        spans = form_blocks(("well", "flow", "slope", "span", "well2"), MAX_SPANS)
        defects = form_blocks(("problem", "problemDistance"), MAX_DEFECTS)
        removed = request.form.getlist("remove_attachment")
    return render_template(
        "add_panel.html", **details, values=values, diagnostic_id=diagnostic_id, spans=spans, defects=defects,
        areas=areas, flows=FLOWS, slopes=SLOPES, removed=removed, max_spans=MAX_SPANS, max_defects=MAX_DEFECTS,
    )


def form_blocks(prefixes, limit):
    prefix = prefixes[0] + "_"
    ids = sorted({
        int(key.removeprefix(prefix)) for key in request.form
        if key.startswith(prefix) and key.removeprefix(prefix).isascii()
        and key.removeprefix(prefix).isdecimal() and len(key.removeprefix(prefix)) <= 6
    })[:limit]
    return [tuple(request.form.get(f"{field}_{index}", "") for field in prefixes) for index in ids]


def save_from_form(diagnostic_id):
    db = current_app.extensions["db"]
    store = current_app.extensions["attachments"]
    data = DiagnosticInput.from_form(request.form)
    uploads = validate_uploads(request.files)
    written = []
    ready_to_commit = False
    try:
        with db.transaction() as cursor:
            removed = []
            author = g.user["full_name"]
            if diagnostic_id:
                row = get_diagnostic(cursor, diagnostic_id, visible_area(g.user), lock="update") or abort(404)
                if request.form.get("version") != str(row["version"]):
                    abort(409, description="Диагностику уже изменили. Откройте её заново перед сохранением.")
                cursor.execute("""
                    SELECT 1 FROM diagnostic_migration_issues
                    WHERE diagnostic_id=%s LIMIT 1
                """, (diagnostic_id,))
                if cursor.fetchone() and request.form.get("reviewed") != "yes":
                    raise FormError("Подтвердите проверку данных предыдущей версии.")
                author = row["author"] or author
                removed = selected_removals(cursor, diagnostic_id, uploads)
            saved_id = save_diagnostic(cursor, data, author, diagnostic_id or None)
            remove_attachments(cursor, saved_id, removed)
            add_attachments(cursor, saved_id, uploads)
            store.write(uploads, written)
            ready_to_commit = True
    except Exception:
        # If commit itself failed, keep new files in case the server committed before disconnecting.
        if not ready_to_commit:
            store.discard(written)
        raise
    if removed:
        drain_deletions(db, store)
    return saved_id


def selected_removals(cursor, diagnostic_id, uploads):
    attachments = get_attachments(cursor, diagnostic_id)
    by_id = {str(attachment["id"]): attachment for attachment in attachments}
    removed_ids = set(request.form.getlist("remove_attachment"))
    if removed_ids.difference(by_id):
        raise FormError("Одно из выбранных вложений не принадлежит этой диагностике.")
    retained = [attachment for key, attachment in by_id.items() if key not in removed_ids]
    for kind in ("photo", "slope"):
        retained_count = sum(attachment["kind"] == kind for attachment in retained)
        uploaded_count = sum(upload.kind == kind for upload in uploads)
        if uploaded_count and retained_count + uploaded_count > MAX_ATTACHMENTS_PER_KIND:
            raise FormError(f"Допустимо до {MAX_ATTACHMENTS_PER_KIND} вложений каждого типа.")
    return [by_id[attachment_id] for attachment_id in removed_ids]


def drain_deletions(db, store):
    try:
        store.drain_deletions(db)
    except DatabaseError:
        current_app.logger.exception("Could not process queued attachment deletions")


@bp.post("/delete/<int:diagnostic_id>")
@access(*EDITORS)
def delete_diagnostic(diagnostic_id):
    db = current_app.extensions["db"]
    with db.transaction() as cursor:
        if not get_diagnostic(cursor, diagnostic_id, visible_area(g.user), lock="update"):
            abort(404)
        remove_attachments(cursor, diagnostic_id, get_attachments(cursor, diagnostic_id))
        cursor.execute("DELETE FROM diagnostics WHERE id = %s", (diagnostic_id,))
    drain_deletions(db, current_app.extensions["attachments"])
    flash("Диагностика удалена.")
    target = "diagnostics.admin_diagnostics" if g.user["role"] == "Admin" else "diagnostics.view_diagnostics"
    return redirect(url_for(target), code=303)
