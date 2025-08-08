from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
import uuid
from contextlib import closing

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# Database Configuration
BASE_DIR = os.getcwd()
DATABASE = os.path.join(BASE_DIR, 'EMS.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE, timeout=10)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

# -----------------------------
# Utility Functions
# -----------------------------
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

def get_filtered_sorted_leads(employee_id, customer_id, status, sort_by, sort_order):
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
        query += ' AND leads.status = ?'
        params.append(status)

    query += f' ORDER BY {sort_by} {sort_order.upper()}'

    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

# -----------------------------
# Home Page
# -----------------------------
@app.route('/')
def index():
    return render_template('base.html')

# -----------------------------
# CUSTOMERS
# -----------------------------
@app.route('/customers')
def customers():
    filters = {
        "customerName": request.args.get("name", ""),
        "phone": request.args.get("phone", ""),
        "source": request.args.get("source", ""),
        "currentLocation": request.args.get("currentLocation", ""),
        "desiredDestination": request.args.get("desiredDestination", "")
    }

    sort_by = request.args.get("sort_by", "customerName")
    sort_order = request.args.get("sort_order", "asc")

    query = "SELECT * FROM customers WHERE 1=1"
    params = []

    for col, val in filters.items():
        if val:
            query += f" AND {col} = ?"
            params.append(val)

    query += f" ORDER BY {sort_by} {sort_order.upper()}"

    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            customers = cursor.fetchall()

            # For dropdowns
            column_values = {}
            for col in filters:
                cursor.execute(f"SELECT DISTINCT {col} FROM customers ORDER BY {col}")
                column_values[col] = [row[0] for row in cursor.fetchall() if row[0]]

    return render_template("customers.html",
                         customers=customers,
                         filters=filters,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         column_values=column_values)

@app.route('/add_customer', methods=['GET', 'POST'])
def add_customer():
    if request.method == 'POST':
        new_id = str(uuid.uuid4())[:8]
        form = request.form
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute('''
                    INSERT INTO customers 
                    (customerId, customerName, phone, source, currentLocation, desiredDestination, dateOfArrival)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    new_id,
                    form['customerName'],
                    form['phone'],
                    form['source'],
                    form['currentLocation'],
                    form['desiredDestination'],
                    form['dateOfArrival']
                ))
                conn.commit()
        flash("Customer added!", "success")
        return redirect(url_for('customers'))

    return render_template('add_customer.html')

@app.route('/customers/edit/<string:customer_id>', methods=['GET', 'POST'])
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
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute('''
                    UPDATE customers
                    SET customerName = ?, phone = ?, source = ?, currentLocation = ?, 
                        desiredDestination = ?, dateOfArrival = ?
                    WHERE customerId = ?
                ''', (
                    form['customerName'],
                    form['phone'],
                    form['source'],
                    form['currentLocation'],
                    form['desiredDestination'],
                    form['dateOfArrival'],
                    customer_id
                ))
                conn.commit()
        flash("Customer updated!", "info")
        return redirect(url_for('customers'))

    return render_template('edit_customer.html', customer=customer)

@app.route('/customers/delete/<string:customer_id>')
def delete_customer(customer_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM customers WHERE customerId = ?", (customer_id,))
            conn.commit()
    flash("Customer deleted!", "success")
    return redirect(url_for('customers'))

# -----------------------------
# EMPLOYEES
# -----------------------------
@app.route('/employees')
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
def add_employee():
    if request.method == 'POST':
        empId = str(uuid.uuid4())[:8]
        form = request.form
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
        flash("Employee added!", "success")
        return redirect(url_for('employees'))

    return render_template('add_employee.html')

@app.route('/employee/edit/<string:emp_id>', methods=['GET', 'POST'])
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
        flash("Employee updated!", "info")
        return redirect(url_for('employees'))

    return render_template('edit_employee.html', employee=employee)

@app.route('/employee/delete/<string:emp_id>')
def delete_employee(emp_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM employees WHERE empId = ?", (emp_id,))
            conn.commit()
    flash("Employee deleted!", "success")
    return redirect(url_for('employees'))

# -----------------------------
# LEADS
# -----------------------------
@app.route('/leads', methods=['GET'])
def leads():
    filters = {
        "employeeId": request.args.get('employeeId'),
        "customerId": request.args.get('customerId'),
        "status": request.args.get('status'),
        "source": request.args.get('source')
    }
    
    sort_by = request.args.get('sort_by', 'employeeLeadId')
    sort_order = request.args.get('sort_order', 'asc')

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

    if filters["employeeId"]:
        query += ' AND leads.employeeId = ?'
        params.append(filters["employeeId"])
    if filters["customerId"]:
        query += ' AND leads.customerId = ?'
        params.append(filters["customerId"])
    if filters["status"]:
        query += ' AND leads.status = ?'
        params.append(filters["status"])
    if filters["source"]:
        query += ' AND leads.source LIKE ?'
        params.append(f'%{filters["source"]}%')

    query += f' ORDER BY {sort_by} {sort_order.upper()}'

    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            leads = cursor.fetchall()
            
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

@app.route('/leads/add', methods=['GET', 'POST'])
def add_lead():
    if request.method == 'POST':
        form = request.form
        lead_id = str(uuid.uuid4())[:8]
        
        # Get all required related data
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                # Get employee details
                cursor.execute("SELECT empName, phoneNo FROM employees WHERE empId = ?", 
                             (form['employeeId'],))
                employee = cursor.fetchone()
                if not employee:
                    flash("Employee not found!", "danger")
                    return redirect(url_for('add_lead'))
                
                # Get customer details
                cursor.execute("SELECT customerName, phone FROM customers WHERE customerId = ?", 
                             (form['customerId'],))
                customer = cursor.fetchone()
                if not customer:
                    flash("Customer not found!", "danger")
                    return redirect(url_for('add_lead'))
                
                # Insert with all required fields
                cursor.execute('''
                    INSERT INTO leads 
                    (employeeLeadId, employeeId, employeeName, employeeContactNo,
                     customerId, customerName, customerContactNo, status, source,
                     currentAddress, desiredDestination, dateSource,
                     createdAt, updatedAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ''', (
                    lead_id,
                    form['employeeId'],
                    employee['empName'],
                    employee['phoneNo'],
                    form['customerId'],
                    customer['customerName'],
                    customer['phone'],
                    form['status'],
                    form['source'],
                    form['currentAddress'],
                    form['desiredDestination'],
                    form['dateSource']
                ))
                conn.commit()
        
        flash("Lead added successfully!", "success")
        return redirect(url_for('leads'))

    return render_template('add_lead.html', 
                         employees=get_all_employees(), 
                         customers=get_all_customers())

@app.route('/leads/edit/<string:lead_id>', methods=['GET', 'POST'])
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
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                # 🟢 Update Lead
                cursor.execute('''
                    UPDATE leads
                    SET employeeId = ?, customerId = ?, status = ?, source = ?, 
                        currentAddress = ?, desiredDestination = ?, dateSource = ?, updatedAt = datetime('now')
                    WHERE employeeLeadId = ?
                ''', (
                    form['employeeId'],
                    form['customerId'],
                    form['status'],
                    form['source'],
                    form['currentAddress'],
                    form['desiredDestination'],
                    form['dateSource'],
                    lead_id
                ))

                # 🔄 Update Customer Table (sync fields)
                cursor.execute('''
                    UPDATE customers
                    SET source = ?, 
                        currentLocation = ?, 
                        desiredDestination = ?, 
                        updatedAt = datetime('now')
                    WHERE customerId = ?
                ''', (
                    form['source'],
                    form['currentAddress'],
                    form['desiredDestination'],
                    form['customerId']
                ))

                conn.commit()

        flash("Lead and related customer updated!", "info")
        return redirect(url_for('leads'))

    return render_template('edit_lead.html', lead=lead, employees=get_all_employees(), customers=get_all_customers())


@app.route('/leads/delete/<string:lead_id>')
def delete_lead(lead_id):
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM leads WHERE employeeLeadId = ?", (lead_id,))
            conn.commit()
    flash("Lead deleted!", "success")
    return redirect(url_for('leads'))

@app.route("/leads/create", methods=["GET", "POST"])
def create_lead():
    employees = get_all_employees()
    customers = get_all_customers()

    if request.method == "POST":
        with closing(get_db_connection()) as conn:
            with closing(conn.cursor()) as cursor:
                cursor.execute("""
                    INSERT INTO employee_leads (
                        employeeId, customerId, status, source, currentAddress, 
                        desiredDestination, dateSource, createdAt, updatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (
                    request.form["employeeId"],
                    request.form["customerId"],
                    request.form["status"],
                    request.form["source"],
                    request.form["currentAddress"],
                    request.form["desiredDestination"],
                    request.form["dateSource"]
                ))
                conn.commit()
        flash("Lead created successfully!")
        return redirect(url_for('leads'))

    return render_template("create_lead.html", employees=employees, customers=customers)

@app.route('/dashboard')
def dashboard():
    with closing(get_db_connection()) as conn:
        with closing(conn.cursor()) as cursor:
            # Get leads by status (convert Row to dict)
            cursor.execute('SELECT status, COUNT(*) as count FROM leads GROUP BY status')
            leads_by_status = [dict(row) for row in cursor.fetchall()]
            
            # Get leads by source (convert Row to dict)
            cursor.execute('SELECT source, COUNT(*) as count FROM leads GROUP BY source')
            leads_by_source = [dict(row) for row in cursor.fetchall()]
            
            # Get leads by date (convert Row to dict)
            cursor.execute('''
                SELECT DATE(createdAt) as date, COUNT(*) as count 
                FROM leads 
                GROUP BY DATE(createdAt)
                ORDER BY DATE(createdAt)
            ''')
            leads_by_date = [dict(row) for row in cursor.fetchall()]
            
            # Get total counts
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
                         total_leads=total_leads)

# -----------------------------
# Run App
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)