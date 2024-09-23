from psycopg2.extras import RealDictCursor
from datetime import datetime
from flask import session
from db_requests import get_db_connection

# Получение данных для идентификации
def get_user_data(username):
    # устанавливаем соединение с БД
        conn = get_db_connection()
        c = conn.cursor(cursor_factory=RealDictCursor)  # используем RealDictCursor
        # создаем запрос для поиска пользователя по username,
        # если такой пользователь существует, то получаем все данные id, password
        c.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = c.fetchone()
        # закрываем подключение БД
        conn.close()
        return user

# Получение пароля из бд
def get_user_password(user_id):
    # Проверяем текущий пароль
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute('SELECT password FROM users WHERE id = %s', (user_id,))
    stored_password = c.fetchone()['password']
    return stored_password

# Изменение пароля
def update_user_password(hashed_new_password, user_id):
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_new_password, user_id))
    conn.commit()
    conn.close()
    return 'Пароль успешно изменен.'

# Получение данных всех пользователей
def get_users():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Получение поля area_name по внешнему ключу и указание стандартного значения
    cur.execute('''
                SELECT users.id, users.username, users.full_name, users.role, users.timestampdata,
                    COALESCE(areas.name, 'Все участки') AS area_name
                FROM users
                LEFT JOIN areas ON users.areaid = areas.id
                ORDER BY id ASC
    ''')
    users = cur.fetchall()
    conn.close()
    return users

# Получение данных пользователя
def get_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT users.id, users.username, users.full_name, users.role, users.timestampdata,
                    COALESCE(areas.name, 'Все участки') AS area_name
                FROM users
                LEFT JOIN areas ON users.areaid = areas.id
                WHERE users.id = %s
    ''', (user_id,))
    user = cur.fetchone()
    conn.close()
    return user

# Редактирование данных пользователя
def update_user(user_id, username, full_name, role, areaid=None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    user_timestampdata = datetime.now()
    cur.execute("""
        UPDATE users SET username = %s, full_name = %s, role = %s, areaid = %s, timestampdata = %s
        WHERE id = %s
    """, (username, full_name, role, areaid, user_timestampdata, user_id))
    
    conn.commit()
    conn.close()
    return None

# Удаление пользователя
def delete_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()
    return None
