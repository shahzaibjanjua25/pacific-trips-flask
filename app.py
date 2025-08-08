from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
import os
import uuid

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# Fix __file__ issue in environments like Jupyter
BASE_DIR = os.getcwd()
DATABASE = os.path.join(BASE_DIR, 'EMS.db')

# -----------------------------
# Database Connection
# -----------------------------
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# -----------------------------
# Utility Functions
# -----------------------------
def get_all_employees():
    conn = get_db_connection()
    employees = conn.execute("SELECT empId, empName FROM employees").fetchall()
    conn.close()
    return employees

def get_all_customers():
    conn = get_db_connection()
    customers = conn.execute("SELECT customerId, customerName FROM customers").fetchall()
    conn.close()
    return customers

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

    conn = get_db_connection()
    leads = conn.execute(query, params).fetchall()
    conn.close()
    return leads

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

    conn = get_db_connection()
    c = conn.cursor()

    c.execute(query, params)
    customers = c.fetchall()

    # For dropdowns
    column_values = {}
    for col in filters:
        c.execute(f"SELECT DISTINCT {col} FROM customers ORDER BY {col}")
        column_values[col] = [row[0] for row in c.fetchall() if row[0]]

    conn.close()

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
        conn = get_db_connection()
        conn.execute('''
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
        conn.close()
        flash("Customer added!", "success")
        return redirect(url_for('customers'))

    return render_template('add_customer.html')

@app.route('/customers/edit/<string:customer_id>', methods=['GET', 'POST'])
def edit_customer(customer_id):
    conn = get_db_connection()
    customer = conn.execute("SELECT * FROM customers WHERE customerId = ?", (customer_id,)).fetchone()

    if not customer:
        flash("Customer not found.", "danger")
        return redirect(url_for('customers'))

    if request.method == 'POST':
        form = request.form
        conn.execute('''
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
        conn.close()
        flash("Customer updated!", "info")
        return redirect(url_for('customers'))

    conn.close()
    return render_template('edit_customer.html', customer=customer)

@app.route('/customers/delete/<string:customer_id>')
def delete_customer(customer_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM customers WHERE customerId = ?", (customer_id,))
    conn.commit()
    conn.close()
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

    conn = get_db_connection()
    employees = conn.execute(query, params).fetchall()

    column_values = {
        'empName': [row['empName'] for row in conn.execute("SELECT DISTINCT empName FROM employees")],
        'phoneNo': [row['phoneNo'] for row in conn.execute("SELECT DISTINCT phoneNo FROM employees")]
    }

    conn.close()

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

        conn = get_db_connection()
        conn.execute('''
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
        conn.close()
        flash("Employee added!", "success")
        return redirect(url_for('employees'))

    return render_template('add_employee.html')

@app.route('/employee/edit/<string:emp_id>', methods=['GET', 'POST'])
def edit_employee(emp_id):
    conn = get_db_connection()
    employee = conn.execute("SELECT * FROM employees WHERE empId = ?", (emp_id,)).fetchone()

    if not employee:
        flash("Employee not found", "danger")
        return redirect(url_for('employees'))

    if request.method == 'POST':
        form = request.form
        conn.execute('''
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
        conn.close()
        flash("Employee updated!", "info")
        return redirect(url_for('employees'))

    conn.close()
    return render_template('edit_employee.html', employee=employee)

@app.route('/employee/delete/<string:emp_id>')
def delete_employee(emp_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM employees WHERE empId = ?", (emp_id,))
    conn.commit()
    conn.close()
    flash("Employee deleted!", "success")
    return redirect(url_for('employees'))

# -----------------------------
# LEADS
# -----------------------------
@app.route('/leads', methods=['GET'])
def leads():
    employee_id = request.args.get('employeeId')
    customer_id = request.args.get('customerId')
    status = request.args.get('status')
    sort_by = request.args.get('sort_by', 'employeeLeadId')
    sort_order = request.args.get('sort_order', 'asc')

    leads = get_filtered_sorted_leads(employee_id, customer_id, status, sort_by, sort_order)
    employees = get_all_employees()
    customers = get_all_customers()

    return render_template("leads.html", leads=leads,
                           filters={"employeeId": employee_id, "customerId": customer_id, "status": status},
                           sort_by=sort_by, sort_order=sort_order,
                           filter_options={"employees": employees, "customers": customers})

@app.route('/leads/add', methods=['GET', 'POST'])
def add_lead():
    if request.method == 'POST':
        form = request.form
        lead_id = str(uuid.uuid4())[:8]

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO leads 
            (employeeLeadId, employeeId, customerId, status, source, currentAddress, desiredDestination, dateSource, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ''', (
            lead_id,
            form['employeeId'],
            form['customerId'],
            form['status'],
            form['source'],
            form['currentAddress'],
            form['desiredDestination'],
            form['dateSource']
        ))
        conn.commit()
        conn.close()
        flash("Lead added!", "success")
        return redirect(url_for('leads'))

    return render_template('add_lead.html', employees=get_all_employees(), customers=get_all_customers())

@app.route('/leads/edit/<string:lead_id>', methods=['GET', 'POST'])
def edit_lead(lead_id):
    conn = get_db_connection()
    lead = conn.execute("SELECT * FROM leads WHERE employeeLeadId = ?", (lead_id,)).fetchone()

    if not lead:
        flash("Lead not found", "danger")
        return redirect(url_for('leads'))

    if request.method == 'POST':
        form = request.form
        conn.execute('''
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
        conn.commit()
        conn.close()
        flash("Lead updated!", "info")
        return redirect(url_for('leads'))

    conn.close()
    return render_template('edit_lead.html', lead=lead, employees=get_all_employees(), customers=get_all_customers())

@app.route('/leads/delete/<string:lead_id>')
def delete_lead(lead_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM leads WHERE employeeLeadId = ?", (lead_id,))
    conn.commit()
    conn.close()
    flash("Lead deleted!", "success")
    return redirect(url_for('leads'))
@app.route("/leads/create", methods=["GET", "POST"])
def create_lead():
    conn = get_db_connection()
    employees = conn.execute("SELECT * FROM employees").fetchall()
    customers = conn.execute("SELECT * FROM customers").fetchall()

    if request.method == "POST":
        employeeId = request.form["employeeId"]
        customerId = request.form["customerId"]
        status = request.form["status"]
        source = request.form["source"]
        currentAddress = request.form["currentAddress"]
        desiredDestination = request.form["desiredDestination"]
        dateSource = request.form["dateSource"]

        conn.execute("""
            INSERT INTO employee_leads (
                employeeId, customerId, status, source, currentAddress, 
                desiredDestination, dateSource, createdAt, updatedAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (employeeId, customerId, status, source, currentAddress, desiredDestination, dateSource))
        conn.commit()
        conn.close()
        flash("Lead created successfully!")
        return redirect(url_for('leads'))

    conn.close()
    return render_template("create_lead.html", employees=employees, customers=customers)

# -----------------------------
# Run App
# -----------------------------
if __name__ == '__main__':
    app.run(debug=True)
