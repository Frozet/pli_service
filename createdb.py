import os
import psycopg2
from psycopg2 import sql
from createuser import create_user

# Подключение к базе данных PostgreSQL
conn = psycopg2.connect(
    host=os.getenv('POSTGRES_HOST'),
    database=os.getenv('POSTGRES_DB'),
    user=os.getenv('POSTGRES_USER'),
    password=os.getenv('POSTGRES_PASSWORD')
)

# Создание курсора
c = conn.cursor()

# Создание таблицы Areas
c.execute('''
    CREATE TABLE IF NOT EXISTS areas (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255),
        timestampdata TIMESTAMP
    )
''')

# Создание таблицы Diagnostics
c.execute('''
    CREATE TABLE IF NOT EXISTS diagnostics (
        id SERIAL PRIMARY KEY,
        address VARCHAR(255),
        short_title VARCHAR(255),
        diagnostic_type VARCHAR(255),
        date VARCHAR(255),
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
        photo_path VARCHAR(512),
        slope_graph_path VARCHAR(512)
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
        timestampdata TIMESTAMP,
        areaid INTEGER REFERENCES areas (id)
    )
''')

# Завершение работы с курсором и закрытие соединения с базой данных
conn.commit()
c.close()
conn.close()

create_user('admin', 'admin', 'Admin Admin', 'Admin')