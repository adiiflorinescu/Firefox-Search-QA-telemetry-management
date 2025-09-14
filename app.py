import sqlite3
import os
import csv
import io
import re
from flask import Flask, jsonify, render_template, request, flash, redirect, url_for, session, Response
from collections import defaultdict
from dotenv import load_dotenv

# --- Load Environment Variables ---
# This will load the .env file in the root directory
load_dotenv()

# --- Import configuration ---
import config

# --- App Initialization ---
app = Flask(__name__)

# --- Configuration ---
# Load configuration from environment variables or defaults
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'a-default-secret-key-for-dev-only')
# Set the database file path relative to the instance folder
app.config['DATABASE'] = os.path.join(app.instance_path, 'metrics.db')

# Ensure the instance folder exists
try:
    os.makedirs(app.instance_path)
except OSError:
    pass


# --- Database Helper ---
def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# --- Generic CSV Upload Logic ---
def process_csv_upload(file, table_name, columns, redirect_url):
    """Generic function to process a CSV file upload and store results in session."""
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(redirect_url)
    if not file.filename.endswith('.csv'):
        flash('Invalid file type. Please upload a .csv file.', 'error')
        return redirect(redirect_url)

    inserted_count = 0
    skipped_rows = []
    try:
        # We can't pass a file handle to the pre-processor, so we read it first
        stream_content = file.stream.read().decode("UTF8")

        # Use the pre-processing stream from the db module
        from db.import_data import get_csv_stream_from_content
        with get_csv_stream_from_content(stream_content, table_name, len(columns)) as csv_stream:
            csv_reader = csv.reader(csv_stream)
            header = next(csv_reader)  # Skip header

            with get_db_connection() as conn:
                cursor = conn.cursor()

                # MODIFIED: Special handling for coverage uploads
                if table_name == 'coverage':
                    for i, row in enumerate(csv_reader, 2):
                        if len(row) != len(columns):
                            skipped_rows.append(
                                f"Line {i}: Incorrect column count. Expected {len(columns)}, got {len(row)}.")
                            continue

                        tc_id, tcid_title, metrics_str = (row[0], row[1], row[2])
                        metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]

                        if not tc_id or not metric_names:
                            skipped_rows.append(f"Line {i}: TC ID and at least one metric are required.")
                            continue

                        try:
                            cursor.execute("SAVEPOINT csv_row;")
                            # Insert into coverage table
                            cursor.execute(
                                "INSERT INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                                (tc_id, tcid_title or None)
                            )
                            coverage_id = cursor.lastrowid
                            # Insert into link table
                            for metric in metric_names:
                                cursor.execute(
                                    "INSERT INTO coverage_to_metric_link (coverage_id, metric_name) VALUES (?, ?)",
                                    (coverage_id, metric)
                                )
                            cursor.execute("RELEASE SAVEPOINT csv_row;")
                            inserted_count += 1
                        except sqlite3.IntegrityError as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i} (TCID: {tc_id}): {e}")
                        except Exception as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i} (TCID: {tc_id}): Unexpected error {e}")
                else:
                    # Original logic for other tables
                    placeholders = ', '.join(['?'] * len(columns))
                    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders});"
                    for i, row in enumerate(csv_reader, 2):
                        if len(row) != len(columns):
                            skipped_rows.append(
                                f"Line {i}: Incorrect column count. Expected {len(columns)}, got {len(row)}.")
                            continue

                        data_tuple = tuple(val.strip() if val and val.strip() else None for val in row)
                        try:
                            cursor.execute("SAVEPOINT csv_row;")
                            cursor.execute(sql, data_tuple)
                            cursor.execute("RELEASE SAVEPOINT csv_row;")
                            inserted_count += 1
                        except sqlite3.IntegrityError as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i}: {e}")
                        except Exception as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i}: Unexpected error {e}")

        # Store results in session, keyed by table name for clarity
        session[f'{table_name}_upload_results'] = {'inserted': inserted_count, 'skipped': skipped_rows}

    except Exception as e:
        flash(f"A critical error occurred while processing the CSV: {e}", 'error')

    return redirect(redirect_url)


