import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from flask import session

# Подключение к бд
def get_db_connection():
    conn = psycopg2.connect(
    host="localhost",      # Например, "localhost"
    database="pli_service", # Название вашей базы данных
    user="postgres",  # Имя пользователя PostgreSQL
    password="postgres"  # Пароль пользователя PostgreSQL
    )
    return conn

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

def get_user_password(user_id):
    # Проверяем текущий пароль
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute('SELECT password FROM users WHERE id = %s', (user_id,))
    stored_password = c.fetchone()['password']
    return stored_password

def update_user_password(hashed_new_password, user_id):
    conn = get_db_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute('UPDATE users SET password = %s WHERE id = %s', (hashed_new_password, user_id))
    conn.commit()
    conn.close()
    return 'Пароль успешно изменен.'

# Получение данных всех диагностик из бд
def get_diagnostics(search_query, sort_by, order, per_page, start):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Получаем общее количество записей для вычисления количества страниц
    if session['area'] == 'f':
        cursor.execute("SELECT COUNT(*) FROM diagnostics")
    else:
        cursor.execute("SELECT COUNT(*) FROM diagnostics WHERE area = %s", (session['area'],))
    total_items = cursor.fetchone()['count']
    total_pages = (total_items + per_page - 1) // per_page  # Округление вверх

    # Формируем SQL-запрос с использованием параметра search_query
    if session['area'] == 'f':
        if search_query:
            query = f"""
            SELECT * FROM diagnostics 
            WHERE 
                short_title ILIKE %s OR
                diagnostic_type ILIKE %s OR
                date::TEXT ILIKE %s OR
                type ILIKE %s OR
                diameter::TEXT ILIKE %s OR
                material ILIKE %s OR
                distance::TEXT ILIKE %s OR
                problems ILIKE %s OR
                author ILIKE %s
            ORDER BY {sort_by} {order.upper()}
            LIMIT {per_page} OFFSET {start}
            """
            like_query = f"%{search_query}%"
            cursor.execute(query, (like_query, like_query, like_query, like_query, like_query, like_query, like_query, like_query, like_query))
        else:
            query = f"""
                SELECT * FROM diagnostics
                ORDER BY {sort_by} {order.upper()}
                LIMIT {per_page} OFFSET {start}
            """
            cursor.execute(query)
    else:
        if search_query:
            query = f"""
            SELECT * FROM diagnostics 
            WHERE 
                short_title ILIKE %s OR
                diagnostic_type ILIKE %s OR
                date::TEXT ILIKE %s OR
                type ILIKE %s OR
                diameter::TEXT ILIKE %s OR
                material ILIKE %s OR
                distance::TEXT ILIKE %s OR
                problems ILIKE %s OR
                author ILIKE %s AND
                area = '{session['area']}'
            ORDER BY {sort_by} {order.upper()}
            LIMIT {per_page} OFFSET {start}
            """
            like_query = f"%{search_query}%"
            cursor.execute(query, (like_query, like_query, like_query, like_query, like_query, like_query, like_query, like_query, like_query))
        else:
            query = f"""
                SELECT * FROM diagnostics
                WHERE area = '{session['area']}'
                ORDER BY {sort_by} {order.upper()}
                LIMIT {per_page} OFFSET {start}
            """
            cursor.execute(query)

    diagnostics = cursor.fetchall()
    conn.close()

    return diagnostics, total_pages

