"""
Migration: Fix duplicate data_syncs records
Removes duplicate records and adds unique constraint on data_source
"""
import sqlite3
import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'access_control.db')

def migrate():
    """Fix duplicate data_syncs records"""
    print("Starting fix for duplicate data_syncs...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Step 1: Find duplicates
        cursor.execute("""
            SELECT data_source, COUNT(*) as count
            FROM data_syncs
            GROUP BY data_source
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()
        
        if duplicates:
            print(f"Found {len(duplicates)} data sources with duplicates:")
            for data_source, count in duplicates:
                print(f"  - {data_source}: {count} records")
            
            # Step 2: For each duplicate, keep the one with the latest created_at or id
            for data_source, count in duplicates:
                # Get all IDs for this data_source, ordered by created_at DESC, then id DESC
                cursor.execute("""
                    SELECT id FROM data_syncs
                    WHERE data_source = ?
                    ORDER BY created_at DESC, id DESC
                """, (data_source,))
                ids = cursor.fetchall()
                
                # Keep the first one (newest), delete the rest
                keep_id = ids[0][0]
                delete_ids = [id[0] for id in ids[1:]]
                
                if delete_ids:
                    placeholders = ','.join(['?'] * len(delete_ids))
                    cursor.execute(f"""
                        DELETE FROM data_syncs
                        WHERE id IN ({placeholders})
                    """, delete_ids)
                    print(f"  - Kept record {keep_id} for '{data_source}', deleted {len(delete_ids)} duplicates")
        else:
            print("No duplicates found.")
        
        # Step 3: Add unique constraint by creating a new table
        print("\nAdding unique constraint on data_source...")
        
        # Create new table with unique constraint
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS data_syncs_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_source VARCHAR(100) NOT NULL UNIQUE,
                sync_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                last_sync_at DATETIME,
                next_sync_at DATETIME,
                auto_sync_enabled BOOLEAN NOT NULL DEFAULT 1,
                sync_interval_minutes INTEGER NOT NULL DEFAULT 60,
                api_endpoint VARCHAR(500),
                api_method VARCHAR(10) NOT NULL DEFAULT 'GET',
                api_params TEXT,
                records_synced INTEGER NOT NULL DEFAULT 0,
                sync_duration_seconds REAL,
                error_message TEXT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_synced_by INTEGER,
                FOREIGN KEY (last_synced_by) REFERENCES users(id)
            )
        """)
        
        # Copy data from old table to new table
        cursor.execute("""
            INSERT INTO data_syncs_new 
            (id, data_source, sync_type, status, last_sync_at, next_sync_at,
             auto_sync_enabled, sync_interval_minutes, api_endpoint, api_method,
             api_params, records_synced, sync_duration_seconds, error_message,
             created_at, updated_at, last_synced_by)
            SELECT id, data_source, sync_type, status, last_sync_at, next_sync_at,
                   auto_sync_enabled, sync_interval_minutes, api_endpoint, api_method,
                   api_params, records_synced, sync_duration_seconds, error_message,
                   created_at, updated_at, last_synced_by
            FROM data_syncs
            ORDER BY created_at DESC, id DESC
        """)
        
        # Drop old table
        cursor.execute("DROP TABLE data_syncs")
        
        # Rename new table
        cursor.execute("ALTER TABLE data_syncs_new RENAME TO data_syncs")
        
        # Recreate index
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_data_syncs_source ON data_syncs(data_source)")
        
        conn.commit()
        print("\n[SUCCESS] Fixed duplicate data_syncs and added unique constraint!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()


