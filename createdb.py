import sqlite3

# Создание или подключение к базе данных
conn = sqlite3.connect('database.db')

# Создание курсора
c = conn.cursor()

# Создание таблицы Diagnostics
c.execute('''CREATE TABLE IF NOT EXISTS diagnostics (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             address TEXT,
             short_title TEXT,
             date DATE,
             coordinates TEXT,
             type TEXT,
             diameter INTEGER,
             material TEXT,
             flow TEXT,
             distance INTEGER,
             count_of_well INTEGER,
             distance_between_wells TEXT,
             slope_between_wells TEXT,
             author TEXT,
             problems TEXT,
             problems_distances TEXT,
             timestampdata DATETIME)''')

# Создание таблицы Users
c.execute('''CREATE TABLE IF NOT EXISTS users (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             username TEXT,
             password TEXT,
             role TEXT)''')

# Закрытие соединения с базой данных
conn.close()