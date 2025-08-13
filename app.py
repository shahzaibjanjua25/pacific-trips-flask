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
app.secret_key = 'your-secret-key'  # Replace with a secure key in production

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
                achievedAmount REAL,
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
                amountClosed REAL,
                createdAt TEXT DEFAULT CURRENT_TIMESTAMP,
                updatedAt TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (employeeId) REFERENCES employees(empId),
                FOREIGN KEY (customerId) REFERENCES customers(customerId)
            )
        ''')
        # Create logs table
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
        cursor = conn.cursor()
        cursor.execute("SELECT empId, empName FROM employees")
        return [{'empId': row['empId'], 'empName': row['empName']} for row in cursor.fetchall()]

def get_all_customers():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT customerId, customerName FROM customers")
        return [{'customerId': row['customerId'], 'customerName': row['customerName']} for row in cursor.fetchall()]

def get_employee_details(emp_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE empId = ?", (emp_id,))
        return cursor.fetchone()

def log_change(table_name, action, record_id, description, old_values=None, new_values=None, changed_by=None, lead_employee=None):
    log_id = str(uuid.uuid4())[:8]
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
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

# Authentication Middleware
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
            cursor = conn.cursor()
            cursor.execute("SELECT empId, empName FROM employees WHERE empId = ?", (employee_id,))
            employee = cursor.fetchone()
            
            if not employee:
                flash('Invalid Employee ID.', 'danger')
                return redirect(url_for('register'))
            
            cursor.execute("SELECT employeeId FROM users WHERE employeeId = ?", (employee_id,))
            if cursor.fetchone():
                flash('Employee ID already registered.', 'danger')
                return redirect(url_for('register'))
            
            password_hash = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (employeeId, password_hash, role)
                VALUES (?, ?, 'employee')
            ''', (employee_id, password_hash))
            conn.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html', current_year=datetime.now().year)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        employee_id = request.form['employeeId']
        password = request.form['password']
        
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
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
    
    return render_template('login.html', current_year=datetime.now().year)

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
    return render_template('base.html', current_year=datetime.now().year)

@app.route('/profile')
@employee_required
def profile():
    employee = get_employee_details(session['user_id'])
    if not employee:
        flash('Employee details not found.', 'danger')
        return redirect(url_for('index'))
    return render_template('profile.html', employee=employee, current_year=datetime.now().year)

@app.route('/customers')
@admin_required
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
        cursor = conn.cursor()
        cursor.execute(query, params)
        customers = cursor.fetchall()

        column_values = {}
        for col in filters:
            if col not in ["start_date", "end_date"]:
                cursor.execute(f"SELECT DISTINCT {col} FROM customers ORDER BY {col}")
                column_values[col] = [row[0] for row in cursor.fetchall() if row[0]]
            else:
                column_values[col] = []

    return render_template("customers.html",
                         customers=customers,
                         filters=filters,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         column_values=column_values,
                         current_year=datetime.now().year)

@app.route('/add_customer', methods=['GET', 'POST'])
@admin_required
def add_customer():
    if request.method == 'POST':
        new_id = str(uuid.uuid4())[:8]
        form = request.form
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
        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
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
            conn.commit()
        
        description = f"Added customer {form['customerName']} with ID {new_id}"
        log_change('customers', 'INSERT', new_id, description, new_values=new_values, changed_by=session['user_id'])
        
        flash("Customer added!", "success")
        return redirect(url_for('customers'))

    return render_template('add_customer.html', current_year=datetime.now().year)

@app.route('/customers/edit/<string:customer_id>', methods=['GET', 'POST'])
@admin_required
def edit_customer(customer_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE customerId = ?", (customer_id,))
        customer = cursor.fetchone()

    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for('customers'))

    if request.method == 'POST':
        form = request.form
        old_values = dict(customer)
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
            cursor = conn.cursor()
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

        changes = [f"{key} from '{old_values[key]}' to '{new_values[key]}'" for key in new_values if old_values[key] != new_values[key]]
        description = f"Updated customer {form['customerName']} (ID: {customer_id}): {', '.join(changes)}" if changes else f"No changes to customer {form['customerName']} (ID: {customer_id})"
        log_change('customers', 'UPDATE', customer_id, description, old_values=old_values, new_values=new_values, changed_by=session['user_id'])

        flash("Customer and related leads updated!", "info")
        return redirect(url_for('customers'))

    return render_template('edit_customer.html', customer=customer, current_year=datetime.now().year)

