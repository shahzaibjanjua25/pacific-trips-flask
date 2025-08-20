from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
import sqlite3
import uuid
from contextlib import closing
import os

# Create the Blueprint first
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Database Configuration
BASE_DIR = os.getcwd()
DATABASE = os.path.join(BASE_DIR, 'EMS.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        employee_id = request.form['employee_id']
        password = request.form['password']
        
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT empId, empName FROM employees WHERE empId = ?", (employee_id,))
            employee = cursor.fetchone()
            
            if not employee:
                flash('Employee ID not found', 'danger')
                return redirect(url_for('auth.register'))
            
            cursor.execute("SELECT * FROM users WHERE employee_id = ?", (employee_id,))
            if cursor.fetchone():
                flash('This employee already has an account', 'danger')
                return redirect(url_for('auth.register'))
            
            username = employee['empName'].lower().replace(' ', '_') + '_' + employee_id[:4]
            user_id = str(uuid.uuid4())[:8]
            password_hash = generate_password_hash(password)
            
            try:
                cursor.execute('''
                    INSERT INTO users (user_id, username, password_hash, role, employee_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, password_hash, 'employee', employee_id))
                conn.commit()
                
                flash('Registration successful! You can now login.', 'success')
                return redirect(url_for('auth.login'))
            except sqlite3.IntegrityError as e:
                flash('Registration failed. Please try again.', 'danger')
                return redirect(url_for('auth.register'))
    
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        employee_id = request.form['employeeId']  # note: you use employeeId in form, not username
        password = request.form['password']
        
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE employee_id = ?', (employee_id,))
            user_data = cursor.fetchone()
        
        if user_data and check_password_hash(user_data['password_hash'], password):
            from app import User
            user = User(user_data['user_id'], user_data['username'], 
                       user_data['role'], user_data['employee_id'])
            login_user(user)

            # Instead of redirect here, render template with success flag
            return render_template('login.html', login_success=True)
        else:
            flash('Invalid employee ID or password', 'danger')
    
    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile')
@login_required
def profile():
    if current_user.role != 'employee':
        flash('This page is for employees only', 'danger')
        return redirect(url_for('index'))

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM employees WHERE empId = ?', (current_user.employee_id,))
        employee = cursor.fetchone()

        if not employee:
            flash('Employee data not found', 'danger')
            return redirect(url_for('index'))

    return render_template('profile.html', employee=dict(employee))
