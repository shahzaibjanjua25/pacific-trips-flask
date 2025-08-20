from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid
from contextlib import closing
import json
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# Database Configuration
BASE_DIR = os.getcwd()
DATABASE = os.path.join(BASE_DIR, 'EMS.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                employeeId TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'employee')),
                createdAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create employees table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                empId TEXT PRIMARY KEY,
                empName TEXT NOT NULL,
                phoneNo TEXT,
                targetAmount REAL,
                achievedAmount REAL DEFAULT 0,
                createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
                updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create customers table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                customerId TEXT PRIMARY KEY,
                customerName TEXT NOT NULL,
                phone TEXT,
                status TEXT,
                source TEXT,
                currentLocation TEXT,
                desiredDestination TEXT,
                dateOfArrival TEXT,
                createdAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create leads table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leads (
                employeeLeadId TEXT PRIMARY KEY,
                employeeId TEXT,
                employeeName TEXT,
                employeeContactNo TEXT,
                customerId TEXT,
                customerName TEXT,
                customerContactNo TEXT,
                currentAddress TEXT,
                desiredDestination TEXT,
                status TEXT,
                source TEXT,
                amountClosed REAL DEFAULT 0,
                createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
                updatedAt TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Create logs table if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                log_id TEXT PRIMARY KEY,
                table_name TEXT NOT NULL,
                action TEXT NOT NULL,
                record_id TEXT NOT NULL,
                description TEXT,
                old_values TEXT,
                new_values TEXT,
                created_at TEXT NOT NULL,
                changed_by TEXT,
                lead_employee TEXT
            )
        ''')
        conn.commit()

def get_all_employees():
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT empId, empName FROM employees")
            return cursor.fetchall()

def get_all_customers():
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT customerId, customerName FROM customers")
            return cursor.fetchall()

def get_employee_details(emp_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM employees WHERE empId = ?", (emp_id,))
            return cursor.fetchone()

def generate_status_chart(chart_data):
    """
    Convert the chart data from Flask to a format suitable for Python charting libraries.
    Returns data structured for either Matplotlib or Plotly.
    """
    # Status colors mapping
    status_colors = {
        'Pending': '#3498db',        # Blue
        'Contacted': '#f1c40f',      # Yellow
        'Not interested': '#e74c3c', # Red (replacing Lost)
        'Qoutation': '#6f42c1',      # Purple
        'Group Trip': '#2ecc71',     # Green
        'Refund': '#95a5a6',         # Gray
        'Confirmed': '#27ae60'       # Dark Green
    }

    # Process the data similar to the JavaScript version
    processed_data = {
        'labels': [],  # Dates
        'datasets': []  # Employee status data
    }

    # Temporary storage for employee-status combinations
    temp_data = {}

    for date, employees_data in chart_data.items():
        processed_data['labels'].append(date)
        
        for employee_id, employee_info in employees_data.items():
            for status, count in employee_info['statuses'].items():
                key = f"{employee_id}-{status}"
                if key not in temp_data:
                    temp_data[key] = {
                        'label': f"{employee_info['name']} - {status}",
                        'data': [0] * len(processed_data['labels']),
                        'backgroundColor': status_colors.get(status, '#95a5a6'),
                        'borderColor': status_colors.get(status, '#95a5a6'),
                        'employee_name': employee_info['name'],
                        'status': status
                    }
                # Update the count for this date
                temp_data[key]['data'][-1] = count

    # Add datasets to the main structure
    for dataset in temp_data.values():
        processed_data['datasets'].append(dataset)

    return processed_data


# Example usage with Plotly
def create_plotly_chart(chart_data):
    processed_data = generate_status_chart(chart_data)
    
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    for dataset in processed_data['datasets']:
        fig.add_trace(go.Bar(
            x=processed_data['labels'],
            y=dataset['data'],
            name=dataset['label'],
            marker_color=dataset['backgroundColor'],
            hovertemplate=
                '<b>%{x}</b><br>' +
                f'Employee: {dataset["employee_name"]}<br>' +
                f'Status: {dataset["status"]}<br>' +
                'Count: %{y}<extra></extra>'
        ))
    
    fig.update_layout(
        barmode='stack',
        title='Lead Status Changes Over Time',
        xaxis_title='Date',
        yaxis_title='Count',
        hovermode='x unified'
    )
    
    return fig


# Example usage with Matplotlib
def create_matplotlib_chart(chart_data):
    processed_data = generate_status_chart(chart_data)
    
    import matplotlib.pyplot as plt
    import numpy as np
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    dates = processed_data['labels']
    x = np.arange(len(dates))
    
    # Track cumulative heights for stacking
    cumulative = np.zeros(len(dates))
    
    for dataset in processed_data['datasets']:
        ax.bar(
            x, 
            dataset['data'], 
            bottom=cumulative,
            label=dataset['label'],
            color=dataset['backgroundColor'],
            edgecolor=dataset['borderColor']
        )
        cumulative += np.array(dataset['data'])
    
    ax.set_xticks(x)
    ax.set_xticklabels(dates, rotation=45)
    ax.set_title('Lead Status Changes Over Time')
    ax.set_xlabel('Date')
    ax.set_ylabel('Count')
    ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    
    plt.tight_layout()
    return fig

def get_filtered_sorted_leads(employee_id, customer_id, status, start_date, source, end_date, sort_by, sort_order):
    query = '''
        SELECT leads.*, 
               customers.customerName AS cust_name, 
               employees.empName AS emp_name
        FROM leads
        LEFT JOIN customers ON leads.customerId = customers.customerId
        LEFT JOIN employees ON leads.employeeId = employees.empId
        WHERE 1=1
    '''
    params = []

    if employee_id:
        query += ' AND leads.employeeId = ?'
        params.append(employee_id)
    if customer_id:
        query += ' AND leads.customerId = ?'
        params.append(customer_id)
    if status:
        query += ' AND leads.status IN (?, ?, ?, ?, ?, ?, ?)'
        params.append(status)
    if source:
        query += ' AND leads.source IN (?, ?, ?, ?, ?, ?, ?)'
        params.append(source)
    if start_date:
        query += ' AND DATE(leads.createdAt) >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND DATE(leads.createdAt) <= ?'
        params.append(end_date)

    query += f' ORDER BY {sort_by} {sort_order.upper()}'

    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

def log_change(table_name, action, record_id, description, old_values=None, new_values=None, changed_by=None, lead_employee=None):
    log_id = str(uuid.uuid4())[:8]
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute('''
                INSERT INTO logs 
                (log_id, table_name, action, record_id, description, 
                 old_values, new_values, created_at, changed_by, lead_employee)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                log_id,
                table_name,
                action,
                record_id,
                description,
                json.dumps(old_values) if old_values else None,
                json.dumps(new_values) if new_values else None,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                changed_by or 'system',
                lead_employee
            ))
            conn.commit()

