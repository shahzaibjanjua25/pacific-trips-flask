import sqlite3

try:
    conn = sqlite3.connect('EMS.db', timeout=10)
    cursor = conn.cursor()
    print("before")
    print(cursor.execute("select * from employees"))
    conn = sqlite3.connect('EMS.db', timeout=30000)
    print("after")
    conn.commit()
    conn = sqlite3.connect('EMS.db', timeout=300000)

except sqlite3.OperationalError as e:
    print(f"Error: {e}")
finally:
    conn.close()