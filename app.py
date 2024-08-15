from flask import Flask, render_template, redirect, url_for, request, session
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib
import base64
from db_requests import get_db_connection, get_diagnostic_detail, get_diagnostics, format_diagnostic_data, get_diagnostics_coordinates, delete_func, data_from_add_to_db, insert_to_db, edit_row
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
        c = conn.cursor(cursor_factory=RealDictCursor)  # используем RealDictCursor
        # создаем запрос для поиска пользователя по username,
        # если такой пользователь существует, то получаем все данные id, password
        c.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = c.fetchone()
        # закрываем подключение БД
        conn.close()

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
        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata = data_from_add_to_db(request)
        edit_row(diagnostic_id, diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata)

        # Redirect to the diagnostic details page
    return render_template('edit_form.html')
    
# Страница успешного добавления диагностики
@app.route('/submit_form', methods=['GET', 'POST'])
def submit_diagnostic():
    error = None  # обнуляем переменную ошибок
    if request.method == 'POST':
        diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata = data_from_add_to_db(request)
        insert_to_db(diagnostic_name, diagnostic_address, diagnostic_kind, diagnostic_date, diagnostic_coordinates, diagnostic_type, diagnostic_diameter, diagnostic_material, diagnostic_distance, diagnostic_wells, diagnostic_spans, diagnostic_slopes, diagnostic_flows, diagnostic_author, diagnostic_problems, diagnostic_problem_distances, diagnostic_timestampdata)
        
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
     return render_template('map_page.html', diagnostics=diagnostics_list, yandex_api_key=yandex_api_key)


if __name__ == '__main__':
    app.run(debug=True)