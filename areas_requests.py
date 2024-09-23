import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from flask import session
from db_requests import get_db_connection

# Получение всех участков
def get_areas():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM areas ORDER BY id ASC')
    areas = cur.fetchall()
    conn.close()
    return areas

# Получение участка по id
def get_area(area_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM areas WHERE id = %s', (area_id,))
    area = cur.fetchone()
    conn.close()
    return area

# Добавление участка
def add_area(name):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    area_timestampdata = datetime.now()
    cur.execute('INSERT INTO areas (name, timestampdata) VALUES (%s, %s)', (name, area_timestampdata))
    conn.commit()
    conn.close()
    return None

# Редактирование участка
def update_area(area_id, name):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    area_timestampdata = datetime.now()
    cur.execute("""
        UPDATE areas SET name = %s, timestampdata = %s
        WHERE id = %s
    """, (name, area_timestampdata, area_id))
    
    conn.commit()
    conn.close()
    return None

# Удаление участка
def delete_area(area_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("DELETE FROM areas WHERE id = %s", (area_id,))
    conn.commit()
    conn.close()
    return None
