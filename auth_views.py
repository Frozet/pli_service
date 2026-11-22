import hashlib

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from diagnostic_data import FormError
from security import access, check_csrf, hash_password, password_hasher, start_session, verify_password

bp = Blueprint("auth", __name__)


@bp.route("/adm_login", methods=["GET", "POST"])
def user_login():
    if request.method == "GET":
        return render_template("login_adm.html")
    check_csrf()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    db = current_app.extensions["db"]
    client_key = hashlib.sha256((request.remote_addr or "unknown").encode()).hexdigest()
    with db.transaction() as cursor:
        cursor.execute("""
            INSERT INTO login_attempts (client_key, attempts, expires_at)
            VALUES (%s, 1, CURRENT_TIMESTAMP + INTERVAL '15 minutes')
            ON CONFLICT (client_key) DO UPDATE SET
                attempts = CASE WHEN login_attempts.expires_at <= CURRENT_TIMESTAMP THEN 1
                                ELSE login_attempts.attempts + 1 END,
                expires_at = CASE WHEN login_attempts.expires_at <= CURRENT_TIMESTAMP THEN EXCLUDED.expires_at
                                  ELSE login_attempts.expires_at END
            WHERE login_attempts.expires_at <= CURRENT_TIMESTAMP OR login_attempts.attempts < 15
            RETURNING attempts
        """, (client_key,))
        allowed = cursor.fetchone()
        user = None
        if allowed and 1 <= len(username) <= 255 and "\0" not in username:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
    if not allowed:
        return render_template("login_adm.html", error="Слишком много попыток. Повторите через 15 минут."), 429, {
            "Retry-After": "900",
        }
    stored = user["password"] if user else None
    if not verify_password(stored, password):
        return render_template("login_adm.html", error="Неправильное имя пользователя или пароль."), 401

    if not stored.startswith("$argon2") or password_hasher.check_needs_rehash(stored):
        with db.transaction() as cursor:
            cursor.execute("""
                UPDATE users SET password = %s, timestampdata = CURRENT_TIMESTAMP
                WHERE id = %s AND password = %s RETURNING *
            """, (password_hasher.hash(password), user["id"], stored))
            user = cursor.fetchone()
        if not user:
            return render_template("login_adm.html", error="Данные учётной записи изменились. Войдите снова."), 401
    start_session(user)
    return redirect(url_for("index"), code=303)


@bp.route("/change_password", methods=["GET", "POST"])
@access()
def change_password():
    if request.method == "GET":
        return render_template("change_password.html")
    password = request.form.get("new_password", "")
    try:
        if password != request.form.get("confirm_password"):
            raise FormError("Новые пароли не совпадают.")
        if not verify_password(g.user["password"], request.form.get("current_password", "")):
            raise FormError("Текущий пароль введён неверно.")
        updated = hash_password(password)
    except FormError as error:
        flash(str(error))
        return render_template("change_password.html"), 400

    with current_app.extensions["db"].transaction() as cursor:
        cursor.execute("""
            UPDATE users SET password = %s, timestampdata = CURRENT_TIMESTAMP
            WHERE id = %s AND password = %s RETURNING *
        """, (updated, g.user["id"], g.user["password"]))
        user = cursor.fetchone()
    if user:
        start_session(user)
        flash("Пароль успешно изменён.")
    return redirect(url_for("admin.admin_panel"), code=303)


@bp.post("/logout")
@access()
def logout():
    session.clear()
    return redirect(url_for("index"), code=303)


@bp.get("/user_panel.html")
@access()
def user_panel():
    return render_template("user_panel.html")
