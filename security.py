import hashlib
import hmac
import secrets
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import abort, current_app, g, redirect, request, session, url_for

from diagnostic_data import FormError

ROLES = ("Admin", "User", "Viewer")
EDITORS = ("Admin", "User")
password_hasher = PasswordHasher()


def verify_password(stored, password):
    if not password or len(password) > 256:
        return False
    if not stored:
        stored = current_app.extensions["dummy_password"]
        verify_password(stored, password)
        return False
    if len(stored) == 64 and all(char in "0123456789abcdef" for char in stored):
        return hmac.compare_digest(stored, hashlib.sha256(password.encode()).hexdigest())
    try:
        return password_hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_password(password):
    if not 12 <= len(password) <= 256 or password.isspace():
        raise FormError("Пароль должен содержать от 12 до 256 символов.")
    return password_hasher.hash(password)


def session_signature(user):
    fields = (user["id"], user["password"], user["role"], user["areaid"], user["timestampdata"])
    payload = repr(fields).encode()
    key = current_app.secret_key
    return hmac.digest(key.encode() if isinstance(key, str) else key, payload, "sha256").hex()


def load_user():
    g.user = None
    if "user_id" not in session:
        return
    db = current_app.extensions["db"]
    with db.transaction() as cursor:
        cursor.execute("SELECT * FROM users WHERE id = %s", (session["user_id"],))
        user = cursor.fetchone()
    if (user and user["role"] in ROLES
            and hmac.compare_digest(session.get("auth", ""), session_signature(user))):
        g.user = user
    else:
        session.clear()


def start_session(user):
    session.clear()
    session.permanent = True
    session.update(user_id=user["id"], auth=session_signature(user))


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def check_csrf():
    expected = session.get("csrf_token", "")
    submitted = request.form.get("csrf_token", "")
    if not expected or not submitted.isascii() or not hmac.compare_digest(expected, submitted):
        abort(400, description="Срок действия формы истёк. Откройте страницу заново.")


def access(*roles):
    def decorate(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not g.user:
                if request.method in ("GET", "HEAD"):
                    return redirect(url_for("auth.user_login"))
                abort(401)
            if roles and g.user["role"] not in roles:
                abort(403)
            if request.method == "POST":
                check_csrf()
            return view(*args, **kwargs)
        return wrapper
    return decorate