# --- NEW: Root URL Route ---
@app.route('/')
def home():
    """Redirects the base URL to the main metrics view page."""
    return redirect(url_for('metrics'))


# --- Management Page Route ---
@app.route('/manage')
def index():
    """Renders the main data management page."""
    # Pop all possible result keys from the session
    coverage_upload_results = session.pop('coverage_upload_results', None)
    glean_upload_results = session.pop('glean_metrics_upload_results', None)
    legacy_upload_results = session.pop('legacy_metrics_upload_results', None)

    return render_template(
        'index.html',
        coverage_upload_results=coverage_upload_results,
        glean_upload_results=glean_upload_results,
        legacy_upload_results=legacy_upload_results
    )


# --- View Metrics Page Route ---

@app.route('/metrics')
def metrics():
    """Renders the metrics and coverage view page."""
    conn = get_db_connection()
    glean_metrics = conn.execute('SELECT * FROM glean_metrics WHERE is_deleted = FALSE ORDER BY glean_name').fetchall()
    legacy_metrics = conn.execute(
        'SELECT * FROM legacy_metrics WHERE is_deleted = FALSE ORDER BY legacy_name').fetchall()

    # MODIFIED: Query to join coverage with the link table and aggregate metrics
    coverage_query = """
        SELECT
            c.coverage_id,
            c.tc_id,
            c.tcid_title,
            c.created_at,
            c.updated_at,
            GROUP_CONCAT(l.metric_name, ', ') as metrics
        FROM coverage c
        LEFT JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE
        GROUP BY c.coverage_id
        ORDER BY c.tc_id;
    """
    coverage = conn.execute(coverage_query).fetchall()
    conn.close()

    return render_template(
        'metrics.html',
        glean_metrics=glean_metrics,
        legacy_metrics=legacy_metrics,
        coverage=coverage,
        tc_base_url=config.TC_BASE_URL
    )


# --- MODIFIED: Metric Reports Page Route ---
@app.route('/reports')
def reports():
    """Renders the new metric reports page with aggregated data."""
    conn = get_db_connection()

    # --- NEW: Queries for the breakdown section ---
    total_glean_metrics = conn.execute("SELECT COUNT(*) FROM glean_metrics WHERE is_deleted = FALSE").fetchone()[0]
    total_legacy_metrics = conn.execute("SELECT COUNT(*) FROM legacy_metrics WHERE is_deleted = FALSE").fetchone()[0]

    # MODIFIED: These queries now check the link table
    glean_covered_tcs = conn.execute("""
        SELECT COUNT(DISTINCT l.coverage_id) FROM coverage_to_metric_link l
        JOIN glean_metrics g ON l.metric_name = g.glean_name
    """).fetchone()[0]
    legacy_covered_tcs = conn.execute("""
        SELECT COUNT(DISTINCT l.coverage_id) FROM coverage_to_metric_link l
        JOIN legacy_metrics lg ON l.metric_name = lg.legacy_name
    """).fetchone()[0]

    # MODIFIED: This query now joins through the link table and qualifies column names.
    # Comments are moved outside the query string to prevent SQL errors.
    report_query = """
        SELECT
            all_metrics.metric_name,
            all_metrics.metric_type,
            COUNT(l.link_id) as tcid_count
        FROM (
            SELECT glean_name as metric_name, 'Glean' as metric_type FROM glean_metrics WHERE is_deleted = FALSE
            UNION ALL
            SELECT legacy_name as metric_name, 'Legacy' as metric_type FROM legacy_metrics WHERE is_deleted = FALSE
        ) as all_metrics
        LEFT JOIN coverage_to_metric_link l ON all_metrics.metric_name = l.metric_name
        GROUP BY all_metrics.metric_name, all_metrics.metric_type
        ORDER BY all_metrics.metric_name;
    """
    report_data = conn.execute(report_query).fetchall()

    # MODIFIED: Fetch coverage data to build a mapping of metric -> [tcids]
    coverage_data_query = """
        SELECT c.tc_id, c.tcid_title, l.metric_name
        FROM coverage c
        JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE
    """
    coverage_data = conn.execute(coverage_data_query).fetchall()

    metric_to_tcids = defaultdict(list)
    for row in coverage_data:
        tcid_info = (row['tc_id'], row['tcid_title'])
        if row['metric_name']:
            metric_to_tcids[row['metric_name']].append(tcid_info)

    conn.close()

    return render_template(
        'reports.html',
        report_data=report_data,
        metric_to_tcids=metric_to_tcids,
        tc_base_url=config.TC_BASE_URL,
        total_glean_metrics=total_glean_metrics,
        total_legacy_metrics=total_legacy_metrics,
        glean_covered_tcs=glean_covered_tcs,
        legacy_covered_tcs=legacy_covered_tcs
    )


