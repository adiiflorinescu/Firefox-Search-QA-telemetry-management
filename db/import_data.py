import sqlite3
import csv
import os
import io
from contextlib import contextmanager

# --- Configuration ---
# Build paths from the project's root directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(PROJECT_ROOT, "metrics.db")
GLEAN_CSV = os.path.join(PROJECT_ROOT, "glean_data.csv")
LEGACY_CSV = os.path.join(PROJECT_ROOT, "legacy_data.csv")
COVERAGE_CSV = os.path.join(PROJECT_ROOT, "coverage_data.csv")


def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# NEW function to handle string content
@contextmanager
def get_csv_stream_from_content(content, table_name, num_expected_columns):
    """
    A context manager that yields a stream-like object for CSV string content.
    It applies pre-processing for metric files to handle formatting issues.
    """
    is_metric_file = table_name in ['glean_metrics', 'legacy_metrics']

    # Wrap content in a stream
    f = io.StringIO(content)

    if is_metric_file:
        def preprocess_metric_csv_generator():
            try:
                yield next(f)
            except StopIteration:
                return

            for line in f:
                if not line.strip(): continue
                name_part, rest_of_line = line.split(',', 1)
                cleaned_name = name_part.split(' ')[0]
                processed_line = f"{cleaned_name},{rest_of_line}"

                parts = processed_line.strip().split(',')
                if len(parts) == num_expected_columns:
                    yield processed_line
                    continue

                if len(parts) > num_expected_columns:
                    try:
                        start_parts = parts[:3]
                        end_parts = parts[-2:]
                        description = ','.join(parts[3:-2])
                        if not description.startswith('"') and not description.endswith('"'):
                            description = f'"{description}"'
                        cleaned_line = ','.join(start_parts + [description] + end_parts) + '\n'
                        yield cleaned_line
                    except IndexError:
                        yield processed_line
                else:
                    yield processed_line

        yield preprocess_metric_csv_generator()
    else:
        yield f


@contextmanager
def get_csv_stream_from_file(file_path, table_name, num_expected_columns):
    """
    A context manager that yields a stream-like object for a CSV file path.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        # Read content to pass to the other function
        content = f.read()

    # Use the content-based stream generator
    with get_csv_stream_from_content(content, table_name, num_expected_columns) as stream:
        yield stream


def import_csv_data(cursor, file_path, table_name, columns):
    """
    Generic function to import data from a CSV file into a table,
    with row-by-row error handling.
    """
    if not os.path.exists(file_path):
        print(f"Warning: Data file not found at '{file_path}'. Skipping import for {table_name}.")
        return

    print(f"\n--- Importing data for {table_name} from {os.path.basename(file_path)} ---")
    inserted_count = 0
    skipped_count = 0

    try:
        # Use the context manager to get the appropriate CSV stream
        with get_csv_stream_from_file(file_path, table_name, len(columns)) as csv_stream:
            reader = csv.reader(csv_stream)

            try:
                # This will now safely handle empty files or streams
                header = next(reader)
            except StopIteration:
                print(
                    f"  [SKIP] File '{os.path.basename(file_path)}' is empty or contains only a header. No data to import.")
                return

            placeholders = ', '.join(['?'] * len(columns))
            sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders});"

            for i, row in enumerate(reader, 2):  # Start line count from 2
                if len(row) != len(columns):
                    print(f"  [SKIP] Line {i}: Incorrect number of columns. Expected {len(columns)}, got {len(row)}.")
                    skipped_count += 1
                    continue

                data_tuple = tuple(val.strip() if val and val.strip() else None for val in row)

                try:
                    cursor.execute(sql, data_tuple)
                    inserted_count += 1
                except sqlite3.IntegrityError as e:
                    print(f"  [SKIP] Line {i}: Database constraint failed. Reason: {e}")
                    skipped_count += 1
                except Exception as e:
                    print(f"  [SKIP] Line {i}: An unexpected error occurred: {e}")
                    skipped_count += 1

    except Exception as e:
        print(f"A critical error occurred while reading {os.path.basename(file_path)}: {e}")
        return

    print(f"--- Summary for {table_name}: {inserted_count} rows inserted, {skipped_count} rows skipped. ---")


def main():
    """Main function to import all data from CSV files."""
    if not os.path.exists(DB_FILE):
        print(f"Error: Database file '{DB_FILE}' not found.")
        print("Please run 'python -m db.setup_database' first to create the database schema.")
        return

    try:
        with get_db_connection() as conn:
            print(f"Connected to database '{DB_FILE}' for data import.")
            cursor = conn.cursor()

            # The order is important due to foreign key constraints
            import_csv_data(
                cursor,
                GLEAN_CSV,
                'glean_metrics',
                ['glean_name', 'metric_type', 'expiration', 'description', 'search_metric', 'legacy_correspondent']
            )
            import_csv_data(
                cursor,
                LEGACY_CSV,
                'legacy_metrics',
                ['legacy_name', 'metric_type', 'expiration', 'description', 'search_metric', 'glean_correspondent']
            )
            import_csv_data(
                cursor,
                COVERAGE_CSV,
                'coverage',
                ['tc_id', 'glean_name', 'legacy_name']
            )

        print("\nData import process finished.")
    except sqlite3.Error as e:
        print(f"A database error occurred during import: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    main()