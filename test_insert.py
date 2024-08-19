from db_requests import get_db_connection
import random
from datetime import datetime


# Этот скрипт служит для тестирования системы, вставляет 70 новых строк в базу данных
conn = get_db_connection()
cursor = conn.cursor()

for i in range(70):
    diagnostic_name = 'Тестовая ' + str(i)
    diagnostic_address = 'Тестовая, ' + str(i)
    diagnostic_kind = 'Без повреждений'
    diagnostic_date = '2024-08-19'
    diagnostic_coordinates = str(52 + random.random()) + ',' + str(104 + random.random())
    diagnostic_type = 'КК'
    diagnostic_diameter = 100
    diagnostic_material = 'Корсис'
    diagnostic_distance = random.randint(2, 100)
    diagnostic_wells = '1, 2'
    diagnostic_spans = diagnostic_distance
    diagnostic_slopes = '5'
    diagnostic_flows = 'против течения'
    diagnostic_author = 'Автор А.'
    diagnostic_problems = 'Проблема ' + str(i)
    diagnostic_problem_distances = '1'
    diagnostic_timestampdata = datetime.now()
    diagnostic_area = 'ff'
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