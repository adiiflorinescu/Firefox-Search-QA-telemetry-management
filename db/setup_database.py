import sqlite3
import os

# --- Configuration ---
# Build paths from the project's root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# MODIFIED: The database will be created in the 'instance' folder at the project root
INSTANCE_FOLDER = os.path.join(PROJECT_ROOT, "instance")
DB_FILE = os.path.join(INSTANCE_FOLDER, "metrics.db")


# --- Database Functions ---

def create_tables(cursor):
    """Creates the database tables with foreign key relationships."""
    print("Creating tables...")

    sql_create_glean_table = """
    CREATE TABLE glean_metrics (
        glean_name TEXT PRIMARY KEY,
        metric_type TEXT NOT NULL,
        expiration TEXT,
        description TEXT,
        search_metric BOOLEAN,
        legacy_correspondent TEXT,
        is_deleted BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT (datetime('now')),
        updated_at DATETIME DEFAULT (datetime('now'))
    );
    """
    sql_create_legacy_table = """
    CREATE TABLE legacy_metrics (
        legacy_name TEXT PRIMARY KEY,
        metric_type TEXT NOT NULL,
        expiration TEXT,
        description TEXT,
        search_metric BOOLEAN,
        glean_correspondent TEXT,
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

    # MODIFIED: The link table now includes region and engine, and a more specific UNIQUE constraint.
    sql_create_link_table = """
    CREATE TABLE coverage_to_metric_link (
        link_id INTEGER PRIMARY KEY AUTOINCREMENT,
        coverage_id INTEGER NOT NULL,
        metric_name TEXT NOT NULL,
        region TEXT,
        engine TEXT,
        FOREIGN KEY (coverage_id) REFERENCES coverage (coverage_id) ON DELETE CASCADE,
        UNIQUE(coverage_id, metric_name, region, engine)
    );
    """

    cursor.execute(sql_create_glean_table)
    cursor.execute(sql_create_legacy_table)
    cursor.execute(sql_create_coverage_table)
    cursor.execute(sql_create_link_table)


def create_triggers(cursor):
    """Creates triggers to auto-update the 'updated_at' column for all tables."""
    print("Creating triggers for auto-updating timestamps...")

    # Trigger for glean_metrics
    cursor.execute("""
        CREATE TRIGGER update_glean_metrics_updated_at
        AFTER UPDATE ON glean_metrics FOR EACH ROW
        BEGIN
            UPDATE glean_metrics SET updated_at = datetime('now') WHERE glean_name = OLD.glean_name;
        END;
    """)

    # Trigger for legacy_metrics
    cursor.execute("""
        CREATE TRIGGER update_legacy_metrics_updated_at
        AFTER UPDATE ON legacy_metrics FOR EACH ROW
        BEGIN
            UPDATE legacy_metrics SET updated_at = datetime('now') WHERE legacy_name = OLD.legacy_name;
        END;
    """)

    # Trigger for the new coverage table
    cursor.execute("""
        CREATE TRIGGER update_coverage_updated_at
        AFTER UPDATE ON coverage FOR EACH ROW
        BEGIN
            UPDATE coverage SET updated_at = datetime('now') WHERE coverage_id = OLD.coverage_id;
        END;
    """)


def main():
    """Main function to create the database schema and triggers."""
    # Ensure the instance folder exists before creating the database inside it
    if not os.path.exists(INSTANCE_FOLDER):
        os.makedirs(INSTANCE_FOLDER)
        print(f"Created instance folder: {INSTANCE_FOLDER}")

    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"Removed existing database file: {DB_FILE}")

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