# --- NEW: Probe Extraction Route ---
@app.route('/extract-probes', methods=['POST'])
def extract_probes():
    """
    Handles file upload, extracts telemetry probes, and returns a new CSV file.
    """
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected for probe extraction.', 'error')
        return redirect(url_for('index'))
    if not file.filename.endswith('.csv'):
        flash('Invalid file type. Please upload a .csv file.', 'error')
        return redirect(url_for('index'))

    # Regex to find probes starting with 'browser.', 'urlbar.', OR 'contextservices.'
    probe_regex = re.compile(r'(?:browser|urlbar|contextservices)\.[\w.-]+')

    try:
        # Read the uploaded file in memory
        stream_content = file.stream.read().decode("UTF8")
        infile = io.StringIO(stream_content)
        reader = csv.reader(infile)

        # Prepare the output CSV in memory
        outfile = io.StringIO()
        writer = csv.writer(outfile)

        # Process header
        header = next(reader)
        writer.writerow(header + ['Found Probes'])
        steps_col_index = header.index('Steps')
        expected_steps_col_index = header.index('Steps (Expected Result)')

        # Process each row
        for row in reader:
            if len(row) > max(steps_col_index, expected_steps_col_index):
                combined_text = row[steps_col_index] + " " + row[expected_steps_col_index]
                found_probes = set(probe_regex.findall(combined_text))
                result_text = ', '.join(sorted(list(found_probes))) if found_probes else 'nothing found'
                writer.writerow(row + [result_text])
            else:
                writer.writerow(row + ['malformed row'])

        # Create a response to send the file back to the user
        output = outfile.getvalue()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=extract_data_with_probes.csv"}
        )

    except ValueError as e:
        flash(f"Error processing CSV: Missing required column in header - {e}", 'error')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"An unexpected error occurred during probe extraction: {e}", 'error')
        return redirect(url_for('index'))


# --- NEW: Soft Delete Route ---
@app.route('/delete/<string:table_name>/<string:pk>', methods=['POST'])
def soft_delete(table_name, pk):
    """Marks an item as deleted in the database."""
    pk_columns = {
        'coverage': 'coverage_id',
        'glean_metrics': 'glean_name',
        'legacy_metrics': 'legacy_name'
    }

    if table_name not in pk_columns:
        return jsonify({'success': False, 'error': 'Invalid table name'}), 400

    pk_column = pk_columns[table_name]

    try:
        with get_db_connection() as conn:
            # For coverage, we only need to delete from the main table.
            # The link table will cascade delete if set up, but a soft delete is better.
            if table_name == 'coverage':
                conn.execute(f"UPDATE coverage SET is_deleted = TRUE WHERE {pk_column} = ?", (pk,))
            else:
                conn.execute(f"UPDATE {table_name} SET is_deleted = TRUE WHERE {pk_column} = ?", (pk,))
        return jsonify({'success': True})
    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- Form Submission Routes ---

