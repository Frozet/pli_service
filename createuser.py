import psycopg2
import hashlib

def create_user(username, password, full_name, role, area):
    # Хеширование пароля
    hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()

    conn = psycopg2.connect(
        host="localhost",
        database="pli_service",
        user="postgres",
        password="postgres"
    )

    # Создание курсора
    c = conn.cursor()

    # Добавление нового пользователя
    c.execute(
        'INSERT INTO users (username, password, full_name, role, area) VALUES (%s, %s, %s, %s, %s)', 
        (username, hashed_password, full_name, role, area)
    )
    # Сохранение изменений и закрытие соединения с базой данных
    conn.commit()
    conn.close()

# Впишите нужные логин, пароль, полное имя, роль(Admin, User или Viewer) и тэг участка
create_user('testuser', 'testuser', 'Тестов Тест Тестович', 'Viewer', 'ct')