def migrate_db():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE logs ADD COLUMN changed_by TEXT DEFAULT 'system'")
            cursor.execute("ALTER TABLE logs ADD COLUMN lead_employee TEXT")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e):
                raise

# Authentication middleware
def login_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def admin_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'danger')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

def employee_required(f):
    def wrap(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first.', 'danger')
            return redirect(url_for('login'))
        if session.get('role') != 'employee':
            flash('Employee access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        employee_id = request.form['employeeId']
        password = request.form['password']
        
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                # Check if employee exists
                cursor.execute("SELECT empId, empName FROM employees WHERE empId = ?", (employee_id,))
                employee = cursor.fetchone()
                
                if not employee:
                    flash('Invalid Employee ID.', 'danger')
                    return redirect(url_for('register'))
                
                # Check if employee is already registered
                cursor.execute("SELECT employeeId FROM users WHERE employeeId = ?", (employee_id,))
                if cursor.fetchone():
                    flash('Employee ID already registered.', 'danger')
                    return redirect(url_for('register'))
                
                # Register employee
                password_hash = generate_password_hash(password)
                cursor.execute('''
                    INSERT INTO users (employeeId, password_hash, role)
                    VALUES (?, ?, 'employee')
                ''', (employee_id, password_hash))
                conn.commit()
                
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        employee_id = request.form['employeeId']
        password = request.form['password']
        
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                # Check if user exists
                cursor.execute("SELECT * FROM users WHERE employeeId = ?", (employee_id,))
                user = cursor.fetchone()
                
                if user and check_password_hash(user['password_hash'], password):
                    session['user_id'] = user['employeeId']
                    session['role'] = user['role']
                    employee = get_employee_details(user['employeeId'])
                    session['user_name'] = employee['empName'] if employee else 'Admin'
                    flash('Login successful!', 'success')
                    return redirect(url_for('index'))
                else:
                    flash('Invalid credentials.', 'danger')
                    return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    session.pop('user_name', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('base.html')

@app.route('/profile')
@login_required
def profile():
    if session.get('role') != 'employee':
        flash('This page is for employees only', 'danger')
        return redirect(url_for('index'))

    employee = get_employee_details(session['user_id'])
    if not employee:
        flash(f'Employee details not found for ID: {session["user_id"]}. Please contact an admin.', 'danger')
        return redirect(url_for('index'))
    
    return render_template('profile.html', employee=employee)


@app.route('/customers')
@admin_required
@login_required
def customers():    
    filters = {
        "customerName": request.args.get("customerName", ""),
        "phone": request.args.get("phone", ""),
        "source": request.args.get("source", ""),
        "currentLocation": request.args.get("currentLocation", ""),
        "desiredDestination": request.args.get("desiredDestination", ""),
        "start_date": request.args.get("start_date", ""),
        "end_date": request.args.get("end_date", "")
    }

    sort_by = request.args.get("sort_by", "customerName")
    sort_order = request.args.get("sort_order", "asc")

    query = "SELECT * FROM customers WHERE 1=1"
    params = []

    for col, val in filters.items():
        if val and col not in ["start_date", "end_date"]:
            query += f" AND {col} = ?"
            params.append(val)

    if filters['start_date']:
        query += " AND DATE(createdAt) >= ?"
        params.append(filters['start_date'])
    if filters['end_date']:
        query += " AND DATE(createdAt) <= ?"
        params.append(filters['end_date'])

    query += f" ORDER BY {sort_by} {sort_order.upper()}"

    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            customers = cursor.fetchall()

            column_values = {}
            for col in filters:
                if col not in ["start_date", "end_date"]:
                    cursor.execute(f"SELECT DISTINCT {col} FROM customers ORDER BY {col}")
                    column_values[col] = [row[0] for row in cursor.fetchall() if row[0]]
                else:
                    column_values[col] = []  # No dropdown for dates

    return render_template("customers.html",
                         customers=customers,
                         filters=filters,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         column_values=column_values)


@app.route('/add_customer', methods=['GET', 'POST'])
@login_required
def add_customer():
    if request.method == 'POST':
        new_id = str(uuid.uuid4())[:8]
        form = request.form
        amount_closed = float(form.get('amountClosed', 0))
        new_values = {
            'customerId': new_id,
            'customerName': form['customerName'],
            'phone': form['phone'],
            'status': form['status'],
            'source': form['source'],
            'currentLocation': form['currentLocation'],
            'desiredDestination': form['desiredDestination'],
            'dateOfArrival': form['dateOfArrival']
        }
        employee = get_employee_details(session['user_id'])
        if not employee:
            flash("Employee details not found.", "danger")
            return redirect(url_for('add_customer'))
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute('''
                    INSERT INTO customers 
                    (customerId, customerName, phone, status, source, currentLocation, desiredDestination, dateOfArrival)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_id,
                    form['customerName'],
                    form['phone'],
                    form['status'],
                    form['source'],
                    form['currentLocation'],
                    form['desiredDestination'],
                    form['dateOfArrival']
                ))

                # Insert into leads
                lead_id = str(uuid.uuid4())[:8]
                lead_amount_closed = amount_closed if form['status'] == 'Confirmed' else 0
                cursor.execute('''
                    INSERT INTO leads 
                    (employeeLeadId, employeeId, employeeName, employeeContactNo, 
                     customerId, customerName, customerContactNo, 
                     currentAddress, desiredDestination, status, source, amountClosed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lead_id,
                    employee['empId'],
                    employee['empName'],
                    employee['phoneNo'],
                    new_id,
                    form['customerName'],
                    form['phone'],
                    form['currentLocation'],
                    form['desiredDestination'],
                    form['status'],
                    form['source'],
                    lead_amount_closed
                ))

                if form['status'] == 'Confirmed' and amount_closed > 0:
                    new_achieved = employee['achievedAmount'] + amount_closed
                    cursor.execute('''
                        UPDATE employees 
                        SET achievedAmount = ?
                        WHERE empId = ?
                    ''', (new_achieved, employee['empId']))

                conn.commit()
        
        # Log the customer insertion
        description = f"Added customer {form['customerName']} with ID {new_id}"
        log_change('customers', 'INSERT', new_id, description, new_values=new_values, changed_by=session['user_id'])
        
        # Log the lead insertion
        lead_new_values = {
            'employeeLeadId': lead_id,
            'employeeId': employee['empId'],
            'customerId': new_id,
            'status': form['status'],
            'source': form['source'],
            'currentAddress': form['currentLocation'],
            'desiredDestination': form['desiredDestination'],
            'amountClosed': lead_amount_closed
        }
        lead_description = f"Added lead {lead_id} for employee {employee['empName']} and customer {form['customerName']}"
        log_change('leads', 'INSERT', lead_id, lead_description, new_values=lead_new_values, changed_by=session['user_id'], lead_employee=employee['empId'])
        
        flash("Customer and Lead added!", "success")
        return redirect(url_for('leads'))

    return render_template('add_customer.html')

@app.route('/customers/edit/<string:customer_id>', methods=['GET', 'POST'])
@admin_required
def edit_customer(customer_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM customers WHERE customerId = ?", (customer_id,))
            customer = cursor.fetchone()

    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for('customers'))

    if request.method == 'POST':
        form = request.form
        old_values = dict(customer)  # Convert SQLite Row to dict
        new_values = {
            'customerName': form['customerName'],
            'phone': form['phone'],
            'status': form['status'],
            'source': form['source'],
            'currentLocation': form['currentLocation'],
            'desiredDestination': form['desiredDestination'],
            'dateOfArrival': form['dateOfArrival']
        }
        
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute('''
                    UPDATE customers
                    SET customerName = ?, phone = ?, status = ?, source = ?, currentLocation = ?, 
                        desiredDestination = ?, dateOfArrival = ?
                    WHERE customerId = ?
                ''', (
                    form['customerName'],
                    form['phone'],
                    form['status'],
                    form['source'],
                    form['currentLocation'],
                    form['desiredDestination'],
                    form['dateOfArrival'],
                    customer_id
                ))

                cursor.execute('''
                    UPDATE leads
                    SET status = ?, 
                        source = ?,
                        currentAddress = ?,
                        desiredDestination = ?,
                        updatedAt = datetime('now')
                    WHERE customerId = ?
                ''', (
                    form['status'],
                    form['source'],
                    form['currentLocation'],
                    form['desiredDestination'],
                    customer_id
                ))
                
                conn.commit()

        # Log the update
        changes = [f"{key} from '{old_values[key]}' to '{new_values[key]}'" for key in new_values if old_values[key] != new_values[key]]
        description = f"Updated customer {form['customerName']} (ID: {customer_id}): {', '.join(changes)}" if changes else f"No changes to customer {form['customerName']} (ID: {customer_id})"
        log_change('customers', 'UPDATE', customer_id, description, old_values=old_values, new_values=new_values)

        flash("Customer and related leads updated!", "info")
        return redirect(url_for('customers'))

    return render_template('edit_customer.html', customer=customer)

@app.route('/customers/delete/<string:customer_id>')
@admin_required
def delete_customer(customer_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM customers WHERE customerId = ?", (customer_id,))
            customer = cursor.fetchone()
            if customer:
                old_values = dict(customer)
                cursor.execute("DELETE FROM customers WHERE customerId = ?", (customer_id,))
                conn.commit()
                
                # Log the deletion
                description = f"Deleted customer {customer['customerName']} (ID: {customer_id})"
                log_change('customers', 'DELETE', customer_id, description, old_values=old_values)
                
                flash("Customer deleted!", "success")
            else:
                flash("Customer not found!", "danger")
    return redirect(url_for('customers'))

@app.route('/employees')
@admin_required
def employees():
    filters = {
        'empName': request.args.get('empName', ''),
        'phoneNo': request.args.get('phoneNo', ''),
        'start_date': request.args.get('start_date', ''),
        'end_date': request.args.get('end_date', '')
    }

    sort_by = request.args.get('sort_by', 'empId')
    sort_order = request.args.get('sort_order', 'asc')

    query = "SELECT * FROM employees WHERE 1=1"
    params = []

    for col in ['empName', 'phoneNo']:
        val = filters[col]
        if val:
            query += f" AND {col} = ?"
            params.append(val)

    if filters['start_date']:
        query += " AND DATE(createdAt) >= ?"
        params.append(filters['start_date'])

    if filters['end_date']:
        query += " AND DATE(createdAt) <= ?"
        params.append(filters['end_date'])

    query += f" ORDER BY {sort_by} {sort_order.upper()}"

    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            employees = cursor.fetchall()

            column_values = {
                'empName': [row['empName'] for row in conn.execute("SELECT DISTINCT empName FROM employees")],
                'phoneNo': [row['phoneNo'] for row in conn.execute("SELECT DISTINCT phoneNo FROM employees")]
            }

    return render_template('employees.html',
                         employees=employees,
                         filters=filters,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         column_values=column_values)

@app.route('/employee/add', methods=['GET', 'POST'])
@admin_required
def add_employee():
    if request.method == 'POST':
        empId = str(uuid.uuid4())[:8]
        form = request.form
        new_values = {
            'empId': empId,
            'empName': form['empName'],
            'phoneNo': form['phoneNo'],
            'targetAmount': form['targetAmount'],
            'achievedAmount': form['achievedAmount']
        }
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute('''
                    INSERT INTO employees 
                    (empId, empName, phoneNo, targetAmount, achievedAmount, createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ''', (
                    empId,
                    form['empName'],
                    form['phoneNo'],
                    form['targetAmount'],
                    form['achievedAmount']
                ))
                conn.commit()
        
        # Log the insertion
        description = f"Added employee {form['empName']} with ID {empId}"
        log_change('employees', 'INSERT', empId, description, new_values=new_values)
        
        flash(f"Employee added! ID: {empId}", "success")
        return redirect(url_for('employees'))

    preview_emp_id = str(uuid.uuid4())[:8]
    return render_template('add_employee.html', empId=preview_emp_id)

@app.route('/employee/edit/<string:emp_id>', methods=['GET', 'POST'])
@admin_required
def edit_employee(emp_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM employees WHERE empId = ?", (emp_id,))
            employee = cursor.fetchone()

    if not employee:
        flash("Employee not found", "danger")
        return redirect(url_for('employees'))

    if request.method == 'POST':
        form = request.form
        old_values = dict(employee)
        new_values = {
            'empName': form['empName'],
            'phoneNo': form['phoneNo'],
            'targetAmount': form['targetAmount'],
            'achievedAmount': form['achievedAmount']
        }
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute('''
                    UPDATE employees
                    SET empName = ?, phoneNo = ?, targetAmount = ?, achievedAmount = ?, updatedAt = datetime('now')
                    WHERE empId = ?
                ''', (
                    form['empName'],
                    form['phoneNo'],
                    form['targetAmount'],
                    form['achievedAmount'],
                    emp_id
                ))
                conn.commit()
        
        # Log the update
        changes = [f"{key} from '{old_values[key]}' to '{new_values[key]}'" for key in new_values if old_values[key] != new_values[key]]
        description = f"Updated employee {form['empName']} (ID: {emp_id}): {', '.join(changes)}" if changes else f"No changes to employee {form['empName']} (ID: {emp_id})"
        log_change('employees', 'UPDATE', emp_id, description, old_values=old_values, new_values=new_values)

        flash("Employee updated!", "info")
        return redirect(url_for('employees'))

    return render_template('edit_employee.html', employee=employee)

@app.route('/employee/delete/<string:emp_id>')
@admin_required
def delete_employee(emp_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM employees WHERE empId = ?", (emp_id,))
            employee = cursor.fetchone()
            if employee:
                old_values = dict(employee)
                cursor.execute("DELETE FROM employees WHERE empId = ?", (emp_id,))
                conn.commit()
                
                # Log the deletion
                description = f"Deleted employee {employee['empName']} (ID: {emp_id})"
                log_change('employees', 'DELETE', emp_id, description, old_values=old_values)
                
                flash("Employee deleted!", "success")
            else:
                flash("Employee not found!", "danger")
    return redirect(url_for('employees'))
@app.route('/leads', methods=['GET'])
@login_required
def leads():
    filters = {
        "employeeId": request.args.get("employeeId", ''),
        "customerId": request.args.get('customerId', ''),
        "status": request.args.get('status', ''),
        "source": request.args.get('source', ''),
        "start_date": request.args.get('start_date', ''),
        "end_date": request.args.get('end_date', '')
    }
    
    sort_by = request.args.get('sort_by', 'employeeLeadId')
    sort_order = request.args.get('sort_order', 'asc')

    if session['role'] == 'employee':
        filters["employeeId"] = session['user_id']

    leads = get_filtered_sorted_leads(
        filters["employeeId"],
        filters["customerId"],
        filters["status"],
        filters["source"],
        filters["start_date"],
        filters["end_date"],
        sort_by,
        sort_order
    )
            
    employees = get_all_employees()
    customers = get_all_customers()

    return render_template("leads.html", 
                         leads=leads,
                         filters=filters,
                         sort_by=sort_by, 
                         sort_order=sort_order,
                         filter_options={
                             "employees": employees, 
                             "customers": customers
                         })

@app.route('/leads/edit/<string:lead_id>', methods=['GET', 'POST'])
# @admin_required
def edit_lead(lead_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM leads WHERE employeeLeadId = ?", (lead_id,))
            lead = cursor.fetchone()

    if not lead:
        flash("Lead not found", "danger")
        return redirect(url_for('leads'))

    if request.method == 'POST':
        form = request.form
        new_emp_id = form['employeeId']
        new_cust_id = form['customerId']
        new_status = form['status']
        new_source = form['source']
        amount_closed = float(form.get('amountClosed', 0))
        prev_amount = float(lead['amountClosed'] or 0)

        old_values = dict(lead)

        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("SELECT achievedAmount FROM employees WHERE empId = ?", (lead['employeeId'],))
                old_emp = cursor.fetchone()
                
                cursor.execute("SELECT empName, phoneNo, achievedAmount FROM employees WHERE empId = ?", (new_emp_id,))
                new_emp = cursor.fetchone()

                cursor.execute("""SELECT customerName, phone, currentLocation, desiredDestination, source, status 
                                FROM customers WHERE customerId = ?""", (new_cust_id,))
                new_cust = cursor.fetchone()

                # Handle amount changes if status is Confirmed
                if lead['employeeId'] != new_emp_id:
                    if lead['status'] == 'Confirmed' and old_emp:
                        new_achieved_old = old_emp['achievedAmount'] - prev_amount
                        cursor.execute("""
                            UPDATE employees
                            SET achievedAmount = ?
                            WHERE empId = ?
                        """, (new_achieved_old, lead['employeeId']))

                    if new_status == 'Confirmed' and new_emp:
                        new_achieved_new = new_emp['achievedAmount'] + amount_closed
                        cursor.execute("""
                            UPDATE employees
                            SET achievedAmount = ?
                            WHERE empId = ?
                        """, (new_achieved_new, new_emp_id))
                else:
                    achieved = new_emp['achievedAmount'] if new_emp else 0
                    if new_status == 'Confirmed':
                        if lead['status'] != 'Confirmed':
                            achieved += amount_closed
                        else:
                            achieved = achieved - prev_amount + amount_closed
                    elif lead['status'] == 'Confirmed':
                        achieved -= prev_amount

                    if new_emp:
                        cursor.execute("UPDATE employees SET achievedAmount = ? WHERE empId = ?", (achieved, new_emp_id))

                cursor.execute("""
                    UPDATE leads
                    SET employeeId = ?, employeeName = ?, employeeContactNo = ?,
                        customerId = ?, customerName = ?, customerContactNo = ?,
                        currentAddress = ?, desiredDestination = ?, source=?,
                        status = ?, 
                        amountClosed = ?, updatedAt = datetime('now')
                    WHERE employeeLeadId = ?
                """, (
                    new_emp_id,
                    new_emp['empName'] if new_emp else lead['employeeName'],
                    new_emp['phoneNo'] if new_emp else lead['employeeContactNo'],
                    new_cust_id,
                    new_cust['customerName'] if new_cust else lead['customerName'],
                    new_cust['phone'] if new_cust else lead['customerContactNo'],
                    form['currentAddress'],
                    form['desiredDestination'],
                    new_source,
                    new_status,
                    amount_closed if new_status == 'Confirmed' else 0,
                    lead_id
                ))

                if new_cust_id:
                    cursor.execute("""
                        UPDATE customers
                        SET status = ?,
                            source = ?,
                            currentLocation = ?,
                            desiredDestination = ?
                        WHERE customerId = ?
                    """, (
                        new_status,
                        new_source,
                        form['currentAddress'],
                        form['desiredDestination'],
                        new_cust_id
                    ))

                conn.commit()

        # Log the update
        lead_employee = lead['employeeId']
        new_values = {
            'employeeId': new_emp_id,
            'customerId': new_cust_id,
            'status': new_status,
            'source': new_source,
            'currentAddress': form['currentAddress'],
            'desiredDestination': form['desiredDestination'],
            'amountClosed': amount_closed if new_status == 'Confirmed' else 0
        }
        
        changes = [f"{key} from '{old_values[key]}' to '{new_values[key]}'" 
                  for key in new_values if old_values[key] != new_values[key]]
        
        description = (f"Updated lead {lead_id}: {', '.join(changes)}" 
                      if changes else f"No changes to lead {lead_id}")
        
        log_change('leads', 'UPDATE', lead_id, description, 
                  old_values=old_values, new_values=new_values,
                  changed_by=session['user_id'],
                  lead_employee=lead_employee)

        flash("Lead and linked customer/employee updated!", "info")
        return redirect(url_for('leads'))

    return render_template('edit_lead.html',
                         lead=dict(lead),
                         employees=get_all_employees(),
                         customers=get_all_customers())

@app.route('/leads/delete/<string:lead_id>')
@login_required
def delete_lead(lead_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("SELECT * FROM leads WHERE employeeLeadId = ?", (lead_id,))
            lead = cursor.fetchone()
            if lead:
                old_values = dict(lead)
                cursor.execute("DELETE FROM leads WHERE employeeLeadId = ?", (lead_id,))
                conn.commit()
                
                # Log the deletion
                description = f"Deleted lead {lead_id}"
                log_change('leads', 'DELETE', lead_id, description, old_values=old_values, changed_by=session['user_id'])
                
                flash("Lead deleted!", "success")
            else:
                flash("Lead not found!", "danger")
    return redirect(url_for('leads'))

@app.route("/leads/create", methods=["GET", "POST"])
# @admin_required
def add_lead():
    employees = get_all_employees()
    customers = get_all_customers()

    if request.method == "POST":
        form = request.form
        lead_id = str(uuid.uuid4())[:8]
        new_values = {
            'employeeLeadId': lead_id,
            'employeeId': form["employeeId"],
            'customerId': form["customerId"],
            'status': form["status"],
            'source': form["source"],
            'currentAddress': form["currentAddress"],
            'desiredDestination': form["desiredDestination"]
        }
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("""
                    INSERT INTO leads (
                        employeeLeadId, employeeId, customerId, status, currentAddress, 
                        desiredDestination, source, createdAt, updatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (
                    lead_id,
                    form["employeeId"],
                    form["customerId"],
                    form["status"],
                    form["currentAddress"],
                    form["desiredDestination"],
                    form["source"]
                ))
                conn.commit()
        
        # Log the insertion
        description = f"Created lead for employee {form['employeeId']} and customer {form['customerId']}"
        log_change('leads', 'INSERT', lead_id, description, new_values=new_values)

        flash("Lead created successfully!")
        return redirect(url_for('leads'))

    return render_template("add_lead.html", employees=employees, customers=customers)

@app.route('/status_tracking', methods=['GET'])
@admin_required
def status_tracking():
    # Get filters from request
    filters = {
        'employee_id': request.args.get('employee_id', ''),
        'start_date': request.args.get('start_date', ''),
        'end_date': request.args.get('end_date', '')
    }

    # Build query for actual status changes (status before != status after)
    query = """
        SELECT 
            strftime('%Y-%m-%d', created_at) AS date,
            json_extract(new_values, '$.status') AS new_status,
            COUNT(*) AS status_count
        FROM logs
        WHERE table_name = 'leads'
          AND action = 'UPDATE'
          AND json_extract(new_values, '$.status') IS NOT json_extract(old_values, '$.status')
    """
    params = []

    if filters['employee_id']:
        query += " AND changed_by = ?"
        params.append(filters['employee_id'])

    if filters['start_date']:
        query += " AND DATE(created_at) >= ?"
        params.append(filters['start_date'])

    if filters['end_date']:
        query += " AND DATE(created_at) <= ?"
        params.append(filters['end_date'])

    query += " GROUP BY date, new_status ORDER BY date"

    # Execute query
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        status_data = cursor.fetchall()

        # Get employees for dropdown
        cursor.execute("SELECT empId, empName FROM employees")
        employees = cursor.fetchall()

    # Prepare data for chart
    chart_data = {}
    for row in status_data:
        date = row['date']
        status = row['new_status']
        count = row['status_count']

        if date not in chart_data:
            chart_data[date] = {}
        chart_data[date][status] = count

    # Generate chart using the updated generate_status_chart function
    chart = generate_status_chart(chart_data)

    return render_template('status_tracking.html',
                           chart_data=chart,  # Pass the processed chart data
                           employees=employees,
                           filters=filters)

@app.route('/status_changes')
@admin_required
def status_changes():
    """Display lead status changes with pie chart visualization."""
    # Get filters from request
    filters = {
        'employee_id': request.args.get('employee_id', ''),
        'start_date': request.args.get('start_date', ''),
        'end_date': request.args.get('end_date', ''),
        'status': request.args.get('status', '')
    }

    # Build query for actual status changes only
    query = """
        SELECT 
            json_extract(new_values, '$.status') AS status,
            COALESCE(lead_employee, changed_by) AS employee_id,
            COUNT(*) AS status_count
        FROM logs
        WHERE table_name = 'leads'
          AND action = 'UPDATE'
          AND json_extract(new_values, '$.status') IS NOT json_extract(old_values, '$.status')
    """
    params = []

    if filters['employee_id']:
        query += " AND (lead_employee = ? OR changed_by = ?)"
        params.extend([filters['employee_id'], filters['employee_id']])

    if filters['status']:
        query += " AND json_extract(new_values, '$.status') = ?"
        params.append(filters['status'])

    if filters['start_date']:
        query += " AND DATE(created_at) >= ?"
        params.append(filters['start_date'])

    if filters['end_date']:
        query += " AND DATE(created_at) <= ?"
        params.append(filters['end_date'])

    query += " GROUP BY status, employee_id"

    # Execute query
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        status_data = cursor.fetchall()

        # Get employee names mapping
        cursor.execute("SELECT empId, empName FROM employees")
        employee_names = {row['empId']: row['empName'] for row in cursor.fetchall()}

        # Get unique statuses for dropdown
        cursor.execute("""
            SELECT DISTINCT json_extract(new_values, '$.status') AS status
            FROM logs
            WHERE table_name = 'leads'
            AND action = 'UPDATE'
            AND json_extract(new_values, '$.status') IS NOT json_extract(old_values, '$.status')
            AND json_extract(new_values, '$.status') IS NOT NULL
        """)
        statuses = [row['status'] for row in cursor.fetchall() if row['status']]

    # Prepare data structures
    from collections import defaultdict
    status_counts = defaultdict(int)
    employee_status_counts = defaultdict(lambda: {'name': '', 'statuses': defaultdict(int)})

    for row in status_data:
        status = row['status']
        employee_id = row['employee_id']
        count = row['status_count']

        status_counts[status] += count

        if employee_id in employee_names:
            employee_status_counts[employee_id]['name'] = employee_names[employee_id]
            employee_status_counts[employee_id]['statuses'][status] += count

    status_counts = dict(status_counts)
    employee_status_counts = dict(employee_status_counts)

    # Generate pie chart
    def generate_pie_chart(status_data):
        if not status_data:
            return "<div class='no-data'>No status changes found for the selected filters</div>"

        import plotly.graph_objects as go

        status_colors = {
            'Pending': '#3498db',        # Blue
            'Contacted': '#f1c40f',      # Yellow
            'Not interested': '#e74c3c', # Red
            'Qoutation': '#6f42c1',      # Purple
            'Group Trip': '#2ecc71',     # Green
            'Refund': '#95a5a6',         # Gray
            'Confirmed': '#27ae60'       # Dark Green
        }

        labels = list(status_data.keys())
        values = list(status_data.values())
        colors = [status_colors.get(status, '#95a5a6') for status in labels]

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            marker_colors=colors,
            hole=0.3,
            textinfo='percent+label',
            hoverinfo='label+value+percent',
            textposition='inside'
        )])

        fig.update_layout(
            title='Status Distribution',
            height=500,
            showlegend=False
        )

        return fig.to_html(full_html=False)

    chart_html = generate_pie_chart(status_counts)

    return render_template('status_changes_pie.html',
                           chart_html=chart_html,
                           employees=list(employee_names.items()),
                           statuses=statuses,
                           filters=filters,
                           status_counts=status_counts,
                           employee_status_counts=employee_status_counts)

@app.route('/dashboard')
@admin_required
def dashboard():
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute('SELECT status, COUNT(*) as count FROM leads GROUP BY status')
            leads_by_status = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute('SELECT source, COUNT(*) as count FROM leads GROUP BY source')
            leads_by_source = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute('''
                SELECT DATE(createdAt) as date, COUNT(*) as count 
                FROM leads 
                GROUP BY DATE(createdAt)
                ORDER BY DATE(createdAt)
            ''')
            leads_by_date = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute('SELECT COUNT(*) FROM customers')
            total_customers = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM employees')
            total_employees = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM leads')
            total_leads = cursor.fetchone()[0]
    
    # Generate chart for leads by status
    status_counts = {row['status']: row['count'] for row in leads_by_status}
    status_colors = {
        'Pending': '#3498db',
        'Contacted': '#f1c40f',
        'Not interested': '#e74c3c',
        'Qoutation': '#6f42c1',
        'Group Trip': '#2ecc71',
        'Refund': '#95a5a6',
        'Confirmed': '#27ae60'
    }

    chart = {
        'type': 'pie',
        'data': {
            'labels': list(status_counts.keys()),
            'datasets': [{
                'data': list(status_counts.values()),
                'backgroundColor': [status_colors.get(status, '#95a5a6') for status in status_counts.keys()]
            }]
        },
        'options': {
            'title': {'display': True, 'text': 'Leads by Status'},
            'legend': {'position': 'right'}
        }
    }

    return render_template("dashboard.html",
                         leads_by_status=leads_by_status,
                         leads_by_source=leads_by_source,
                         leads_by_date=leads_by_date,
                         total_customers=total_customers,
                         total_employees=total_employees,
                         total_leads=total_leads,
                         status_chart=chart)

@app.route('/logs', methods=['GET'])
@admin_required
def logs():
    filters = {
        'table_name': request.args.get('table_name', ''),
        'action': request.args.get('action', ''),
        'start_date': request.args.get('start_date', ''),
        'source': request.args.get('source', ''),
        'end_date': request.args.get('end_date', '')
    }
    
    query = "SELECT * FROM logs WHERE 1=1"
    params = []
    
    if filters['table_name']:
        query += " AND table_name = ?"
        params.append(filters['table_name'])
    if filters['action']:
        query += " AND action = ?"
        params.append(filters['action'])
    if filters['source']:
        query += " AND changed_by = ?"
        params.append(filters['source'])
    if filters['start_date']:
        query += " AND DATE(created_at) >= ?"
        params.append(filters['start_date'])
    if filters['end_date']:
        query += " AND DATE(created_at) <= ?"
        params.append(filters['end_date'])
    
    query += " ORDER BY created_at DESC"
    
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            logs = cursor.fetchall()
            
            # Get distinct values for filters
            cursor.execute("SELECT DISTINCT table_name FROM logs")
            table_names = [row['table_name'] for row in cursor.fetchall()]
            cursor.execute("SELECT DISTINCT action FROM logs")
            actions = [row['action'] for row in cursor.fetchall()]

    return render_template('logs.html',
                         logs=logs,
                         filters=filters,
                         table_names=table_names,
                         actions=actions)

if __name__ == '__main__':
    init_db()
    migrate_db()
    app.run(debug=True)