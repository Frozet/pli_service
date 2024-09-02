import psycopg2
from psycopg2 import sql

# Подключение к базе данных PostgreSQL
conn = psycopg2.connect(
    host="localhost",      # Например, "localhost"
    database="pli_service", # Название вашей базы данных
    user="postgres",  # Имя пользователя PostgreSQL
    password="postgres"  # Пароль пользователя PostgreSQL
)

# Создание курсора
c = conn.cursor()

# Создание таблицы Areas
c.execute('''
    CREATE TABLE IF NOT EXISTS areas (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255)
    )
''')

# Создание таблицы Diagnostics
c.execute('''
    CREATE TABLE IF NOT EXISTS diagnostics (
        id SERIAL PRIMARY KEY,
        address VARCHAR(255),
        short_title VARCHAR(255),
        diagnostic_type VARCHAR(255),
        date DATE,
        coordinates TEXT,
        type VARCHAR(255),
        diameter INTEGER,
        material VARCHAR(255),
        flow TEXT,
        distance INTEGER,
        count_of_well TEXT,
        distance_between_wells TEXT,
        slope_between_wells TEXT,
        author VARCHAR(255),
        problems TEXT,
        problems_distances TEXT,
        timestampdata TIMESTAMP,
        areaid INTEGER REFERENCES areas (id),
        photo_path VARCHAR(255)
    )
''')

# Создание таблицы Users
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(255),
        password VARCHAR(255),
        full_name VARCHAR(255),
        role VARCHAR(255),
        areaid INTEGER REFERENCES areas (id)
    )
''')

# Завершение работы с курсором и закрытие соединения с базой данных
conn.commit()
c.close()
conn.close()
