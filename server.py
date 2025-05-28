from flask import Flask, render_template, request, redirect, url_for, send_file, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import sqlite3
import os
from datetime import datetime
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

DB_PATH = 'myapp/database.db'

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/add_admin', methods=['GET', 'POST'])
def add_admin():
    if session.get('role') != 'admin':  # Только для администратора
        flash('У вас нет прав для доступа к этой странице.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Хэшируем пароль
        password_hash = generate_password_hash(password)

        # Подключаемся к базе данных
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        try:
            # Вставляем администратора в таблицу Users
            cursor.execute('''
                INSERT INTO Users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, 'admin'))

            conn.commit()
            flash('Новый администратор успешно добавлен!', 'success')
        except sqlite3.IntegrityError:
            flash('Этот логин или email уже существует в базе данных.', 'danger')
        finally:
            conn.close()

        return redirect(url_for('index'))  # Перенаправление на главную страницу

    return render_template('add_admin.html')  # Отображаем форму для добавления администратора


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO Users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
                         (username, email, password_hash, 'student'))  # Роль по умолчанию - студент
            conn.commit()
            flash('Регистрация прошла успешно! Теперь войдите.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Логин или почта уже используется.', 'danger')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM Users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Вы вошли в систему!', 'success')
            if user['role'] == 'admin':
                return redirect(url_for('index'))
            else:
                return redirect(url_for('profile'))
        else:
            flash('Неверный логин или пароль.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

def calculate_age(birth_date_str):
    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
    today = datetime.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

def format_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%d.%m.%Y')

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if session.get('role') == 'admin':
        conn = get_db_connection()
        departments = conn.execute('SELECT DISTINCT department FROM Students').fetchall()
        conn.close()
        return render_template('index.html', departments=departments)
    else:
        return redirect(url_for('profile'))

@app.route('/select_class/<department>')
def select_class(department):
    conn = get_db_connection()
    if session.get('role') == 'admin':
        # Если администратор, показываем все классы
        classes = conn.execute('SELECT DISTINCT class FROM Students WHERE department = ?', (department,)).fetchall()
    else:
        # Если студент, показываем только классы, к которым он принадлежит
        user_id = session.get('user_id')
        classes = conn.execute('''
            SELECT DISTINCT class FROM Students WHERE department = ? AND user_id = ?
        ''', (department, user_id)).fetchall()

    conn.close()
    return render_template('select_class.html', department=department, classes=classes)

@app.route('/select_normative/<department>/<class_name>')
def select_normative(department, class_name):
    conn = get_db_connection()
    normatives = conn.execute('SELECT id, name FROM Normatives').fetchall()
    conn.close()
    return render_template('select_normative.html', department=department, class_name=class_name, normatives=normatives)

@app.route('/select_student/<department>/<class_name>/<int:normative_id>')
def select_student(department, class_name, normative_id):
    conn = get_db_connection()
    if session.get('role') == 'admin':
        # Если администратор, показываем всех студентов
        students = conn.execute('SELECT id, full_name FROM Students WHERE department = ? AND class = ?', (department, class_name)).fetchall()
    else:
        # Если студент, показываем только своего
        user_id = session.get('user_id')
        students = conn.execute('SELECT id, full_name FROM Students WHERE department = ? AND class = ? AND user_id = ?', (department, class_name, user_id)).fetchall()

    normative = conn.execute('SELECT name FROM Normatives WHERE id = ?', (normative_id,)).fetchone()
    conn.close()
    return render_template('select_student.html', department=department, class_name=class_name, students=students, normative_id=normative_id, normative_name=normative['name'])

# Остальной код остается прежним...

@app.route('/add_result/<int:student_id>/<int:normative_id>', methods=['GET'])
def show_result_form(student_id, normative_id):
    conn = get_db_connection()

    student = conn.execute('SELECT * FROM Students WHERE id = ?', (student_id,)).fetchone()
    normative = conn.execute('SELECT * FROM Normatives WHERE id = ?', (normative_id,)).fetchone()

    if not student or not normative:
        conn.close()
        return "Ученик или норматив не найдены", 404

    # Вычисление возраста
    birth_date = datetime.strptime(student['birth_date'], '%Y-%m-%d')
    today = datetime.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    # Список всех сданных нормативов для этого ученика
    previous_results = conn.execute('''
        SELECT r.id, r.result_value, r.result_date, r.grade,
               n.name, n.unit
        FROM Results r
        JOIN Normatives n ON r.normative_id = n.id
        WHERE r.student_id = ?
        ORDER BY r.result_date DESC
    ''', (student_id,)).fetchall()

    conn.close()

    return render_template(
        'add_result.html',
        student=student,
        normative=normative,
        age=age,
        previous_results=previous_results
    )

@app.route('/add_result/<int:student_id>/<int:normative_id>', methods=['POST'])
def add_result(student_id, normative_id):
    result_value = request.form.get('result')
    if not result_value:
        return "Ошибка: результат не указан", 400

    try:
        result_value = float(result_value)
    except ValueError:
        return "Ошибка: результат должен быть числом", 400

    conn = get_db_connection()
    student = conn.execute('SELECT * FROM Students WHERE id = ?', (student_id,)).fetchone()
    normative = conn.execute('SELECT * FROM Normatives WHERE id = ?', (normative_id,)).fetchone()

    if not student or not normative:
        conn.close()
        return "Ученик или норматив не найден", 404

    birth_date = datetime.strptime(student['birth_date'], '%Y-%m-%d')
    today = datetime.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

    grade_row = conn.execute('''
        SELECT grade FROM Grades
        WHERE normative_id = ?
          AND gender = ?
          AND age = ?
          AND ? BETWEEN min_value AND max_value
    ''', (normative_id, student['gender'], age, result_value)).fetchone()

    grade = grade_row['grade'] if grade_row else None

    conn.execute('''
        INSERT INTO Results (student_id, normative_id, result_value, result_date, grade)
        VALUES (?, ?, ?, DATE('now'), ?)
    ''', (student_id, normative_id, result_value, grade))

    conn.commit()
    conn.close()

    return render_template('result_saved.html', student=student, normative=normative, result=result_value, grade=grade)


@app.route('/export_all_results/<string:department>/<string:class_name>')
def export_all_results(department, class_name):
    conn = get_db_connection()
    normatives = conn.execute('SELECT id, name FROM Normatives').fetchall()

    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')

    for norm in normatives:
        results_query = '''
            SELECT s.full_name AS "Ученик",
                   n.name AS "Норматив",
                   r.result_value AS "Результат",
                   r.grade AS "Оценка",
                   r.result_date AS "Дата"
            FROM Students s
            JOIN Results r ON s.id = r.student_id
            JOIN Normatives n ON r.normative_id = n.id
            WHERE s.department = ?
              AND s.class = ?
              AND r.normative_id = ?
        '''
        df = pd.read_sql(results_query, conn, params=(department, class_name, norm['id']))
        if not df.empty:
            sheet_name = norm['name'][:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    writer.close()
    output.seek(0)
    conn.close()

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        download_name=f'all_results_{class_name}.xlsx',
        as_attachment=True
    )

@app.route('/edit_result/<int:result_id>', methods=['GET', 'POST'])
def edit_result(result_id):
    conn = get_db_connection()
    if request.method == 'POST':
        new_value = request.form.get('result')
        try:
            new_value = float(new_value)
        except ValueError:
            return "Ошибка: результат должен быть числом", 400

        result = conn.execute('SELECT * FROM Results WHERE id = ?', (result_id,)).fetchone()
        if not result:
            conn.close()
            return "Результат не найден", 404

        student = conn.execute('SELECT * FROM Students WHERE id = ?', (result['student_id'],)).fetchone()
        normative = conn.execute('SELECT * FROM Normatives WHERE id = ?', (result['normative_id'],)).fetchone()

        age = calculate_age(student['birth_date'])

        grade_row = conn.execute('''
            SELECT grade FROM Grades
            WHERE normative_id = ?
              AND gender = ?
              AND age = ?
              AND ? BETWEEN min_value AND max_value
        ''', (normative['id'], student['gender'], age, new_value)).fetchone()
        grade = grade_row['grade'] if grade_row else None

        conn.execute('''
            UPDATE Results
            SET result_value = ?, grade = ?
            WHERE id = ?
        ''', (new_value, grade, result_id))
        conn.commit()
        conn.close()
        return redirect(url_for('show_result_form', student_id=student['id'], normative_id=normative['id']))
    else:
        result = conn.execute('SELECT * FROM Results WHERE id = ?', (result_id,)).fetchone()
        conn.close()
        return render_template('edit_result.html', result=result)


@app.route('/delete_result/<int:result_id>', methods=['POST'])
def delete_result(result_id):
    conn = get_db_connection()

    # Получаем нужную информацию для возврата на страницу ученика
    result = conn.execute('''
        SELECT r.id, s.id as student_id, s.department, s.class, r.normative_id
        FROM Results r
        JOIN Students s ON r.student_id = s.id
        WHERE r.id = ?
    ''', (result_id,)).fetchone()

    if not result:
        conn.close()
        return "Результат не найден", 404

    conn.execute('DELETE FROM Results WHERE id = ?', (result_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('show_result_form', student_id=result['student_id'], normative_id=result['normative_id']))



@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    conn = get_db_connection()
    student = conn.execute('SELECT * FROM Students WHERE user_id = ?', (session['user_id'],)).fetchone()

    # Расчёт возраста
    if student['birth_date']:
        birth_date = datetime.strptime(student['birth_date'], '%Y-%m-%d')
        age = (datetime.now() - birth_date).days // 365
    else:
        age = None

    if request.method == 'POST':
        height = request.form.get('height')
        weight = request.form.get('weight')
        photo = request.files.get('photo')

        # Загрузка фото
        if photo and allowed_file(photo.filename):
            filename = secure_filename(photo.filename)
            photo_filename = f"{datetime.utcnow().timestamp()}_{filename}"
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
            conn.execute('UPDATE Students SET photo = ? WHERE user_id = ?', (photo_filename, session['user_id']))

        # Обновление данных роста и веса
        if height and weight:
            conn.execute('UPDATE Students SET height = ?, weight = ? WHERE user_id = ?',
                         (height, weight, session['user_id']))
            height_m = float(height) / 100
            bmi = round(float(weight) / (height_m ** 2), 2)

            # Сохранение изменений здоровья
            conn.execute('''
                INSERT INTO StudentHealthChanges (student_id, height, weight, bmi, change_date, changed_by)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (student['id'], height, weight, bmi, session['user_id']))
        conn.commit()
        conn.close()
        return redirect(url_for('profile'))

    results = conn.execute('''
        SELECT r.result_value, r.result_date, n.name AS normative_name, n.unit
        FROM Results r
        JOIN Normatives n ON r.normative_id = n.id
        WHERE r.student_id = ?
    ''', (student['id'],)).fetchall()

    functional_tests = conn.execute('''
        SELECT test_name, result_value, result_date
        FROM FunctionalTests
        WHERE student_id = ?
    ''', (student['id'],)).fetchall()

    health_changes = conn.execute('''
        SELECT height, weight, bmi, change_date
        FROM StudentHealthChanges
        WHERE student_id = ?
        ORDER BY change_date DESC
    ''', (student['id'],)).fetchall()

    conn.close()

    if student['height'] and student['weight']:
        height_m = student['height'] / 100
        bmi = round(student['weight'] / (height_m ** 2), 2)
    else:
        bmi = "Нет данных"

    return render_template('profile.html', student=student, age=age, results=results,
                           functional_tests=functional_tests, bmi=bmi, health_changes=health_changes)

if __name__ == '__main__':
    app.run(debug=True)