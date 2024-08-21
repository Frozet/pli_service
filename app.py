from flask import Flask, flash, render_template, redirect, url_for, request, session
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import base64
from db_requests import get_user_data, get_user_password, update_user_password, get_diagnostic_detail, get_diagnostics, get_users, get_user, format_diagnostic_data, get_diagnostics_coordinates, delete_func, data_from_add_to_db, insert_to_db, edit_row
from graph_generate import generate_diagnostic_plot

app = Flask(__name__)
with open('static/secret_key.txt', 'r') as f:
        key = f.readline()
app.secret_key = key  # тут секретный ключ
# секретный ключ для хеширования данных сессии при авторизации

# Получение ключа от Yandex API
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

        user = get_user_data(username)

        # теперь проверяем если данные сходятся формы с данными БД
        if user and user['password'] == hashed_password:
            # в случае успеха создаем сессию в которую записываем все данные пользователя
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            session['area'] = user['area']
            # и делаем переадресацию пользователя на главную страницу
            return redirect(url_for('index'))

        else:
            error = 'Неправильное имя пользователя или пароль'

    return render_template('login_adm.html', error=error)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Проверяем, что новый пароль и подтверждение совпадают
        if new_password != confirm_password:
            flash('Новые пароли не совпадают.')
            return redirect(url_for('change_password'))

        stored_password = get_user_password(session['user_id'])

        if hashlib.sha256(current_password.encode('utf-8')).hexdigest() != stored_password:
            flash('Текущий пароль введен неверно.')
            return redirect(url_for('change_password'))

        # Обновляем пароль в базе данных
        hashed_new_password = hashlib.sha256(new_password.encode('utf-8')).hexdigest()
        update_password = update_user_password(hashed_new_password, session['user_id'])

        flash(update_password)
        return redirect(url_for('user_panel'))

    return render_template('change_password.html')

@app.route('/logout')
def logout():
    # Удаление данных пользователя из сессии
    session.clear()
    # Перенаправление на главную страницу
    return redirect(url_for('index'))

# Страница админ панели
@app.route('/admin_panel')
def admin_panel():
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        return render_template('admin_panel.html')
    else:
        return render_template('user_panel.html')

# Страница админ панели - таблица диагностик
@app.route('/admin_diagnostics', methods=['GET'])
def admin_diagnostics():
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    search_query = request.args.get('search_query', '')  # Получаем параметр search_query из строки запроса
    area_filter = request.args.get('areaFilter', 'all')
    sort_by = request.args.get('sort_by', 'date')  # Сортировка по умолчанию - по дате
    order = request.args.get('order', 'asc')  # Порядок сортировки по умолчанию - возрастание
    page = int(request.args.get('page', 1))  # Текущая страница, по умолчанию - 1
    per_page = 100  # Количество записей на странице
    start = (page - 1) * per_page
    end = start + per_page
    diagnostics, total_pages = get_diagnostics(search_query, area_filter, sort_by, order, per_page, start)

    if session['role'] == 'Admin':
        return render_template('admin_diagnostics.html', diagnostics=diagnostics, sort_by=sort_by, order=order,
                           page=page, total_pages=total_pages)
    else:
        return render_template('user_panel.html')

# Страница админ панели - таблица пользователей    
@app.route('/admin_users')
def admin_users():
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        users = get_users()
        return render_template('admin_users.html', users=users)
    else:
        return render_template('user_panel.html')

# Страница админ панели - изменение пользователя    
@app.route('/admin_edit_user/<int:user_id>')
def admin_edit_user(user_id):
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        user = get_user(user_id)
        return render_template('admin_edit_user.html', user=user)
    else:
        return render_template('user_panel.html')

# Страница аккаунта редактора или пользователя
@app.route('/user_panel.html')
def user_panel():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    return render_template('user_panel.html')

