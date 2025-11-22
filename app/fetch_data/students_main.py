import requests
import sqlite3
import time

# --- Configuration ---
LOGIN_URL = "https://api.cfu.ac.ir/Login"
STUDENTS_URL = "https://api.cfu.ac.ir/API/Golestan/Students_2"
USERNAME = "khodarahmi"
PASSWORD = "9909177"
DATABASE_FILE = "faculty_data.db"  # Change to your SQLite database path

# --- Step 1: Login and Get Token ---
def get_token():
    response = requests.post(LOGIN_URL, json={"userName": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    return response.json()["data"]["token"]

# --- Step 2: Connect to SQLite and get pardis_code values ---
def get_pardis_codes(cursor):
    import sqlite3
    DB_PATH2 = "C:\\services\\cert2\\app\\access_control.db"
    conn2 = sqlite3.connect(DB_PATH2)
    cursor2 = conn2.cursor()    
    cursor2.execute("SELECT pardis_code FROM pardis")
    return [row[0] for row in cursor2.fetchall()]

# --- Step 3: Generate all valid term codes ---
def generate_term_codes(start_year=1400, end_year=1404):
    term_codes = []
    for year in range(start_year, end_year + 1):
        base = int(str(year)[-3:])  # e.g., 1402 -> 402
        for term in range(1, 4):
            term_codes.append(f"{base}{term}")
    return term_codes

# --- Step 4: Create Students table if not exists ---
def create_students_table(cursor):
    cursor.execute("""
        CREATE TABLE Students (
            studentnum TEXT PRIMARY KEY,
            firstname TEXT,
            familyname TEXT,
            firstnameeng TEXT,
            familynameeng TEXT,
            fathername TEXT,
            codvaziayat TEXT,
            vazeiyat TEXT,
            birthdate TEXT,
            birthplace TEXT,
            city TEXT,
            address TEXT,
            phonenum TEXT,
            email TEXT,
            sex TEXT,
            course TEXT,
            course_name TEXT,
            grade TEXT,
            gradname TEXT,
            degsdate TEXT,
            last_degree TEXT,
            uniname TEXT,
            sub_uniname TEXT,
            sub_num TEXT, 
            province_code INTEGER, 
            code_Markaz INTEGER, 
            province TEXT, 
            term TEXT)
    """)

# --- Step 5: Insert data into Students table ---
def insert_students(cursor, students):
    print("Students count:", len(students))
    for student in students:
        try:
            student['province_code']=student['provinceCode']
            cursor.execute("""
            INSERT OR IGNORE INTO Students VALUES (
                :studentnum, :firstname, :familyname, :firstnameeng, :familynameeng,
                :fathername, :codvaziayat, :vazeiyat, :birthdate, :birthplace,
                :city, :address, :phonenum, :email, :sex, :course, :course_name,
                :grade, :gradname, :degsdate, :last_degree, :uniname,
                :sub_uniname, :sub_num,
                :code_Markaz, 
                :province, 
                :term, :province_code
            )
            """, student)
        except Exception as e:
            print(f"Insert error for student {student.get('studentnum', 'unknown')}: {e}")

# --- Step 6: Fetch students for a pardis and term ---
def fetch_students(token, code_pardis, term):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "codePardis": str(code_pardis),  # Ensure it's a string
        "term": str(term),               # Also keep term as string
        "paging": {
            "pageNumber": 1,
            "pageSize": 1000000
        },
        "Filter": {}  # Include empty Filter field if no filters needed
    }

    try:
        print(f"Sending request for pardis: {code_pardis}, term: {term}")
        response = requests.post(STUDENTS_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response.json().get("data", [])
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error for pardis {code_pardis}, term {term}: {http_err}")
        print(f"Response content: {response.text}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


# --- Main Routine ---
def main():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # Prepare DB
    # create_students_table(cursor)

    # Login
    token = get_token()

    # Fetch pardis codes and terms
    pardis_codes = get_pardis_codes(cursor)
    term_codes = generate_term_codes()

    # Fetch and insert students
    for code_pardis in pardis_codes:
        for term in term_codes:
            print(f"Fetching for Pardis {code_pardis}, Term {term}...")
            students = fetch_students(token, code_pardis, term)
            if students:
                insert_students(cursor, students)
                conn.commit()
            time.sleep(1)  # Avoid hammering the API

    conn.close()
    print("All done.")

if __name__ == "__main__":
    main()
