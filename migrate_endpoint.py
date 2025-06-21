#!/usr/bin/env python3
"""
Simple migration endpoint to fix session_id column
"""

from flask import Flask, jsonify
from database import db
from sqlalchemy import text
import os

app = Flask(__name__)

# Database configuration
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set")

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

@app.route('/migrate-session-id')
def migrate_session_id():
    """Migrate session_id column to VARCHAR(64)"""
    try:
        with db.engine.connect() as connection:
            # Check current column definition
            result = connection.execute(text("""
                SELECT column_name, data_type, character_maximum_length 
                FROM information_schema.columns 
                WHERE table_name = 'file_uploads' AND column_name = 'session_id'
            """))
            
            current_def = result.fetchone()
            if current_def:
                current_length = current_def.character_maximum_length
                
                if current_length == 64:
                    return jsonify({
                        'status': 'already_migrated',
                        'message': 'Column is already VARCHAR(64)',
                        'current_length': current_length
                    })
                
                # Execute migration
                connection.execute(text("ALTER TABLE file_uploads ALTER COLUMN session_id TYPE VARCHAR(64);"))
                connection.commit()
                
                # Verify migration
                result = connection.execute(text("""
                    SELECT column_name, data_type, character_maximum_length 
                    FROM information_schema.columns 
                    WHERE table_name = 'file_uploads' AND column_name = 'session_id'
                """))
                
                new_def = result.fetchone()
                new_length = new_def.character_maximum_length if new_def else None
                
                return jsonify({
                    'status': 'success',
                    'message': 'Migration completed successfully',
                    'old_length': current_length,
                    'new_length': new_length
                })
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'session_id column not found'
                }), 404
                
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Migration failed: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
