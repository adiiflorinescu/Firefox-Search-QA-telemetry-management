# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/db_migrations.py

import os
import re
from flask import current_app
from .db import get_db

def get_current_db_version(db):
    """Gets the current user_version from the database."""
    return db.execute('PRAGMA user_version').fetchone()[0]

def get_available_migrations():
    """Finds and sorts all available migration scripts."""
    migrations_path = os.path.join(current_app.root_path, '..', 'migrations')
    if not os.path.isdir(migrations_path):
        return {}

    migration_files = {}
    # Regex to find files like 'v1.sql', 'v2.sql', etc.
    version_regex = re.compile(r'^v(\d+)\.sql$')

    for filename in os.listdir(migrations_path):
        match = version_regex.match(filename)
        if match:
            version_num = int(match.group(1))
            migration_files[version_num] = os.path.join(migrations_path, filename)

    return migration_files

def run_migrations():
    """
    Checks the database version and applies all pending migrations.
    This is safe to run on every application startup.
    """
    db = get_db()
    current_version = get_current_db_version(db)
    all_migrations = get_available_migrations()
    latest_version = max(all_migrations.keys()) if all_migrations else 0

    current_app.logger.info(f"Database version: {current_version}. Latest migration available: v{latest_version}.")

    if current_version >= latest_version:
        current_app.logger.info("Database is up to date.")
        return

    # Apply migrations in sorted order
    for version in sorted(all_migrations.keys()):
        if version > current_version:
            script_path = all_migrations[version]
            current_app.logger.info(f"Applying migration: {os.path.basename(script_path)}...")
            try:
                with open(script_path, 'r', encoding='utf-8') as f:
                    db.executescript(f.read())
                db.commit()
                # Verify that the script correctly updated the version
                new_version = get_current_db_version(db)
                if new_version != version:
                    raise RuntimeError(f"Migration {version} did not set PRAGMA user_version correctly!")
                current_app.logger.info(f"Successfully migrated to version {version}.")
                current_version = version
            except Exception as e:
                current_app.logger.error(f"Failed to apply migration {version}: {e}")
                db.rollback()
                # Stop immediately if a migration fails
                raise
