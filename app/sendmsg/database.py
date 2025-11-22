import sqlite3

DB_NAME = "C:\\services\\cert2\\app\\access_control.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS Messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_text TEXT NOT NULL,
            insert_date_shamsi TEXT NOT NULL
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS SMS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            mobile TEXT NOT NULL,
            attempts INTEGER DEFAULT 0,
            last_sent_at INTEGER,
            send_result TEXT CHECK(send_result IN ('success', 'failed')),
            message_id INTEGER NOT NULL,
            FOREIGN KEY (message_id) REFERENCES Messages(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()

def insert_message(message_text, insert_date_shamsi):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("INSERT INTO Messages (message_text, insert_date_shamsi) VALUES (?, ?)", 
                (message_text, insert_date_shamsi))
    message_id = cur.lastrowid
    conn.commit()
    conn.close()
    return message_id

def insert_sms_record(mobile, message_id, created_at):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO SMS (created_at, mobile, attempts, last_sent_at, send_result, message_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (created_at, mobile, 1, created_at, 'failed', message_id))
    sms_id = cur.lastrowid
    conn.commit()
    conn.close()
    return sms_id

def update_sms_result(sms_id, result, sent_at):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        UPDATE SMS
        SET send_result = ?, last_sent_at = ?
        WHERE id = ?
    ''', (result, sent_at, sms_id))
    conn.commit()
    conn.close()
