#!/usr/bin/env python3
"""
Database migration script to expand session_id column from VARCHAR(36) to VARCHAR(64)
This fixes the StringDataRightTruncation error when storing 43-character session IDs.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

def migrate_session_id_column():
    """Migrate session_id column from VARCHAR(36) to VARCHAR(64)"""
    
    # Get database URL from environment
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable is not set")
        return False
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        print("Starting migration: Expanding session_id column from VARCHAR(36) to VARCHAR(64)")
        
        with engine.connect() as connection:
            # Start transaction
            trans = connection.begin()
            
            try:
                # Check current column definition
                print("Checking current column definition...")
                result = connection.execute(text("""
                    SELECT column_name, data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'file_uploads' AND column_name = 'session_id'
                """))
                
                current_def = result.fetchone()
                if current_def:
                    print(f"Current definition: {current_def.column_name} {current_def.data_type}({current_def.character_maximum_length})")
                else:
                    print("WARNING: session_id column not found in file_uploads table")
                
                # Alter the column
                print("Executing ALTER TABLE command...")
                connection.execute(text("""
                    ALTER TABLE file_uploads 
                    ALTER COLUMN session_id TYPE VARCHAR(64)
                """))
                
                # Verify the change
                print("Verifying the change...")
                result = connection.execute(text("""
                    SELECT column_name, data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'file_uploads' AND column_name = 'session_id'
                """))
                
                new_def = result.fetchone()
                if new_def:
                    print(f"New definition: {new_def.column_name} {new_def.data_type}({new_def.character_maximum_length})")
                
                # Commit transaction
                trans.commit()
                print("Migration completed successfully!")
                return True
                
            except Exception as e:
                # Rollback on error
                trans.rollback()
                print(f"ERROR during migration: {str(e)}")
                return False
                
    except SQLAlchemyError as e:
        print(f"Database connection error: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Session ID Column Migration ===")
    print("This script will expand the session_id column from VARCHAR(36) to VARCHAR(64)")
    print("to fix the StringDataRightTruncation error.\n")
    
    # Confirm before proceeding
    if len(sys.argv) > 1 and sys.argv[1] == "--force":
        proceed = True
    else:
        response = input("Do you want to proceed with the migration? (y/N): ")
        proceed = response.lower() in ['y', 'yes']
    
    if proceed:
        success = migrate_session_id_column()
        if success:
            print("\n✅ Migration completed successfully!")
            print("The session_id column can now store up to 64 characters.")
            sys.exit(0)
        else:
            print("\n❌ Migration failed!")
            sys.exit(1)
    else:
        print("Migration cancelled.")
        sys.exit(0)
