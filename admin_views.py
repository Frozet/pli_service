from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from psycopg2.errors import ForeignKeyViolation, UniqueViolation

from areas_requests import get_area, get_areas
from diagnostic_data import FormError, required
from security import access
from users_requests import account_fields, create_user, get_users

bp = Blueprint("admin", __name__)


@bp.get("/admin_panel")
@access()
def admin_panel():
    if g.user["role"] != "Admin":
        return redirect(url_for("auth.user_panel"))
    return render_template("admin_panel.html")


@bp.get("/admin_users")
@access("Admin")
def admin_users():
    with current_app.extensions["db"].transaction() as cursor:
        users = get_users(cursor)
    return render_template("admin_users.html", users=users)


@bp.get("/admin_edit_user/<int:user_id>")
@access("Admin")
def admin_edit_user(user_id):
    with current_app.extensions["db"].transaction() as cursor:
        user = get_users(cursor, user_id) or abort(404)
    return render_template("admin_edit_user.html", user=user)


@bp.route("/admin_add_user", methods=["GET", "POST"])
@bp.route("/admin_edit_user_form/<int:user_id>", methods=["GET", "POST"])
@access("Admin")
def user_form(user_id=None):
    db = current_app.extensions["db"]
    user = None
    with db.transaction() as cursor:
        if user_id is not None:
            user = get_users(cursor, user_id) or abort(404)
        areas = get_areas(cursor)
    if request.method == "GET":
        return render_template("admin_user_form.html", user=user, areas=areas, values=user or {})

    status = 400
    try:
        username, full_name, role, areaid = account_fields(request.form)
        if user_id == g.user["id"] and role != "Admin":
            raise FormError("Вы не можете изменить собственную роль администратора.")
        with db.transaction() as cursor:
            if user_id is None:
                create_user(cursor, username, full_name, role, areaid, request.form.get("password", ""))
            else:
                cursor.execute("""
                    UPDATE users SET username=%s, full_name=%s, role=%s, areaid=%s,
                        timestampdata=CURRENT_TIMESTAMP WHERE id=%s
                """, (username, full_name, role, areaid, user_id))
                if not cursor.rowcount:
                    abort(404)
    except FormError as error:
        flash(str(error))
    except ForeignKeyViolation:
        flash("Выберите существующий участок.")
    except UniqueViolation:
        flash("Пользователь с таким логином уже существует.")
        status = 409
    else:
        endpoint = "admin.admin_edit_user" if user_id is not None else "admin.admin_users"
        params = {"user_id": user_id} if user_id is not None else {}
        return redirect(url_for(endpoint, **params), code=303)
    values = dict(request.form)
    values["areaid"] = request.form.get("areaid", type=int)
    return render_template("admin_user_form.html", user=user, areas=areas, values=values), status


@bp.post("/admin_delete_user/<int:user_id>")
@access("Admin")
def admin_delete_user(user_id):
    if user_id == g.user["id"]:
        flash("Вы не можете удалить собственную учётную запись.")
        return redirect(url_for("admin.admin_edit_user", user_id=user_id), code=303)
    with current_app.extensions["db"].transaction() as cursor:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if not cursor.rowcount:
            abort(404)
    return redirect(url_for("admin.admin_users"), code=303)


@bp.get("/admin_areas")
@access("Admin")
def admin_areas():
    with current_app.extensions["db"].transaction() as cursor:
        areas = get_areas(cursor)
    return render_template("admin_areas.html", areas=areas)


@bp.get("/admin_edit_area/<int:area_id>")
@access("Admin")
def admin_edit_area(area_id):
    with current_app.extensions["db"].transaction() as cursor:
        area = get_area(cursor, area_id) or abort(404)
    return render_template("admin_edit_area.html", area=area)


@bp.route("/admin_add_area", methods=["GET", "POST"])
@bp.route("/admin_edit_area_form/<int:area_id>", methods=["GET", "POST"])
@access("Admin")
def area_form(area_id=None):
    db = current_app.extensions["db"]
    area = None
    if area_id is not None:
        with db.transaction() as cursor:
            area = get_area(cursor, area_id) or abort(404)
    template = "admin_edit_area_form.html" if area else "admin_add_area.html"
    if request.method == "GET":
        return render_template(template, area=area)
    try:
        name = required(request.form, "name", "Название участка")
    except FormError as error:
        flash(str(error))
        return render_template(template, area=area), 400
    with db.transaction() as cursor:
        if area_id is None:
            cursor.execute("INSERT INTO areas (name, timestampdata) VALUES (%s, CURRENT_TIMESTAMP)", (name,))
        else:
            cursor.execute("UPDATE areas SET name=%s, timestampdata=CURRENT_TIMESTAMP WHERE id=%s", (name, area_id))
            if not cursor.rowcount:
                abort(404)
    return redirect(url_for("admin.admin_areas"), code=303)


@bp.post("/admin_delete_area/<int:area_id>")
@access("Admin")
def admin_delete_area(area_id):
    try:
        with current_app.extensions["db"].transaction() as cursor:
            cursor.execute("DELETE FROM areas WHERE id = %s", (area_id,))
            if not cursor.rowcount:
                abort(404)
    except ForeignKeyViolation:
        flash("Участок используется в карточках диагностик или учётных записях.")
        return redirect(url_for("admin.admin_edit_area", area_id=area_id), code=303)
    return redirect(url_for("admin.admin_areas"), code=303)
