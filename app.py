import os
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_wtf.csrf import CSRFError
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user

from models import db, User, BedFile
from utils import parse_bed_file, compute_all_jaccards


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bedapp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Safety 
ADMINS = {'kugi8412'}
csrf = CSRFProtect(app)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def setup():
    db.create_all()

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('The form submission was invalid. Please try again.', 'danger')
    return redirect(url_for('file_list'))



# AUTHORIZATION
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('User already exists.')
            return redirect(url_for('register'))
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('Login successful!')
            return redirect(url_for('index'))
        flash('Invalid credentials.')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out.')
    return redirect(url_for('index'))

# ROUTES
@app.route('/')
def index():
    return render_template('base.html')

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected.')
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash('Only .bed and .bed.gz files are supported.')
            return redirect(request.url)

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        if BedFile.query.filter_by(filename=filename).first():
            flash('File already exists.')
            return redirect(request.url)

        _, total_len = parse_bed_file(filepath)
        db.session.add(BedFile(
            filename=filename,
            filepath=filepath,
            total_length=total_len,
            uploaded_by=current_user.id
        ))
        db.session.commit()
        flash('File uploaded.')
        return redirect(url_for('file_list'))

    return render_template('upload_file.html')

@app.route('/files')
@login_required
def file_list():
    page = request.args.get('page', 1, type=int)
    pagination = BedFile.query.paginate(page=page, per_page=5)
    return render_template('file_list.html', files=pagination.items, pagination=pagination)

@app.route('/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    if current_user.username not in ADMINS:
        flash('Permission denied.', 'danger')
        return redirect(url_for('file_list'))

    file_entry = BedFile.query.get(file_id)
    if not file_entry:
        flash('File not found in database.', 'danger')
        return redirect(url_for('file_list'))

    file_path = file_entry.filepath
    success = True

    # Delete physical file
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'File "{file_entry.filename}" deleted from storage.', 'success')
    except FileNotFoundError:
        flash(f'Warning: File "{file_entry.filename}" not found in storage.', 'warning')
    except Exception as e:
        success = False
        flash(f'Error deleting file: {str(e)}', 'danger')

    # Delete database record if file deletion succeeded or file was already missing
    if success:
        try:
            db.session.delete(file_entry)
            db.session.commit()
            flash('Database record removed successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error removing database record: {str(e)}', 'danger')

    return redirect(url_for('file_list'))

@app.route('/compare', methods=['GET', 'POST'])
@login_required
def compare():
    files = BedFile.query.all()
    if request.method == 'POST':
        existing_id = request.form.get('existing_file')
        upload_option = request.form.get('upload_option')
        uploaded_file = request.files.get('file')

        try:
            N = min(int(request.form.get('N', 3)), len(files) - (1 if existing_id else 0))
        except ValueError:
            N = 3

        if existing_id:
            file_entry = db.session.get(BedFile, existing_id)
            input_tree, input_len = parse_bed_file(file_entry.filepath)
        elif uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            uploaded_file.save(temp_path)
            input_tree, input_len = parse_bed_file(temp_path)

            if upload_option == 'permanent' and not BedFile.query.filter_by(filename=filename).first():
                db.session.add(BedFile(
                    filename=filename,
                    filepath=temp_path,
                    total_length=input_len,
                    uploaded_by=current_user.id
                ))
                db.session.commit()
        else:
            flash('No input file provided.')
            return redirect(request.url)

        exclude_id = int(existing_id) if existing_id else None
        comparison_set = [f for f in files if f.id != exclude_id]
        all_results = compute_all_jaccards(input_tree, input_len, comparison_set)

        identical = [r for r in all_results if r['jaccard'] == 1.0]
        others = sorted((r for r in all_results if r['jaccard'] < 1.0), key=lambda r: r['jaccard'], reverse=True)[:N]

        return render_template('results.html', results={'identical': identical, 'others': others})

    return render_template('compare.html', files=files)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'bed', 'gz'}

if __name__ == '__main__':
    app.run(debug=True)