# Получение полных данных конкретной диагностики из бд
def get_diagnostic_detail(diagnostic_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM diagnostics WHERE id = %s", (diagnostic_id,))
    diagnostic = cursor.fetchone()
    conn.close()
    return diagnostic

# Получение данных для расположения иконок на карте
def get_diagnostics_coordinates():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    # Получите все необходимые данные, включая название диагностики, id, и координаты
    if session['area'] == 'f':
        cur.execute('SELECT id, short_title, diagnostic_type, coordinates FROM diagnostics ORDER BY id ASC LIMIT 20')
    else:
        # Для пользователей отдельных участков будут показаны диагностики только с их участка
        query = f"""SELECT id, short_title, diagnostic_type, coordinates FROM diagnostics WHERE area = '{session['area']}' ORDER BY id ASC LIMIT 20"""
        cur.execute(query)
    diagnostics = cur.fetchall()
    conn.close()
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

def data_from_add_to_db(request):
    diagnostic_name = request.form['name']
    diagnostic_address = request.form['address']
    diagnostic_type = request.form['type']
    diagnostic_coordinates = request.form['coordinates']
    diagnostic_kind = request.form['diagnostic_type']
    diagnostic_date = request.form['date']
    diagnostic_diameter = request.form['diameter']
    diagnostic_material = request.form['material']
    diagnostic_distance = request.form['distance']
    diagnostic_author = request.form['author']
    diagnostic_area = request.form['area']
    diagnostic_timestampdata = datetime.now()
    
    # Обработка колодцев, пролета и других данных
    diagnostic_wells = []
    diagnostic_spans = []
    diagnostic_slopes = []
    diagnostic_flows = []
    diagnostic_problems = []
    diagnostic_problem_distances = []

    for key in request.form.keys():
        if key.startswith('well'):
            diagnostic_wells.append(request.form[key])
        elif key.startswith('span_'):
            diagnostic_spans.append(request.form[key])
        elif key.startswith('slope_'):
            diagnostic_slopes.append(request.form[key])
        elif key.startswith('flow_'):
            diagnostic_flows.append(request.form[key])
        elif key.startswith('problem_'):
            diagnostic_problems.append(request.form[key])
        elif key.startswith('problemDistance_'):
            diagnostic_problem_distances.append(request.form[key])

    # Преобразование списков в строки для хранения в БД
    diagnostic_wells = ','.join(diagnostic_wells)
    diagnostic_spans = ','.join(diagnostic_spans)
    diagnostic_slopes = ','.join(diagnostic_slopes)
    diagnostic_flows = ','.join(diagnostic_flows)
    diagnostic_problems = ','.join(diagnostic_problems)
    diagnostic_problem_distances = ','.join(diagnostic_problem_distances)

    return diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata

def insert_to_db(diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Запрос на вставку данных
    insert_query = """
    INSERT INTO diagnostics (
        short_title, address, diagnostic_type, date, coordinates, type, diameter, material, distance, 
        count_of_well, distance_between_wells, slope_between_wells, flow, 
        author, problems, problems_distances, timestampdata, area
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    # Выполнение запроса
    cursor.execute(insert_query, (
        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, 
        diagnostic_coordinates, diagnostic_type, diagnostic_diameter, 
        diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans,
        diagnostic_slopes, diagnostic_flows, diagnostic_author,
        diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata, diagnostic_area
    ))

    # Фиксация изменений и закрытие соединения
    conn.commit()
    conn.close()
    
    return None

def edit_row(diagnostic_id, diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata, diagnostic_area):
    # Update the diagnostic in the database
    conn = get_db_connection()
    cursor = conn.cursor()
    print('timestampdata:', diagnostic_timestampdata, 'area:', diagnostic_area)
    cursor.execute("""
        UPDATE diagnostics SET address = %s, short_title = %s, diagnostic_type = %s, date = %s, coordinates = %s, type = %s, diameter = %s, material = %s, distance = %s, count_of_well = %s, distance_between_wells = %s, slope_between_wells = %s, flow = %s, author = %s, problems = %s, problems_distances = %s, timestampdata = %s, area = %s
        WHERE id = %s
    """, (
        diagnostic_address, diagnostic_name, diagnostic_kind, diagnostic_date, 
        diagnostic_coordinates, diagnostic_type, diagnostic_diameter, 
        diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans,
        diagnostic_slopes, diagnostic_flows, diagnostic_author,
        diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata, 
        diagnostic_id
        ))
    
    conn.commit()
    conn.close()
    
    return None

def delete_func(diagnostic_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM diagnostics WHERE id = %s", (diagnostic_id,))
    conn.commit()
    conn.close()
    return None