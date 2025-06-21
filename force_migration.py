#!/usr/bin/env python3
"""
Force migration of session_id column to VARCHAR(64)
"""

import os
from sqlalchemy import create_engine, text

def force_migration():
    """Force the session_id column to VARCHAR(64)"""
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set")
        return False
    
    try:
        engine = create_engine(database_url)
        
        with engine.connect() as connection:
            # Force the migration
            print("Executing ALTER TABLE command...")
            connection.execute(text("ALTER TABLE file_uploads ALTER COLUMN session_id TYPE VARCHAR(64);"))
            connection.commit()
            print("✅ ALTER TABLE executed successfully")
            
            # Verify the change
            result = connection.execute(text("""
                SELECT column_name, data_type, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'file_uploads' AND column_name = 'session_id'
            """))
            
            column_info = result.fetchone()
            if column_info:
                print(f"✅ Verified - Column: {column_info.column_name}")
                print(f"✅ Verified - Type: {column_info.data_type}")
                print(f"✅ Verified - Length: {column_info.character_maximum_length}")
                
                if column_info.character_maximum_length == 64:
                    print("🎉 SUCCESS: Column is now VARCHAR(64)")
                    return True
                else:
                    print(f"❌ FAILED: Expected 64, got {column_info.character_maximum_length}")
                    return False
            else:
                print("❌ Column verification failed")
                return False
                
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    print("=== Force Migration ===")
    success = force_migration()
    if success:
        print("\n🎉 Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
