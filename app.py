from datetime import datetime
import io
import os
from werkzeug.utils import secure_filename
import pdfkit
from flask import Flask, flash, render_template, redirect, url_for, request, session, send_file
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import hashlib
import base64
from db_requests import get_user_data, get_user_password, update_user_password, get_diagnostic_detail, get_diagnostic_photo_path, get_diagnostics, get_users, get_user, update_user, delete_user, get_areas, get_area, add_area, update_area, delete_area, format_diagnostic_data, get_diagnostics_coordinates, delete_func, data_from_add_to_db, insert_to_db, edit_row, distance_sum
from createuser import create_user
from graph_generate import generate_diagnostic_plot

UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
with open('static/secret_key.txt', 'r') as f:
        key = f.readline()
app.secret_key = key  # тут секретный ключ
# секретный ключ для хеширования данных сессии при авторизации
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Настройка пути к wkhtmltopdf
config = pdfkit.configuration(wkhtmltopdf='/usr/local/bin/wkhtmltopdf')  # укажите правильный путь

# Проверка разрешения файла
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Получение ключа от Yandex API
def get_yandex_api_key():
    with open('static/yandex_api_key.txt', 'r') as f:
        yandex_api_key = f.readline()
    return yandex_api_key

@app.context_processor
def inject_year():
    return {'current_year': datetime.now().year}

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
            session['areaid'] = user['areaid']
            # и делаем переадресацию пользователя на главную страницу
            return redirect(url_for('index'))

        else:
            error = 'Неправильное имя пользователя или пароль'

    return render_template('login_adm.html', error=error)

# Изменение пароля пользователя
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

# Выход из сессии
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
    area_filter = request.args.get('areaFilter', '')
    sort_by = request.args.get('sort_by', 'date')  # Сортировка по умолчанию - по дате
    order = request.args.get('order', 'asc')  # Порядок сортировки по умолчанию - возрастание
    page = int(request.args.get('page', 1))  # Текущая страница, по умолчанию - 1
    per_page = 100  # Количество записей на странице
    start = (page - 1) * per_page
    end = start + per_page
    diagnostics, total_pages = get_diagnostics(search_query, area_filter, sort_by, order, per_page, start)

    if session['role'] == 'Admin':
        areas = get_areas()
        return render_template('admin_diagnostics.html', areas=areas, diagnostics=diagnostics, sort_by=sort_by, order=order,
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

# Страница админ панели - окно пользователя    
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

# Страница админ панели - добавление пользователя
@app.route('/admin_add_user', methods=['GET', 'POST'])
def admin_add_user():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    if session['role'] == 'Admin':
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            full_name = request.form['full_name']
            role = request.form['role']
            areaid = request.form['areaid']
            if role == 'User':
                create_user(username, password, full_name, role)
            else:
                create_user(username, password, full_name, role, areaid)

            return redirect(url_for('admin_users'))
        areas=get_areas()
        return render_template('admin_add_user.html', areas=areas)
    else:
        return render_template('user_panel.html')


# Страница админ панели - изменение пользователя    
@app.route('/admin_edit_user_form/<int:user_id>', methods=['GET', 'POST'])
def admin_edit_user_form(user_id):
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        user = get_user(user_id)
        if request.method == 'POST':
            # Обновить данные пользователя на основе введенных данных
            username = request.form['username']
            full_name = request.form['full_name']
            role = request.form['role']
            areaid = request.form['areaid']
            if role == 'user':
                update_user(user_id, username, full_name, role)
            else:
                update_user(user_id, username, full_name, role, areaid)

            return redirect(url_for('admin_edit_user', user_id=user_id))
        areas=get_areas()
        return render_template('admin_edit_user_form.html', user=user, areas=areas)
    else:
        return render_template('user_panel.html')

# Страница админ панели - удаление пользователя
@app.route('/admin_delete_user/<int:user_id>')
def admin_delete_user(user_id):
    if session['role'] == 'Admin':
        delete_user(user_id)
    return redirect(url_for('admin_users'))

# Страница админ панели - таблица участков    
@app.route('/admin_areas')
def admin_areas():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        areas = get_areas()
        return render_template('admin_areas.html', areas=areas)
    else:
        return render_template('user_panel.html')

# Страница админ панели - окно участка    
@app.route('/admin_edit_area/<int:area_id>')
def admin_edit_area(area_id):
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        area = get_area(area_id)
        return render_template('admin_edit_area.html', area=area)
    else:
        return render_template('user_panel.html')
    
# Страница админ панели - добавление участка
@app.route('/admin_add_area', methods=['GET', 'POST'])
def admin_add_area():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    if session['role'] == 'Admin':
        if request.method == 'POST':
            name = request.form['name']
            add_area(name)
            return redirect(url_for('admin_areas'))
        return render_template('admin_add_area.html')
    else:
        return render_template('user_panel.html')
    
# Страница админ панели - изменение участка   
@app.route('/admin_edit_area_form/<int:area_id>', methods=['GET', 'POST'])
def admin_edit_area_form(area_id):
    # делаем доп проверку если сессия авторизации была создана
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    if session['role'] == 'Admin':
        area = get_area(area_id)
        if request.method == 'POST':
            # Обновить данные пользователя на основе введенных данных
            name = request.form['name']
            update_area(area_id, name)

            return redirect(url_for('admin_edit_area', area_id=area_id))
        return render_template('admin_edit_area_form.html', area=area)
    else:
        return render_template('user_panel.html')

# Страница админ панели - удаление участка
@app.route('/admin_delete_area/<int:area_id>')
def admin_delete_area(area_id):
    if session['role'] == 'Admin':
        delete_area(area_id)
    return redirect(url_for('admin_areas'))

# Страница аккаунта редактора или пользователя
@app.route('/user_panel.html')
def user_panel():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))

    return render_template('user_panel.html')

