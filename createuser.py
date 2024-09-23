import os
from datetime import datetime
import psycopg2
import hashlib

def create_user(username, password, full_name, role, areaid=None):
    # Хеширование пароля
    hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()

    conn = psycopg2.connect(
        host=os.getenv('POSTGRES_HOST'),
        database=os.getenv('POSTGRES_DB'),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD')
    )

    user_timestampdata = datetime.now()
    # Создание курсора
    c = conn.cursor()

    # Добавление нового пользователя
    c.execute(
        'INSERT INTO users (username, password, full_name, role, areaid, timestampdata) VALUES (%s, %s, %s, %s, %s, %s)', 
        (username, hashed_password, full_name, role, areaid, user_timestampdata)
    )
    # Сохранение изменений и закрытие соединения с базой данных
    conn.commit()
    conn.close()

# Впишите нужные логин, пароль, полное имя, роль(Admin, User или Viewer) и id участка(для Viewer)
# create_user('testuser', 'testuser', 'Тестов Тест Тестович', 'Viewer', '1')