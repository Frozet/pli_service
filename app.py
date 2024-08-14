from flask import Flask, render_template, redirect, url_for, request, session
import sqlite3
import hashlib
import base64
from datetime import datetime
from db_requests import get_db_connection, get_diagnostic_detail, get_diagnostics, format_diagnostic_data, get_diagnostics_coordinates
from graph_generate import generate_diagnostic_plot

app = Flask(__name__)
with open('static/secret_key.txt', 'r') as f:
        key = f.readline()
app.secret_key = key  # тут секретный ключ
# секретный ключ для хеширования данных сессии при авторизации

def get_yandex_api_key():
    with open('static/yandex_api_key.txt', 'r') as f:
        yandex_api_key = f.readline()
    return yandex_api_key

# Главная страница
@app.route('/index')
def index():
    yandex_api_key = get_yandex_api_key()
    return render_template('index.html', yandex_api_key=yandex_api_key)

# Страница формы логина в админ панель
@app.route('/adm_login', methods=['GET', 'POST'])
def user_login():
    error = None  # обнуляем переменную ошибок
    if request.method == 'POST':
        username = request.form['username']  # обрабатываем запрос с нашей формы который имеет атрибут name="username"
        password = request.form['password']  # обрабатываем запрос с нашей формы который имеет атрибут name="password"
        hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()  # шифруем пароль в sha-256

        # устанавливаем соединение с БД
        conn = get_db_connection()
        # создаем запрос для поиска пользователя по username,
        # если такой пользователь существует, то получаем все данные id, password
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        # закрываем подключение БД
        conn.close()

        # теперь проверяем если данные сходятся формы с данными БД
        if user and user['password'] == hashed_password:
            # в случае успеха создаем сессию в которую записываем id пользователя
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            # и делаем переадресацию пользователя на главную страницу
            return redirect(url_for('index'))

        else:
            error = 'Неправильное имя пользователя или пароль'

    return render_template('login_adm.html', error=error)

@app.route('/logout')
def logout():
    # Удаление данных пользователя из сессии
    session.clear()
    # Перенаправление на главную страницу или страницу входа
    return redirect(url_for('index'))

# Страница админ панели
@app.route('/admin_panel')
def admin_panel():
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    user_name = session['username']
    role = session['role']
    if role == 'Admin':
        return render_template('admin_panel.html', role=role)
    else:
        return render_template('user_panel.html', user_name=user_name, role=role)

# Страница аккаунта обычного пользователя
@app.route('/user_panel.html')
def user_panel():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    user_name = session['username'] 
    role = session['role']
    return render_template('user_panel.html', user_name=user_name, role=role)

# Добавление диагностики
@app.route('/add_diagnostic/<int:diagnostic_id>', methods=['GET', 'POST'])
def add_diagnostic(diagnostic_id):
    
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    if diagnostic_id:
        edit_mode = True
        diagnostic = get_diagnostic_detail(diagnostic_id)
        user_name = session['username']
        yandex_api_key = get_yandex_api_key()
        return render_template('add_panel.html', user_name=user_name, yandex_api_key=yandex_api_key, diagnostic_id=diagnostic_id, diagnostic=diagnostic, edit_mode=edit_mode)
    else:
        edit_mode = False
        user_name = session['username']
        yandex_api_key = get_yandex_api_key()
        return render_template('add_panel.html', user_name=user_name, yandex_api_key=yandex_api_key, diagnostic_id=0, edit_mode=edit_mode)

@app.route('/edit_form/<int:diagnostic_id>', methods=['GET', 'POST'])
def edit_diagnostic(diagnostic_id):
    if request.method == 'POST':
        # Get form data
        diagnostic_name = request.form['name']
        diagnostic_type = request.form['type']
        diagnostic_coordinates = request.form['coordinates']
        diagnostic_kind = request.form['diagnostic_type']
        diagnostic_date = request.form['date']
        diagnostic_diameter = request.form['diameter']
        diagnostic_material = request.form['material']
        diagnostic_distance = request.form['distance']
        diagnostic_author = request.form['author']
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

        # Update the diagnostic in the database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE diagnostics SET address = ?, short_title = ?, diagnostic_type = ?, date = ?, coordinates = ?, type = ?, diameter = ?, material = ?, distance = ?, count_of_well = ?, distance_between_wells = ?, slope_between_wells = ?, flow = ?, author = ?, problems = ?, problems_distances = ?, timestampdata = ?
            WHERE id = ?
        """, (
            diagnostic_name, diagnostic_name, diagnostic_kind, diagnostic_date, 
            diagnostic_coordinates, diagnostic_type, diagnostic_diameter, 
            diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans,
            diagnostic_slopes, diagnostic_flows, diagnostic_author,
            diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata, diagnostic_id
            ))
        conn.commit()
        conn.close()

        # Redirect to the diagnostic details page
    return render_template('edit_form.html')
    
# Страница успешного добавления диагностики
@app.route('/submit_form', methods=['GET', 'POST'])
def submit_diagnostic():
    error = None  # обнуляем переменную ошибок
    if request.method == 'POST':
        
        diagnostic_name = request.form['name']
        diagnostic_type = request.form['type']
        diagnostic_coordinates = request.form['coordinates']
        diagnostic_kind = request.form['diagnostic_type']
        diagnostic_date = request.form['date']
        diagnostic_diameter = request.form['diameter']
        diagnostic_material = request.form['material']
        diagnostic_distance = request.form['distance']
        diagnostic_author = request.form['author']
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

        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()

        # Запрос на вставку данных
        insert_query = """
        INSERT INTO diagnostics (
            address, short_title, diagnostic_type, date, coordinates, type, diameter, material, distance, 
            count_of_well, distance_between_wells, slope_between_wells, flow, 
            author, problems, problems_distances, timestampdata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Выполнение запроса
        cursor.execute(insert_query, (
            diagnostic_name, diagnostic_name, diagnostic_kind, diagnostic_date, 
            diagnostic_coordinates, diagnostic_type, diagnostic_diameter, 
            diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans,
            diagnostic_slopes, diagnostic_flows, diagnostic_author,
            diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata
        ))

        # Фиксация изменений и закрытие соединения
        conn.commit()
        conn.close()

        

    return render_template('submit_form.html', error=error)

@app.route('/view_diagnostics')
def view_diagnostics():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    diagnostics = get_diagnostics()

    return render_template('view_page.html', diagnostics=diagnostics)

@app.route('/diagnostic_page/<int:diagnostic_id>')
def diagnostic_page(diagnostic_id):
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    diagnostic = get_diagnostic_detail(diagnostic_id)
    problem_details, format_date, wells_details = format_diagnostic_data(diagnostic)
    plot_buf = generate_diagnostic_plot(diagnostic)
    
    return render_template('diagnostic_page.html', diagnostic=diagnostic, problem_details=problem_details, format_date=format_date, wells_details=wells_details, plot_image=base64.b64encode(plot_buf.getvalue()).decode('utf-8'))

@app.route('/map')
def map_page():
     if 'user_id' not in session:
        return redirect(url_for('user_login'))
     diagnostics = get_diagnostics_coordinates()
     diagnostics_list = [dict(row) for row in diagnostics]
     yandex_api_key = get_yandex_api_key()
     return render_template('map_page.html', diagnostics=diagnostics_list, yandex_api_key=yandex_api_key)


if __name__ == '__main__':
    app.run(debug=True)