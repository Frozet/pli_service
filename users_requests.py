from diagnostic_data import FormError, positive_int, required
from security import ROLES, hash_password


def account_fields(form):
    username = required(form, "username", "Логин")
    full_name = required(form, "full_name", "Полное имя")
    role = required(form, "role", "Роль")
    if role not in ROLES:
        raise FormError("Выберите допустимую роль.")
    areaid = positive_int(form.get("areaid"), "Участок") if role == "Viewer" else None
    return username, full_name, role, areaid


def get_users(cursor, user_id=None):
    query = """
        SELECT u.id, u.username, u.full_name, u.role, u.timestampdata, u.areaid,
               COALESCE(a.name, CASE WHEN u.role = 'Viewer' THEN 'Не назначен'
                                     ELSE 'Все участки' END) AS area_name
        FROM users u LEFT JOIN areas a ON a.id = u.areaid
    """
    if user_id is not None:
        cursor.execute(query + " WHERE u.id = %s", (user_id,))
        return cursor.fetchone()
    cursor.execute(query + " ORDER BY u.id")
    return cursor.fetchall()


def create_user(cursor, username, full_name, role, areaid, password):
    cursor.execute("""
        INSERT INTO users (username, full_name, role, areaid, password, timestampdata)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
    """, (username, full_name, role, areaid, hash_password(password)))
