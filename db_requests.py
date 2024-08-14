import sqlite3

# Подключение к бд
def get_db_connection():
    conn = sqlite3.connect('database.db') # Позволяет извлекать данные как словари
    conn.row_factory = sqlite3.Row
    return conn

# Получение данных всех диагностик из бд
def get_diagnostics():
    conn = get_db_connection() 
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diagnostics ORDER BY timestampdata DESC")
    diagnostics = cursor.fetchall()
    conn.close()
    return diagnostics

# Получение полных данных конкретной диагностики из бд
def get_diagnostic_detail(diagnostic_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diagnostics WHERE id = ?", (diagnostic_id,))
    diagnostic = cursor.fetchone()
    conn.close()
    return diagnostic

# Получение данных для расположения иконок на карте
def get_diagnostics_coordinates():
    conn = get_db_connection()
    cur = conn.cursor()
    # Получите все необходимые данные, включая название диагностики, id, и координаты
    cur.execute('SELECT id, short_title, diagnostic_type, coordinates FROM diagnostics')
    diagnostics = cur.fetchall()
    return diagnostics

# Форматирование данных для страницы с деталями инспекции
def format_diagnostic_data(diagnostic):
     # Подготовка проблем и расстояний
    problems = diagnostic['problems'].split(',')
    distances = diagnostic['problems_distances'].split(',')
    problem_details = list(zip(problems, distances))  # Создание списка кортежей (проблема, расстояние)
    # Подготовка даты
    date_of_diagnostic = diagnostic['date'].split('-')
    format_date = date_of_diagnostic[2] + '.' + date_of_diagnostic[1] + '.' +  date_of_diagnostic[0] # Форматирование в удобный формат
    # Подготовка информации о пролетах
    flows = diagnostic['flow'].split(',')
    wells = diagnostic['count_of_well'].split(',')
    wells_firsts = [i for i in wells[::2]]
    wells_seconds = [i for i in wells[1::2]]
    distances_between_wells = diagnostic['distance_between_wells'].split(',')
    slope_between_wells = diagnostic['slope_between_wells'].split(',')
    wells_details = list(zip(wells_firsts, flows, slope_between_wells, distances_between_wells, wells_seconds)) # Создание списка кортежей

    return problem_details, format_date, wells_details