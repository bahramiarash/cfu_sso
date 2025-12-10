#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script to add text_input_type column to survey_questions table.
This column determines whether text questions use single-line (input) or multi-line (textarea) input.
"""

import sqlite3
import os

def migrate():
    # Get the path to survey.db (one level up from migrations directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Try multiple possible paths
    possible_paths = [
        os.path.join(script_dir, '..', 'survey.db'),
        os.path.join(script_dir, '..', '..', 'survey.db'),
        os.path.join(os.path.dirname(script_dir), 'survey.db'),
        'survey.db',
        os.path.join('app', 'survey.db')
    ]
    db_path = None
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            db_path = abs_path
            break
    
    if not db_path:
        print(f"Error: Database not found. Searched in:")
        for path in possible_paths:
            print(f"  - {os.path.abspath(path)}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(survey_questions)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'text_input_type' not in columns:
            # Add text_input_type column with default value 'multi_line'
            cursor.execute("""
                ALTER TABLE survey_questions 
                ADD COLUMN text_input_type TEXT DEFAULT 'multi_line' NOT NULL
            """)
            conn.commit()
            print("✓ Added text_input_type column to survey_questions table")
        else:
            print("✓ text_input_type column already exists")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error during migration: {e}")
        return False

if __name__ == '__main__':
    if migrate():
        print("Migration completed successfully!")
    else:
        print("Migration failed!")