@app.route('/customers/delete/<string:customer_id>')
@admin_required
def delete_customer(customer_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE customerId = ?", (customer_id,))
        customer = cursor.fetchone()
        if customer:
            old_values = dict(customer)
            cursor.execute("DELETE FROM customers WHERE customerId = ?", (customer_id,))
            conn.commit()
            
            description = f"Deleted customer {customer['customerName']} (ID: {customer_id})"
            log_change('customers', 'DELETE', customer_id, description, old_values=old_values, changed_by=session['user_id'])
            
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
        cursor = conn.cursor()
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
                         column_values=column_values,
                         current_year=datetime.now().year)

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
            cursor = conn.cursor()
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
        
        description = f"Added employee {form['empName']} with ID {empId}"
        log_change('employees', 'INSERT', empId, description, new_values=new_values, changed_by=session['user_id'])
        
        flash(f"Employee added! ID: {empId}", "success")
        return redirect(url_for('employees'))

    preview_emp_id = str(uuid.uuid4())[:8]
    return render_template('add_employee.html', empId=preview_emp_id, current_year=datetime.now().year)

@app.route('/employee/edit/<string:emp_id>', methods=['GET', 'POST'])
@admin_required
def edit_employee(emp_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
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
            cursor = conn.cursor()
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
        
        changes = [f"{key} from '{old_values[key]}' to '{new_values[key]}'" for key in new_values if old_values[key] != new_values[key]]
        description = f"Updated employee {form['empName']} (ID: {emp_id}): {', '.join(changes)}" if changes else f"No changes to employee {form['empName']} (ID: {emp_id})"
        log_change('employees', 'UPDATE', emp_id, description, old_values=old_values, new_values=new_values, changed_by=session['user_id'])
        
        flash("Employee updated!", "info")
        return redirect(url_for('employees'))

    return render_template('edit_employee.html', employee=employee, current_year=datetime.now().year)

@app.route('/employee/delete/<string:emp_id>')
@admin_required
def delete_employee(emp_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM employees WHERE empId = ?", (emp_id,))
        employee = cursor.fetchone()
        if employee:
            old_values = dict(employee)
            cursor.execute("DELETE FROM employees WHERE empId = ?", (emp_id,))
            conn.commit()
            
            description = f"Deleted employee {employee['empName']} (ID: {emp_id})"
            log_change('employees', 'DELETE', emp_id, description, old_values=old_values, changed_by=session['user_id'])
            
            flash("Employee deleted!", "success")
        else:
            flash("Employee not found!", "danger")
    return redirect(url_for('employees'))

@app.route('/leads', methods=['GET'])
@login_required
def leads():
    # Get filter and sort parameters
    employee_id_filter = request.args.get('employeeId', '')
    customer_id_filter = request.args.get('customerId', '')
    status_filter = request.args.get('status', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    sort_by = request.args.get('sort_by', 'createdAt')
    sort_order = request.args.get('sort_order', 'desc')

    # Validate sort_by to prevent SQL injection
    valid_columns = ['employeeLeadId', 'employeeId', 'empName', 'customerId', 'customerName', 
                     'status', 'currentAddress', 'desiredDestination', 'source', 'createdAt', 'updatedAt', 'amountClosed']
    if sort_by not in valid_columns:
        sort_by = 'createdAt'
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    # Map sort_by to qualified column names
    sort_column_map = {
        'employeeLeadId': 'l.employeeLeadId',
        'employeeId': 'l.employeeId',
        'empName': 'e.empName',
        'customerId': 'l.customerId',
        'customerName': 'c.customerName',
        'status': 'l.status',
        'currentAddress': 'l.currentAddress',
        'desiredDestination': 'l.desiredDestination',
        'source': 'l.source',
        'createdAt': 'l.createdAt',
        'updatedAt': 'l.updatedAt',
        'amountClosed': 'l.amountClosed'
    }

    # Build SQL query
    query = '''
        SELECT l.employeeLeadId, l.employeeId, e.empName, l.customerId, c.customerName, 
               l.status, l.currentAddress, l.desiredDestination, l.source, 
               l.createdAt, l.updatedAt, l.amountClosed
        FROM leads l
        JOIN employees e ON l.employeeId = e.empId
        JOIN customers c ON l.customerId = c.customerId
        WHERE 1=1
    '''
    params = []

    # Apply employee-specific filter for non-admin users
    if session.get('role') == 'employee':
        query += ' AND l.employeeId = ?'
        params.append(session['user_id'])

    # Apply optional filters
    if employee_id_filter:
        query += ' AND l.employeeId = ?'
        params.append(employee_id_filter)
    if customer_id_filter:
        query += ' AND l.customerId = ?'
        params.append(customer_id_filter)
    if status_filter:
        query += ' AND l.status = ?'
        params.append(status_filter)
    if start_date:
        query += ' AND l.createdAt >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND l.createdAt <= ?'
        params.append(end_date + ' 23:59:59')

    # Add sorting with qualified column name
    query += f' ORDER BY {sort_column_map[sort_by]} {sort_order}'

    # Execute query
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        leads = cursor.fetchall()

    # Get filter options
    filter_options = {
        'employees': get_all_employees(),
        'customers': get_all_customers()
    }

    # Pass data to template
    return render_template(
        'leads.html',
        leads=leads,
        filter_options=filter_options,
        filters={
            'employeeId': employee_id_filter,
            'customerId': customer_id_filter,
            'status': status_filter,
            'start_date': start_date,
            'end_date': end_date
        },
        sort_by=sort_by,
        sort_order=sort_order,
        current_year=datetime.now().year
    )

@app.route('/leads/add', methods=['GET', 'POST'])
@login_required
def add_lead():
    if request.method == 'POST':
        form = request.form
        lead_id = str(uuid.uuid4())[:8]
        amount_closed = float(form.get('amountClosed', 0))
        customer_id = form['customerId']

        with closing(get_db_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM leads WHERE customerId = ?", (customer_id,))
            count = cursor.fetchone()[0]

            if count > 0:
                flash("This customer is already assigned to another lead!", "danger")
                return redirect(url_for('add_lead'))

            cursor.execute("""
                SELECT empId, empName, phoneNo, achievedAmount 
                FROM employees 
                WHERE empId = ?
            """, (form['employeeId'],))
            employee = cursor.fetchone()
            if not employee:
                flash("Employee not found!", "danger")
                return redirect(url_for('add_lead'))

            cursor.execute("""
                SELECT customerId, customerName, phone, currentLocation, desiredDestination, source
                FROM customers
                WHERE customerId = ?
            """, (customer_id,))
            customer = cursor.fetchone()
            if not customer:
                flash("Customer not found!", "danger")
                return redirect(url_for('add_lead'))

            if form['status'] == 'Confirmed' and amount_closed > 0:
                new_achieved = employee['achievedAmount'] + amount_closed
                cursor.execute("""
                    UPDATE employees 
                    SET achievedAmount = ?
                    WHERE empId = ?
                """, (new_achieved, employee['empId']))

            cursor.execute("""
                INSERT INTO leads (
                    employeeLeadId, employeeId, employeeName, employeeContactNo,
                    customerId, customerName, customerContactNo,
                    currentAddress, desiredDestination, status, source, amountClosed,
                    createdAt, updatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (
                lead_id,
                employee['empId'],
                employee['empName'],
                employee['phoneNo'],
                customer['customerId'],
                customer['customerName'],
                customer['phone'],
                customer['currentLocation'],
                customer['desiredDestination'],
                form['status'],
                customer['source'],
                amount_closed if form['status'] == 'Confirmed' else 0
            ))

            conn.commit()

        new_values = {
            'employeeLeadId': lead_id,
            'employeeId': form['employeeId'],
            'customerId': form['customerId'],
            'status': form['status'],
            'source': customer['source'],
            'currentAddress': customer['currentLocation'],
            'desiredDestination': customer['desiredDestination'],
            'amountClosed': amount_closed if form['status'] == 'Confirmed' else 0
        }
        description = f"Added lead {lead_id} for employee {employee['empName']} and customer {customer['customerName']}"
        log_change('leads', 'INSERT', lead_id, description, new_values=new_values, changed_by=session['user_id'])

        flash("Lead added successfully!", "success")
        return redirect(url_for('leads'))

    return render_template('add_lead.html',
                           employees=get_all_employees(),
                           customers=get_all_customers(),
                           current_year=datetime.now().year)

@app.route('/leads/edit/<string:lead_id>', methods=['GET', 'POST'])
@login_required
def edit_lead(lead_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
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
            cursor = conn.cursor()
            cursor.execute("SELECT achievedAmount FROM employees WHERE empId = ?", (lead['employeeId'],))
            old_emp = cursor.fetchone()
            
            cursor.execute("SELECT empName, phoneNo, achievedAmount FROM employees WHERE empId = ?", (new_emp_id,))
            new_emp = cursor.fetchone()

            cursor.execute("""SELECT customerName, phone, currentLocation, desiredDestination, source, status 
                            FROM customers WHERE customerId = ?""", (new_cust_id,))
            new_cust = cursor.fetchone()

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
                    currentAddress = ?, desiredDestination = ?, source = ?,
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
                         customers=get_all_customers(),
                         current_year=datetime.now().year)

@app.route('/leads/delete/<string:lead_id>')
@login_required
def delete_lead(lead_id):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM leads WHERE employeeLeadId = ?", (lead_id,))
        lead = cursor.fetchone()
        if lead:
            old_values = dict(lead)
            cursor.execute("DELETE FROM leads WHERE employeeLeadId = ?", (lead_id,))
            conn.commit()
            
            description = f"Deleted lead {lead_id}"
            log_change('leads', 'DELETE', lead_id, description, old_values=old_values, changed_by=session['user_id'])
            
            flash("Lead deleted!", "success")
        else:
            flash("Lead not found!", "danger")
    return redirect(url_for('leads'))

@app.route('/status_changes')
@admin_required
def status_changes():
    filters = {
        'employee_id': request.args.get('employee_id', ''),
        'start_date': request.args.get('start_date', ''),
        'end_date': request.args.get('end_date', ''),
        'status': request.args.get('status', '')
    }

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

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        status_data = cursor.fetchall()

        cursor.execute("SELECT empId, empName FROM employees")
        employee_names = {row['empId']: row['empName'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT DISTINCT json_extract(new_values, '$.status') AS status
            FROM logs
            WHERE table_name = 'leads'
            AND action = 'UPDATE'
            AND json_extract(new_values, '$.status') IS NOT json_extract(old_values, '$.status')
            AND json_extract(new_values, '$.status') IS NOT NULL
        """)
        statuses = [row['status'] for row in cursor.fetchall() if row['status']]

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

    return render_template('status_changes.html',
                           employees=list(employee_names.items()),
                           statuses=statuses,
                           filters=filters,
                           status_counts=status_counts,
                           employee_status_counts=employee_status_counts,
                           current_year=datetime.now().year)

@app.route('/dashboard')
@admin_required
def dashboard():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
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
    
    return render_template("dashboard.html",
                         leads_by_status=leads_by_status,
                         leads_by_source=leads_by_source,
                         leads_by_date=leads_by_date,
                         total_customers=total_customers,
                         total_employees=total_employees,
                         total_leads=total_leads,
                         current_year=datetime.now().year)

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
        cursor = conn.cursor()
        cursor.execute(query, params)
        logs = cursor.fetchall()
        
        cursor.execute("SELECT DISTINCT table_name FROM logs")
        table_names = [row['table_name'] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT action FROM logs")
        actions = [row['action'] for row in cursor.fetchall()]
    
    return render_template('logs.html',
                         logs=logs,
                         filters=filters,
                         table_names=table_names,
                         actions=actions,
                         current_year=datetime.now().year)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)