# Добавление диагностики
@app.route('/add_diagnostic/<int:diagnostic_id>', methods=['GET', 'POST'])
def add_diagnostic(diagnostic_id):
    # Добавлять диагностики возможно только редактору или админу
    if session['role'] == 'Viewer':
        return redirect(url_for('index'))

    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    with open('static/areas.json', 'r', encoding='utf-8') as f:
        areas = json.load(f)
    if diagnostic_id:
        edit_mode = True
        diagnostic = get_diagnostic_detail(diagnostic_id)
        user_name = session['username']
        yandex_api_key = get_yandex_api_key()
        return render_template('add_panel.html', user_name=user_name, yandex_api_key=yandex_api_key, diagnostic_id=diagnostic_id, diagnostic=diagnostic, areas=areas, edit_mode=edit_mode)
    else:
        edit_mode = False
        user_name = session['username']
        yandex_api_key = get_yandex_api_key()
        return render_template('add_panel.html', user_name=user_name, yandex_api_key=yandex_api_key, diagnostic_id=0, areas=areas, edit_mode=edit_mode)

@app.route('/edit_form/<int:diagnostic_id>', methods=['GET', 'POST'])
def edit_diagnostic(diagnostic_id):
    if request.method == 'POST':
        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata = data_from_add_to_db(request)
        edit_row(diagnostic_id, diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata)

        # Redirect to the diagnostic details page
    return render_template('edit_form.html')
    
# Страница успешного добавления диагностики
@app.route('/submit_form', methods=['GET', 'POST'])
def submit_diagnostic():
    error = None  # обнуляем переменную ошибок
    if request.method == 'POST':
        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata = data_from_add_to_db(request)
        insert_to_db(diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata)
        
    return render_template('submit_form.html', error=error)

@app.route('/view_diagnostics', methods=['GET'])
def view_diagnostics():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    search_query = request.args.get('search_query', '')  # Получаем параметр search_query из строки запроса
    area_filter = request.args.get('areaFilter', 'all')
    sort_by = request.args.get('sort_by', 'date')  # Сортировка по умолчанию - по дате
    order = request.args.get('order', 'asc')  # Порядок сортировки по умолчанию - возрастание
    page = int(request.args.get('page', 1))  # Текущая страница, по умолчанию - 1
    per_page = 50  # Количество записей на странице

    # Устанавливаем начальный и конечный индексы для пагинации
    start = (page - 1) * per_page
    end = start + per_page

    diagnostics, total_pages = get_diagnostics(search_query, area_filter, sort_by, order, per_page, start)

    return render_template('view_page.html', diagnostics=diagnostics, sort_by=sort_by, order=order,
                           page=page, total_pages=total_pages)

@app.route('/diagnostic_page/<int:diagnostic_id>')
def diagnostic_page(diagnostic_id):
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    diagnostic = get_diagnostic_detail(diagnostic_id)
    problem_details, format_date, wells_details = format_diagnostic_data(diagnostic)
    plot_buf = generate_diagnostic_plot(diagnostic)
    
    return render_template('diagnostic_page.html', diagnostic=diagnostic, problem_details=problem_details, format_date=format_date, wells_details=wells_details, plot_image=base64.b64encode(plot_buf.getvalue()).decode('utf-8'))

@app.route('/delete/<int:diagnostic_id>')
def delete_diagnostic(diagnostic_id):
    delete_func(diagnostic_id)
    return redirect(url_for('view_diagnostics'))

@app.route('/map')
def map_page():
     if 'user_id' not in session:
        return redirect(url_for('user_login'))
     diagnostics = get_diagnostics_coordinates()
     diagnostics_list = [dict(row) for row in diagnostics]
     yandex_api_key = get_yandex_api_key()
     with open('static/areas.json', 'r', encoding='utf-8') as f:
        areas = json.load(f)
     return render_template('map_page.html', diagnostics=diagnostics_list, yandex_api_key=yandex_api_key, areas=areas)


if __name__ == '__main__':
    app.run(debug=True)