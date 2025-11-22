import requests
import sqlite3
import time

# Constants
API_BASE_URL = "https://api.cfu.ac.ir"
LOGIN_URL = f"{API_BASE_URL}/Login"
FACULTY_URL = f"{API_BASE_URL}/API/Golestan/Faculty"
USERNAME = "khodarahmi"
PASSWORD = "9909177"
DB_NAME = "faculty_data.db"

def login_and_get_token():
    payload = {
        "userName": "khodarahmi",
        "password": "9909177"
    }
    try:
        response = requests.post(LOGIN_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        token = data['data']['token']
        print("[INFO] Token received.")
        return token
    except Exception as e:
        print(f"[ERROR] Login failed: {e}")
        return None

def fetch_faculty_data(token):
    headers = {
        "Authorization": f"Bearer {token}"
    }
    payload = {
        "pageNumber": 1,
        "pageSize": 1000000
    }
    try:
        response = requests.post(FACULTY_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        print(f"[INFO] Received {len(data['data'])} faculty records.")
        return data['data']
    except Exception as e:
        print(f"[ERROR] Failed to fetch faculty data: {e}")
        return []

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY,
            professorCode TEXT,
            name TEXT,
            family TEXT,
            field TEXT,
            code TEXT,
            mobile TEXT,
            nationalcode TEXT UNIQUE,
            email TEXT,
            personelid TEXT UNIQUE,
            code_Markaz TEXT,
            markaz TEXT,
            city TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("[INFO] SQLite table initialized.")

def insert_faculty_records(records):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    inserted_count = 0
    skipped_count = 0

    for rec in records:
        # Validate required fields
        if not rec.get("nationalcode"):
            skipped_count += 1
            continue  # Skip this record if nationalcode is missing

        cur.execute('''
            INSERT OR REPLACE INTO faculty (
                id, professorCode, name, family, field, code, mobile,
                nationalcode, email, personelid, code_Markaz, markaz, city,
                sex, scope, scope_ID, employ_state, employtype,
                employtype_title, estekhdamtype, estekhdamtype_title
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            rec.get("id"),
            rec.get("professorCode"),
            rec.get("name"),
            rec.get("family"),
            rec.get("field"),
            rec.get("code"),
            rec.get("mobile"),
            rec.get("nationalcode"),
            rec.get("email"),
            rec.get("personelid"),
            rec.get("code_Markaz"),
            rec.get("markaz"),
            rec.get("city"),
            rec.get("sex"),
            rec.get("scope"),
            rec.get("scope_ID"),
            rec.get("employ_state"),
            rec.get("employtype"),
            rec.get("employtype_title"),
            rec.get("estekhdamtype"),
            rec.get("estekhdamtype_title")
        ))
        inserted_count += 1

    conn.commit()

    # Province update logic
    cur.execute('''
        UPDATE faculty
        SET province_code = (
            SELECT p.province_code
            FROM province p
            WHERE faculty.scope LIKE '%' || p.province_name || '%'
            ORDER BY LENGTH(p.province_name) DESC
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM province p
            WHERE faculty.scope LIKE '%' || p.province_name || '%'
        )
    ''')

    conn.commit()
    conn.close()

    print(f"[INFO] {inserted_count} faculty records inserted/updated.")
    print(f"[INFO] {skipped_count} records skipped due to missing nationalcode.")

def main():
    print("[INFO] Starting service...")
    init_db()
    token = login_and_get_token()
    if token:
        faculty_data = fetch_faculty_data(token)
        if faculty_data:
            insert_faculty_records(faculty_data)
    print("[INFO] Done.")

def get_faculty_details_by_markaz(markaz_name):
    import sqlite3
    DB_PATH2 = "C:\\services\\cert2\\app\\fetch_data\\faculty_data.db"
    conn = sqlite3.connect(DB_PATH2)
    cursor = conn.cursor()

    query = """
    SELECT name, family, sex, field, mobile, email, markaz, city, scope, employ_state, estekhdamtype_title
    FROM faculty
    WHERE markaz = ?
    ORDER BY sex, name, family
    """
    cursor.execute(query, (markaz_name,))
    rows = cursor.fetchall()
    conn.close()

    return [
        {
            "row_num": idx + 1,
            "name": row[0],
            "family": row[1],
            "sex": row[2],
            "field": row[3],
            "mobile": row[4],
            "email": row[5],
            "markaz": row[6],
            "city": row[7],
            "scope": row[8],
            "employ_state": row[9],
            "estekhdamtype_title": row[10]
        }
        for idx, row in enumerate(rows)
    ]


if __name__ == "__main__":
    main()
