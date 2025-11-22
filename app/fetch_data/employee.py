import requests
import sqlite3
import logging
import time

# ---------------------- CONFIGURATION ----------------------
API_BASE_URL = "https://api.cfu.ac.ir"
LOGIN_URL = f"{API_BASE_URL}/Login"
PERSONEL_URL = f"{API_BASE_URL}/API/Employee/Personels"

USERNAME = "khodarahmi"
PASSWORD = "9909177"
DB_NAME = "faculty_data.db"
PAGE_SIZE = 100  # می‌توانید بر اساس نیاز افزایش دهید

# ---------------------- LOGGING SETUP ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ---------------------- FUNCTIONS ----------------------

def login_and_get_token():
    """Login and retrieve bearer token"""
    payload = {"userName": USERNAME, "password": PASSWORD}
    try:
        response = requests.post(LOGIN_URL, json=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        token = data.get('data', {}).get('token')
        if not token:
            raise ValueError("Token missing in response.")
        logging.info("✅ Token received successfully.")
        return token
    except Exception as e:
        logging.error(f"❌ Login failed: {e}")
        return None


def init_db():
    """Initialize SQLite table for personel data"""
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS personel (
                id TEXT PRIMARY KEY,
                nationalid TEXT UNIQUE,
                name TEXT,
                family TEXT,
                employ_state TEXT,
                mobile TEXT,
                sex TEXT,
                scope_ID TEXT,
                scope TEXT,
                employtype TEXT,
                employtype_title TEXT,
                estekhdamtype TEXT,
                estekhdamtype_title TEXT,
                organ_Unit TEXT,
                organ_Unit_title TEXT,
                organ_post_title TEXT,
                province_code TEXT
            )
        ''')
    logging.info("🗄️ SQLite table 'personel' initialized.")


def fetch_personel_data(token, page_number=1):
    """Fetch a single page of personel data from API"""
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"pageNumber": page_number, "pageSize": PAGE_SIZE}

    try:
        response = requests.post(PERSONEL_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        records = data.get("data", [])
        total_pages = data.get("totalPages", 1)
        logging.info(f"📦 Page {page_number}/{total_pages}: {len(records)} records fetched.")
        return records, total_pages
    except Exception as e:
        logging.error(f"❌ Failed to fetch page {page_number}: {e}")
        return [], 0


def insert_personel_records(records):
    """Insert or update personel records"""
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        inserted, skipped = 0, 0

        for rec in records:
            if not rec.get("nationalid"):
                skipped += 1
                continue

            cur.execute('''
                INSERT INTO personel (
                    id, nationalid, name, family, employ_state, mobile, sex,
                    scope_ID, scope, employtype, employtype_title,
                    estekhdamtype, estekhdamtype_title,
                    organ_Unit, organ_Unit_title, organ_post_title
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(nationalid) DO UPDATE SET
                    name=excluded.name,
                    family=excluded.family,
                    employ_state=excluded.employ_state,
                    mobile=excluded.mobile,
                    organ_Unit_title=excluded.organ_Unit_title,
                    organ_post_title=excluded.organ_post_title
            ''', (
                rec.get("id"),
                rec.get("nationalid"),
                rec.get("name"),
                rec.get("family"),
                rec.get("employ_state"),
                rec.get("mobile"),
                rec.get("sex"),
                rec.get("scope_ID"),
                rec.get("scope"),
                rec.get("employtype"),
                rec.get("employtype_title"),
                rec.get("estekhdamtype"),
                rec.get("estekhdamtype_title"),
                rec.get("organ_Unit"),
                rec.get("organ_Unit_title"),
                rec.get("organ_post_title"),
            ))

            inserted += 1

        conn.commit()
        logging.info(f"✅ {inserted} inserted/updated, 🚫 {skipped} skipped (no nationalid).")


def fetch_all_personels():
    """Fetch all personel pages until completion"""
    token = login_and_get_token()
    if not token:
        return

    init_db()

    first_page, total_pages = fetch_personel_data(token, page_number=1)
    if not first_page:
        logging.warning("⚠️ No data retrieved from first page.")
        return

    insert_personel_records(first_page)

    for page in range(2, total_pages + 1):
        records, _ = fetch_personel_data(token, page)
        if not records:
            continue
        insert_personel_records(records)
        time.sleep(0.5)  # polite delay between requests

    logging.info("🎯 All pages processed successfully.")


def get_personel_by_scope(scope_name):
    """Get all personel by scope (organizational area)"""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, family, sex, employ_state, mobile, organ_Unit_title, organ_post_title
            FROM personel
            WHERE scope LIKE ?
            ORDER BY family, name
        """, (f"%{scope_name}%",))
        rows = cursor.fetchall()

    return [
        {
            "row_num": idx + 1,
            "name": r[0],
            "family": r[1],
            "sex": r[2],
            "employ_state": r[3],
            "mobile": r[4],
            "organ_Unit_title": r[5],
            "organ_post_title": r[6],
        }
        for idx, r in enumerate(rows)
    ]


# ---------------------- MAIN ENTRY ----------------------
if __name__ == "__main__":
    fetch_all_personels()
