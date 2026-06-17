import os
import uuid
from flask import Flask, render_template, request, redirect, url_for
from flask_mysqldb import MySQL
from dotenv import load_dotenv
import boto3
from botocore.config import Config
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB limit

mysql = MySQL(app)

# S3 Configuration — credentials come from EC2 IAM role automatically
S3_BUCKET = os.getenv('S3_BUCKET')
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')

# Resolve the bucket's actual region, then build the client with SigV4 + virtual-hosted style
# SigV4 + virtual-hosted style is required for presigned URLs on non-us-east-1 buckets
_s3_probe = boto3.client('s3', region_name='us-east-1')
try:
    _loc = _s3_probe.get_bucket_location(Bucket=S3_BUCKET)
    AWS_REGION = _loc['LocationConstraint'] or 'us-east-1'
except Exception:
    pass  # fall back to env value

_s3_config = Config(
    signature_version='s3v4',
    s3={'addressing_style': 'virtual'}
)
s3 = boto3.client('s3', region_name=AWS_REGION, config=_s3_config)

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_RESUME_EXTENSIONS = {'pdf', 'doc', 'docx'}


def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def allowed_resume(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_RESUME_EXTENSIONS


def upload_to_s3(file, folder):
    key = f"{folder}/{uuid.uuid4().hex}_{secure_filename(file.filename)}"
    content_type = file.content_type or 'application/octet-stream'
    s3.upload_fileobj(file, S3_BUCKET, key, ExtraArgs={'ContentType': content_type})
    return key


def presigned_url(key, expiry=3600):
    if not key:
        return None
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': S3_BUCKET, 'Key': key},
        ExpiresIn=expiry
    )


def create_tables():
    cursor = mysql.connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            age INT NOT NULL,
            grade VARCHAR(20) NOT NULL,
            profile_image VARCHAR(500),
            resume VARCHAR(500)
        )
    """)

    # Add new columns to existing tables without breaking old data
    for col, coltype in [('profile_image', 'VARCHAR(500)'), ('resume', 'VARCHAR(500)')]:
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='students' AND COLUMN_NAME=%s",
            (col,)
        )
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute(f"ALTER TABLE students ADD COLUMN {col} {coltype}")

    mysql.connection.commit()
    cursor.close()
    print("Tables ready.")


with app.app_context():
    create_tables()


@app.route('/')
def index():
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM students ORDER BY id DESC")
    students = cursor.fetchall()
    cursor.close()
    for student in students:
        student['profile_image_url'] = presigned_url(student.get('profile_image'))
        student['resume_url'] = presigned_url(student.get('resume'))
    return render_template('index.html', students=students)


@app.route('/add', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        age = request.form['age']
        grade = request.form['grade']

        profile_image_key = None
        resume_key = None

        file = request.files.get('profile_image')
        if file and file.filename and allowed_image(file.filename):
            profile_image_key = upload_to_s3(file, 'profile-images')

        file = request.files.get('resume')
        if file and file.filename and allowed_resume(file.filename):
            resume_key = upload_to_s3(file, 'resumes')

        cursor = mysql.connection.cursor()
        cursor.execute(
            "INSERT INTO students (name, age, grade, profile_image, resume) VALUES (%s, %s, %s, %s, %s)",
            (name, age, grade, profile_image_key, resume_key)
        )
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

        # Preserve existing S3 keys if no new file is uploaded
        profile_image_key = request.form.get('existing_profile_image') or None
        resume_key = request.form.get('existing_resume') or None

        file = request.files.get('profile_image')
        if file and file.filename and allowed_image(file.filename):
            profile_image_key = upload_to_s3(file, 'profile-images')

        file = request.files.get('resume')
        if file and file.filename and allowed_resume(file.filename):
            resume_key = upload_to_s3(file, 'resumes')

        cursor.execute(
            "UPDATE students SET name=%s, age=%s, grade=%s, profile_image=%s, resume=%s WHERE id=%s",
            (name, age, grade, profile_image_key, resume_key, id)
        )
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('index'))

    cursor.execute("SELECT * FROM students WHERE id=%s", (id,))
    student = cursor.fetchone()
    cursor.close()
    return render_template('edit.html', student=student)


@app.route('/delete/<int:id>')
def delete_student(id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM students WHERE id=%s", (id,))
    mysql.connection.commit()
    cursor.close()
    return redirect(url_for('index'))


@app.route('/health')
def health():
    return {"status": "UP", "database": "CONNECTED"}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