# Добавление или изменение диагностики
@app.route('/add_diagnostic/<int:diagnostic_id>', methods=['GET', 'POST'])
def add_diagnostic(diagnostic_id):
    # Добавлять диагностики возможно только редактору или админу
    if session['role'] == 'Viewer':
        return redirect(url_for('index'))

    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    areas = get_areas()
    if diagnostic_id:
        edit_mode = True
        diagnostic = get_diagnostic_detail(diagnostic_id)
        
        if diagnostic['photo_path']:
            photo_count = len(diagnostic['photo_path'].split(','))
            photo_path = diagnostic['photo_path'].split(',')
        else:
            photo_count = 0
            photo_path = []
        user_name = session['username']
        yandex_api_key = get_yandex_api_key()
        return render_template('add_panel.html', user_name=user_name, yandex_api_key=yandex_api_key, diagnostic_id=diagnostic_id, diagnostic=diagnostic, photo_count=photo_count, photo_path=photo_path, areas=areas, edit_mode=edit_mode)
    else:
        edit_mode = False
        user_name = session['username']
        yandex_api_key = get_yandex_api_key()
        return render_template('add_panel.html', user_name=user_name, yandex_api_key=yandex_api_key, diagnostic_id=0, photo_count=0, photo_path=[], areas=areas, edit_mode=edit_mode)

# Страница успешного изменения диагностики
@app.route('/edit_form/<int:diagnostic_id>', methods=['GET', 'POST'])
def edit_diagnostic(diagnostic_id):
    if request.method == 'POST':
        # Получаем список фотографий, которые пользователь удалил
        photos_to_delete = request.form.get('photos_to_delete', '').split(',')

        # Удаляем файлы с диска и обновляем список фотографий
        current_photos = get_diagnostic_photo_path(diagnostic_id).split(',')
        updated_photos = [photo for photo in current_photos if photo not in photos_to_delete]

        # Удаление файлов с сервера
        for photo in photos_to_delete:
            if photo:  # Убедимся, что не пытаемся удалить пустую строку
                try:
                    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], photo[8:]))
                except OSError:
                    pass  # Файл может не существовать, обрабатываем этот случай

        files = request.files.getlist('photos')
        saved_files = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename('diagnostic_' + str(random.randint(1000000, 9999999)) + '_' + file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                saved_files.append(file_path[7:])

        # Добавляем новые фотографии к оставшимся
        updated_photos.extend(saved_files)

        # Получаем данные из формы для обновления записи
        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata = data_from_add_to_db(request)

        # Обновляем запись в БД
        edit_row(diagnostic_id, diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata, ','.join(updated_photos))

        # Redirect to the diagnostic details page
    return render_template('edit_form.html')
    
# Страница успешного добавления диагностики
@app.route('/submit_form', methods=['GET', 'POST'])
def submit_diagnostic():
    error = None  # обнуляем переменную ошибок
    if request.method == 'POST':
        # Обработка загруженных файлов

        files = request.files.getlist('photos')

        saved_files = []
        for file in files:

            if file and allowed_file(file.filename):
                filename = secure_filename('diagnostic_' + str(random.randint(1000000, 9999999)) + '_' + file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                saved_files.append(file_path[7:])


        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata = data_from_add_to_db(request)
        insert_to_db(diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_area, diagnostic_timestampdata, ','.join(saved_files))
        
    return render_template('submit_form.html', error=error)

@app.route('/view_diagnostics', methods=['GET'])
def view_diagnostics():
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    areas = get_areas()
    search_query = request.args.get('search_query', '')  # Получаем параметр search_query из строки запроса
    area_filter = request.args.get('areaFilter', 'all')
    sort_by = request.args.get('sort_by', 'date')  # Сортировка по умолчанию - по дате
    order = request.args.get('order', 'desc')  # Порядок сортировки по умолчанию - возрастание
    page = int(request.args.get('page', 1))  # Текущая страница, по умолчанию - 1
    per_page = 50  # Количество записей на странице

    # Получаем параметры фильтрации по дате
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    # Считаем дистанцию
    total_distance = distance_sum(start_date, end_date)

    # Устанавливаем начальный и конечный индексы для пагинации
    start = (page - 1) * per_page
    end = start + per_page

    diagnostics, total_pages = get_diagnostics(search_query, area_filter, sort_by, order, per_page, start)

    return render_template('view_page.html', areas=areas, diagnostics=diagnostics, sort_by=sort_by, order=order,
                           page=page, total_pages=total_pages, total_distance=total_distance)

@app.route('/diagnostic_page/<int:diagnostic_id>')
def diagnostic_page(diagnostic_id):
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    
    diagnostic = get_diagnostic_detail(diagnostic_id)
    problem_details, format_date, wells_details, photos_paths = format_diagnostic_data(diagnostic)
    plot_buf = generate_diagnostic_plot(diagnostic)
    
    return render_template('diagnostic_page.html', diagnostic=diagnostic, problem_details=problem_details, format_date=format_date, wells_details=wells_details, photos_paths=photos_paths, plot_image=base64.b64encode(plot_buf.getvalue()).decode('utf-8'))

@app.route('/diagnostic/<int:diagnostic_id>/generate_pdf')
def generate_pdf(diagnostic_id):
    # Загрузите данные о диагностике по идентификатору
    diagnostic = get_diagnostic_detail(diagnostic_id)
    area = get_area(diagnostic['areaid'])
    current_date = datetime.now().strftime("%d.%m.%Y")  # Форматирование даты
    problem_details, format_date, wells_details, photos_paths = format_diagnostic_data(diagnostic)
    plot_buf = generate_diagnostic_plot(diagnostic)
    if photos_paths:
        prepared_photos_paths = [url_for('static', filename=photo_path, _external=True) for photo_path in photos_paths]
        print(prepared_photos_paths)
    else:
        prepared_photos_paths = []
    # Рендеринг HTML-шаблона для PDF
    rendered = render_template('diagnostic_pdf.html', diagnostic=diagnostic, area=area, problem_details=problem_details, format_date=format_date, wells_details=wells_details, photos_paths=prepared_photos_paths, plot_image=base64.b64encode(plot_buf.getvalue()).decode('utf-8'), current_date=current_date)

    # Генерация PDF из рендеренного HTML
    pdf = pdfkit.from_string(rendered, False, configuration=config)

    # Отправка PDF-файла в качестве ответа
    response = send_file(
        io.BytesIO(pdf),
        download_name='diagnostic_report.pdf',
        as_attachment=True
    )
    return response

@app.route('/delete/<int:diagnostic_id>')
def delete_diagnostic(diagnostic_id):
    if 'user_id' not in session:
        return redirect(url_for('user_login'))
    if session['role'] == 'Viewer':
        return redirect(url_for('index'))
    delete_func(diagnostic_id)
    if session['role'] == 'Admin':
        return redirect(url_for('admin_diagnostics'))
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