@app.route('/coverage/add', methods=['POST'])
def add_coverage():
    """Handles the form submission for a new coverage entry with multiple metrics."""
    tc_id = request.form.get('tc_id')
    tcid_title = request.form.get('tcid_title')
    metrics_str = request.form.get('metrics')  # Comma-separated string

    if not tc_id or not metrics_str:
        flash('TC ID and at least one Metric are required.', 'error')
        return redirect(url_for('index'))

    metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]
    if not metric_names:
        flash('At least one valid metric name is required.', 'error')
        return redirect(url_for('index'))

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Insert into main coverage table first
            cursor.execute(
                "INSERT INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                (tc_id, tcid_title or None)
            )
            # Get the ID of the new coverage entry
            coverage_id = cursor.lastrowid

            # Insert a record into the link table for each metric
            for metric in metric_names:
                cursor.execute(
                    "INSERT INTO coverage_to_metric_link (coverage_id, metric_name) VALUES (?, ?)",
                    (coverage_id, metric)
                )
        flash(f"Successfully added coverage for TC ID: {tc_id}", 'success')
    except sqlite3.IntegrityError as e:
        flash(f"Error: Could not add entry. A TC ID might already exist. (DB: {e})", 'error')
    except Exception as e:
        flash(f"An unexpected error occurred: {e}", 'error')
    return redirect(url_for('index'))


@app.route('/coverage/upload', methods=['POST'])
def upload_coverage_csv():
    """Handles CSV file upload for bulk coverage creation."""
    # MODIFIED: Columns are now tc_id, tcid_title, and a comma-separated metrics string
    return process_csv_upload(
        request.files.get('file'),
        'coverage',
        ['tc_id', 'tcid_title', 'metrics'],
        url_for('index')
    )


@app.route('/glean/add', methods=['POST'])
def add_glean_metric():
    """Adds a single new Glean metric."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO glean_metrics (glean_name, metric_type, description) VALUES (?, ?, ?)",
                (request.form['glean_name'], request.form['metric_type'], request.form['description'])
            )
        flash(f"Successfully added Glean metric: {request.form['glean_name']}", 'success')
    except sqlite3.IntegrityError as e:
        flash(f"Error adding Glean metric: {e}", 'error')
    return redirect(url_for('index'))


@app.route('/legacy/add', methods=['POST'])
def add_legacy_metric():
    """Adds a single new Legacy metric."""
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO legacy_metrics (legacy_name, metric_type, description) VALUES (?, ?, ?)",
                (request.form['legacy_name'], request.form['metric_type'], request.form['description'])
            )
        flash(f"Successfully added Legacy metric: {request.form['legacy_name']}", 'success')
    except sqlite3.IntegrityError as e:
        flash(f"Error adding Legacy metric: {e}", 'error')
    return redirect(url_for('index'))


@app.route('/glean/upload', methods=['POST'])
def upload_glean_csv():
    """Handles CSV upload for Glean metrics."""
    return process_csv_upload(
        request.files.get('file'),
        'glean_metrics',
        ['glean_name', 'metric_type', 'expiration', 'description', 'search_metric', 'legacy_correspondent'],
        url_for('index')
    )


@app.route('/legacy/upload', methods=['POST'])
def upload_legacy_csv():
    """Handles CSV upload for Legacy metrics."""
    return process_csv_upload(
        request.files.get('file'),
        'legacy_metrics',
        ['legacy_name', 'metric_type', 'expiration', 'description', 'search_metric', 'glean_correspondent'],
        url_for('index')
    )


# --- Shared API Routes ---

@app.route('/search-suggestions')
def search_suggestions():
    """Provides a JSON list of search terms for autofill."""
    suggestion_type = request.args.get('type', 'all')
    with get_db_connection() as conn:
        suggestions = []
        if suggestion_type in ['all', 'glean', 'metrics']:
            suggestions.extend(
                [row['glean_name'] for row in
                 conn.execute('SELECT glean_name FROM glean_metrics WHERE is_deleted = FALSE').fetchall()])
        if suggestion_type in ['all', 'legacy', 'metrics']:
            suggestions.extend([row['legacy_name'] for row in
                                conn.execute(
                                    'SELECT legacy_name FROM legacy_metrics WHERE is_deleted = FALSE ORDER BY legacy_name').fetchall()])
        if suggestion_type == 'all':
            suggestions.extend([row['tc_id'] for row in conn.execute(
                'SELECT DISTINCT tc_id FROM coverage WHERE is_deleted = FALSE').fetchall()])
    return jsonify(sorted(list(set(suggestions))))


# This block is now only used for local development
if __name__ == '__main__':
    # For development, run with the built-in server
    app.run(debug=True)