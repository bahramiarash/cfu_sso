"""
Migration script to add color_palette column to chart_configs table
Run this script to add the color_palette field to existing database
"""
import sqlite3
import os
from pathlib import Path

def migrate():
    """Add color_palette column to chart_configs table"""
    # Find database file
    db_path = None
    possible_paths = [
        'app/instance/access_control.db',
        'instance/access_control.db',
        'access_control.db',
        'app/access_control.db',
        'instance/cert2.db',
        'cert2.db',
        'app/instance/cert2.db',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            db_path = path
            print(f"Found database at: {db_path}")
            break
    
    if not db_path:
        print("Error: Database file not found. Please specify the database path.")
        print("Searched paths:")
        for path in possible_paths:
            print(f"  - {path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(chart_configs)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'color_palette' in columns:
            print(f"Column 'color_palette' already exists in chart_configs table.")
            conn.close()
            return True
        
        # Add color_palette column
        cursor.execute("""
            ALTER TABLE chart_configs 
            ADD COLUMN color_palette VARCHAR(50) DEFAULT 'default' NOT NULL
        """)
        
        conn.commit()
        conn.close()
        
        print(f"Successfully added 'color_palette' column to chart_configs table in {db_path}")
        return True
        
    except Exception as e:
        print(f"Error migrating database: {e}")
        return False

if __name__ == '__main__':
    migrate()

