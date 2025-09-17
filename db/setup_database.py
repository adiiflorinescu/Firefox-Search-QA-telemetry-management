# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/db/setup_database.py

import sqlite3
import os

# --- Configuration ---
# Build paths from the project's root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# The database will be created in the 'instance' folder at the project root
INSTANCE_FOLDER = os.path.join(PROJECT_ROOT, "instance")
DB_FILE = os.path.join(INSTANCE_FOLDER, "metrics.db")


# --- Database Functions ---

def create_tables(cursor):
    """Creates the database tables with foreign key relationships."""
    print("Creating tables...")

    # --- CORRECTED SCHEMA: Added 'priority' column ---
    sql_create_glean_table = """
    CREATE TABLE glean_metrics (
        glean_name TEXT PRIMARY KEY,
        metric_type TEXT NOT NULL,
        expiration TEXT,
        description TEXT,
        search_metric BOOLEAN,
        legacy_correspondent TEXT,
        priority TEXT, -- ADDED
        is_deleted BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT (datetime('now')),
        updated_at DATETIME DEFAULT (datetime('now'))
    );
    """
    # --- CORRECTED SCHEMA: Added 'priority' column ---
    sql_create_legacy_table = """
    CREATE TABLE legacy_metrics (
        legacy_name TEXT PRIMARY KEY,
        metric_type TEXT NOT NULL,
        expiration TEXT,
        description TEXT,
        search_metric BOOLEAN,
        glean_correspondent TEXT,
        priority TEXT, -- ADDED
        is_deleted BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT (datetime('now')),
        updated_at DATETIME DEFAULT (datetime('now'))
    );
    """
    # The coverage table stores the unique TCID and its title.
    sql_create_coverage_table = """
    CREATE TABLE coverage (
        coverage_id INTEGER PRIMARY KEY AUTOINCREMENT,
        tc_id TEXT NOT NULL UNIQUE,
        tcid_title TEXT,
        is_deleted BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT (datetime('now')),
        updated_at DATETIME DEFAULT (datetime('now'))
    );
    """

    # The link table now includes metric_type to ensure uniqueness.
    sql_create_link_table = """
    CREATE TABLE coverage_to_metric_link (
        link_id INTEGER PRIMARY KEY AUTOINCREMENT,
        coverage_id INTEGER NOT NULL,
        metric_name TEXT NOT NULL,
        metric_type TEXT NOT NULL,
        region TEXT,
        engine TEXT,
        is_deleted BOOLEAN DEFAULT FALSE,
        FOREIGN KEY (coverage_id) REFERENCES coverage (coverage_id) ON DELETE CASCADE,
        UNIQUE(coverage_id, metric_name, metric_type, region, engine)
    );
    """

    # --- CORRECTED SCHEMA: Removed 'priority' column ---
    sql_create_planning_table = """
    CREATE TABLE planning (
        planning_id INTEGER PRIMARY KEY AUTOINCREMENT,
        metric_name TEXT NOT NULL,
        metric_type TEXT NOT NULL,
        tc_id TEXT,
        region TEXT,
        engine TEXT,
        is_deleted BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT (datetime('now')),
        updated_at DATETIME DEFAULT (datetime('now')),
        UNIQUE(metric_name, metric_type, tc_id, region, engine)
    );
    """

    cursor.execute(sql_create_glean_table)
    cursor.execute(sql_create_legacy_table)
    cursor.execute(sql_create_coverage_table)
    cursor.execute(sql_create_link_table)
    cursor.execute(sql_create_planning_table)


def create_triggers(cursor):
    """Creates triggers to auto-update the 'updated_at' column for all tables."""
    print("Creating triggers for auto-updating timestamps...")

    tables = ['glean_metrics', 'legacy_metrics', 'coverage', 'planning']
    pk_columns = {
        'glean_metrics': 'glean_name',
        'legacy_metrics': 'legacy_name',
        'coverage': 'coverage_id',
        'planning': 'planning_id'
    }

    for table in tables:
        pk = pk_columns[table]
        trigger_sql = f"""
            CREATE TRIGGER update_{table}_updated_at
            AFTER UPDATE ON {table} FOR EACH ROW
            BEGIN
                UPDATE {table} SET updated_at = datetime('now') WHERE {pk} = OLD.{pk};
            END;
        """
        cursor.execute(trigger_sql)


def main():
    """Main function to create the database schema and triggers."""
    # Ensure the instance folder exists before creating the database inside it
    if not os.path.exists(INSTANCE_FOLDER):
        os.makedirs(INSTANCE_FOLDER)
        print(f"Created instance folder: {INSTANCE_FOLDER}")

    if os.path.exists(DB_FILE):
        # Safety check to prevent accidental deletion
        response = input(
            f"Database file '{DB_FILE}' already exists. Are you sure you want to delete and re-create it? (y/N): ")
        if response.lower() == 'y':
            os.remove(DB_FILE)
            print(f"Removed existing database file: {DB_FILE}")
        else:
            print("Database creation cancelled.")
            return

    try:
        with sqlite3.connect(DB_FILE) as conn:
            print(f"Successfully connected to SQLite database: {DB_FILE}")
            # Enable foreign key constraint enforcement
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor = conn.cursor()

            create_tables(cursor)
            create_triggers(cursor)

        print("Database schema and triggers created successfully.")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == '__main__':
    main()