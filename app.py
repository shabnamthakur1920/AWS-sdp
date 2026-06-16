import os
from flask import Flask, render_template, request, redirect, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)


# Create tables automatically
def create_tables():
    cursor = mysql.connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            age INT NOT NULL,
            grade VARCHAR(20) NOT NULL
        )
    """)

    mysql.connection.commit()
    cursor.close()

    print("Tables created successfully.")


# Run table creation inside Flask context
with app.app_context():
    create_tables()


@app.route('/')
def index():
    cursor = mysql.connection.cursor()

    cursor.execute("""
        SELECT *
        FROM students
        ORDER BY id DESC
    """)

    students = cursor.fetchall()

    cursor.close()

    return render_template('index.html', students=students)


@app.route('/add', methods=['GET', 'POST'])
def add_student():

    if request.method == 'POST':

        name = request.form['name']
        age = request.form['age']
        grade = request.form['grade']

        cursor = mysql.connection.cursor()

        cursor.execute("""
            INSERT INTO students (name, age, grade)
            VALUES (%s, %s, %s)
        """, (name, age, grade))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('index'))

    return render_template('add.html')


@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_student(id):

    cursor = mysql.connection.cursor()

    if request.method == 'POST':

        name = request.form['name']
        age = request.form['age']
        grade = request.form['grade']

        cursor.execute("""
            UPDATE students
            SET name=%s,
                age=%s,
                grade=%s
            WHERE id=%s
        """, (name, age, grade, id))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('index'))

    cursor.execute("""
        SELECT *
        FROM students
        WHERE id=%s
    """, (id,))

    student = cursor.fetchone()

    cursor.close()

    return render_template('edit.html', student=student)


@app.route('/delete/<int:id>')
def delete_student(id):

    cursor = mysql.connection.cursor()

    cursor.execute("""
        DELETE FROM students
        WHERE id=%s
    """, (id,))

    mysql.connection.commit()
    cursor.close()

    return redirect(url_for('index'))


@app.route('/health')
def health():
    return {
        "status": "UP",
        "database": "CONNECTED"
    }


if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )