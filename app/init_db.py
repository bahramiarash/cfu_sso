import sqlite3
import os


base_dir = os.path.dirname(__file__)
db_path = os.path.join(base_dir, 'access_control.db')  # now in C:\services\cert2\app

# Create directory if needed
os.makedirs(os.path.dirname(db_path), exist_ok=True)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Drop tables if they exist
cursor.execute("DROP TABLE IF EXISTS role_dashboard")
cursor.execute("DROP TABLE IF EXISTS dashboards")
cursor.execute("DROP TABLE IF EXISTS roles")

# Create roles table
cursor.execute("""
CREATE TABLE roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
)
""")

# Create dashboards table
cursor.execute("""
CREATE TABLE dashboards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dashboard_id TEXT UNIQUE NOT NULL
)
""")

# Create mapping table
cursor.execute("""
CREATE TABLE role_dashboard (
    role_id INTEGER,
    dashboard_id INTEGER,
    FOREIGN KEY(role_id) REFERENCES roles(id),
    FOREIGN KEY(dashboard_id) REFERENCES dashboards(id)
)
""")

# Insert roles
roles = ['manager', 'analytics_team', 'staff']
for role in roles:
    cursor.execute("INSERT INTO roles (name) VALUES (?)", (role,))

# Insert dashboards
dashboard_ids = [
    'sales_summary',
    'team_performance',
    'full_data_insights',
    'etl_logs',
    'model_metrics'
]
for d in dashboard_ids:
    cursor.execute("INSERT INTO dashboards (dashboard_id) VALUES (?)", (d,))

# Assign dashboards to roles
def assign(role, dashboards):
    cursor.execute("SELECT id FROM roles WHERE name=?", (role,))
    role_id = cursor.fetchone()[0]
    for dash in dashboards:
        cursor.execute("SELECT id FROM dashboards WHERE dashboard_id=?", (dash,))
        dash_id = cursor.fetchone()[0]
        cursor.execute("INSERT INTO role_dashboard (role_id, dashboard_id) VALUES (?, ?)", (role_id, dash_id))

assign('manager', ['sales_summary', 'team_performance'])
assign('analytics_team', ['full_data_insights', 'etl_logs', 'model_metrics'])
assign('staff', dashboard_ids)  # staff gets access to all

conn.commit()
conn.close()

print(f"Database created at: {db_path}")
