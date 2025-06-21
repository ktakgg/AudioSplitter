#!/usr/bin/env python3
"""
Verify that the session_id column migration was successful
"""

import os
from sqlalchemy import create_engine, text

def verify_migration():
    """Verify the session_id column is now VARCHAR(64)"""
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set")
        return False
    
    try:
        engine = create_engine(database_url)
        
        with engine.connect() as connection:
            # Check current column definition
            result = connection.execute(text("""
                SELECT column_name, data_type, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'file_uploads' AND column_name = 'session_id'
            """))
            
            column_info = result.fetchone()
            if column_info:
                print(f"✅ Column found: {column_info.column_name}")
                print(f"✅ Data type: {column_info.data_type}")
                print(f"✅ Max length: {column_info.character_maximum_length}")
                
                if column_info.character_maximum_length == 64:
                    print("✅ Migration successful! Column is now VARCHAR(64)")
                    return True
                else:
                    print(f"❌ Migration incomplete. Expected 64, got {column_info.character_maximum_length}")
                    return False
            else:
                print("❌ session_id column not found")
                return False
                
    except Exception as e:
        print(f"❌ Error checking migration: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Migration Verification ===")
    success = verify_migration()
    if success:
        print("\n🎉 Database is ready for 64-character session IDs!")
    else:
        print("\n⚠️  Migration verification failed!")
