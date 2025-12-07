"""
Direct test of API with actual values from database
"""
import requests
import sqlite3
import os
import json

# Configuration
API_BASE_URL = "https://api.cfu.ac.ir"
LOGIN_URL = f"{API_BASE_URL}/Login"
STUDENTS_URL = f"{API_BASE_URL}/API/Golestan/Students_2"
USERNAME = "khodarahmi"
PASSWORD = "9909177"  # This should match what's in the database

# Get pardis code from database
db_path = os.path.join("app", "access_control.db")
test_pardis = "1110"
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT pardis_code FROM pardis LIMIT 1")
        row = cursor.fetchone()
        if row:
            test_pardis = str(row[0])
        conn.close()
        print(f"Using pardis_code: {test_pardis}")
    except Exception as e:
        print(f"Error reading DB: {e}")

# Test login
print("\n1. Testing login...")
login_payload = {
    "userName": USERNAME,
    "password": PASSWORD
}

try:
    response = requests.post(LOGIN_URL, json=login_payload, timeout=10)
    response.raise_for_status()
    data = response.json()
    token = data['data']['token']
    print("OK: Login successful")
except Exception as e:
    print(f"ERROR: Login failed: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"Response: {e.response.text}")
    exit(1)

# Test endpoint with exact payload structure
print("\n2. Testing endpoint with exact payload...")
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

test_payload = {
    "codePardis": str(test_pardis).strip(),
    "term": "4041",
    "paging": {
        "pageNumber": 1,
        "pageSize": 1
    },
    "Filter": {}
}

print(f"Payload: {json.dumps(test_payload, indent=2)}")
print(f"Headers: {headers}")

try:
    response = requests.post(STUDENTS_URL, json=test_payload, headers=headers, timeout=10)
    print(f"\nResponse Status: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        print("OK: Success!")
        data = response.json()
        print(f"Response keys: {list(data.keys())}")
    else:
        print(f"ERROR: Status {response.status_code}")
        print(f"Response text: {response.text}")
        
        # Try to parse error
        try:
            error_data = response.json()
            print(f"\nParsed error data:")
            print(json.dumps(error_data, indent=2, ensure_ascii=False))
            
            if 'errors' in error_data:
                errors = error_data['errors']
                print(f"\nErrors type: {type(errors)}")
                print(f"Errors value: {errors}")
                print(f"Errors is empty: {not errors if isinstance(errors, (dict, list, str)) else errors is None}")
        except:
            print("Could not parse error as JSON")
            
except Exception as e:
    print(f"ERROR: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"Response status: {e.response.status_code}")
        print(f"Response text: {e.response.text[:1000]}")

print("\nDone.")

