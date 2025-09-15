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
    """
    Generic function to process a CSV file upload and store results in session.
    MODIFIED: No longer accepts 'metric_type' as a parameter. It's now expected in the CSV for coverage uploads.
    """
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

                # MODIFIED: Special handling for coverage uploads with per-row validation
                if table_name == 'coverage':
                    for i, row in enumerate(csv_reader, 2):
                        if len(row) != len(columns):
                            skipped_rows.append(
                                f"Line {i}: Incorrect column count. Expected {len(columns)}, got {len(row)}.")
                            continue

                        # MODIFIED: Unpack the new metric_type column
                        tc_id, tcid_title, metrics_str, metric_type = (row[0], row[1], row[2], row[3].lower().strip())
                        metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]

                        if not tc_id or not metric_names:
                            skipped_rows.append(f"Line {i}: TC ID and at least one metric are required.")
                            continue

                        if metric_type not in ['glean', 'legacy']:
                            skipped_rows.append(
                                f"Line {i} (TCID: {tc_id}): Invalid metric_type '{row[3]}'. Must be 'glean' or 'legacy'.")
                            continue

                        try:
                            # --- Metric Existence Validation for this row ---
                            val_table_name = 'glean_metrics' if metric_type == 'glean' else 'legacy_metrics'
                            val_column_name = 'glean_name' if metric_type == 'glean' else 'legacy_name'
                            non_existent_metrics = []
                            for metric in metric_names:
                                metric_exists = cursor.execute(
                                    f"SELECT 1 FROM {val_table_name} WHERE {val_column_name} = ? AND is_deleted = FALSE",
                                    (metric,)
                                ).fetchone()
                                if not metric_exists:
                                    non_existent_metrics.append(metric)

                            if non_existent_metrics:
                                skipped_rows.append(
                                    f"Line {i} (TCID: {tc_id}): Skipped due to non-existent {metric_type} metrics: {', '.join(non_existent_metrics)}")
                                continue  # Skip this entire row

                            # --- If all metrics are valid, proceed with insertion ---
                            cursor.execute("SAVEPOINT csv_row;")

                            # Find or create the coverage entry for the TCID
                            coverage_entry = cursor.execute(
                                "SELECT coverage_id FROM coverage WHERE tc_id = ? AND is_deleted = FALSE", (tc_id,)
                            ).fetchone()

                            if coverage_entry:
                                coverage_id = coverage_entry['coverage_id']
                                cursor.execute("UPDATE coverage SET tcid_title = ? WHERE coverage_id = ?",
                                               (tcid_title or None, coverage_id))
                            else:
                                cursor.execute(
                                    "INSERT INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                                    (tc_id, tcid_title or None)
                                )
                                coverage_id = cursor.lastrowid

                            # Insert into link table, avoiding duplicates
                            for metric in metric_names:
                                existing_link = cursor.execute(
                                    "SELECT 1 FROM coverage_to_metric_link WHERE coverage_id = ? AND metric_name = ?",
                                    (coverage_id, metric)
                                ).fetchone()
                                if not existing_link:
                                    cursor.execute(
                                        "INSERT INTO coverage_to_metric_link (coverage_id, metric_name) VALUES (?, ?)",
                                        (coverage_id, metric)
                                    )

                            cursor.execute("RELEASE SAVEPOINT csv_row;")
                            inserted_count += 1
                        except sqlite3.Error as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i} (TCID: {tc_id}): Database error - {e}")

                else:
                    # MODIFIED: Logic for Glean/Legacy uploads to handle optional columns
                    placeholders = ', '.join(['?'] * len(columns))
                    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders});"

                    for i, row in enumerate(csv_reader, 2):
                        # The first column (the name) is always required.
                        if not row or not row[0].strip():
                            skipped_rows.append(f"Line {i}: Skipped because the metric name is missing.")
                            continue

                        # Pad the row with None values if optional columns are missing
                        padded_row = (row + [None] * len(columns))[:len(columns)]

                        # --- FIX for NOT NULL constraint ---
                        # Create a mutable list from the padded row to modify it
                        row_values = list(padded_row)

                        # If metric_type (at index 1) is missing, provide a default.
                        if not row_values[1] or not row_values[1].strip():
                            row_values[1] = 'Uncategorized'  # Default value

                        data_tuple = tuple(val.strip() if val and val.strip() else None for val in row_values)

                        try:
                            cursor.execute("SAVEPOINT csv_row;")
                            cursor.execute(sql, data_tuple)
                            cursor.execute("RELEASE SAVEPOINT csv_row;")
                            inserted_count += 1
                        except sqlite3.IntegrityError as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i} (Metric: {data_tuple[0]}): {e}")
                        except Exception as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i} (Metric: {data_tuple[0]}): Unexpected error {e}")

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
        # MODIFIED: Pass the coverage results to the template
        coverage_upload_results=coverage_upload_results,
        glean_upload_results=glean_upload_results,
        legacy_upload_results=legacy_upload_results,
        # Pass session state to the template
        show_management=session.get('show_management', False)
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
        tc_base_url=config.TC_BASE_URL,
        # Pass session state to the template
        show_management=session.get('show_management', False)
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
        legacy_covered_tcs=legacy_covered_tcs,
        # Pass session state to the template
        show_management=session.get('show_management', False)
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


# --- NEW: Route to toggle management view visibility ---
@app.route('/toggle-management-view', methods=['POST'])
def toggle_management_view():
    """Toggles the visibility of the management tab in the session."""
    session['show_management'] = not session.get('show_management', False)
    return jsonify({'success': True, 'show_management': session['show_management']})


# --- Form Submission Routes ---

@app.route('/coverage/add', methods=['POST'])
def add_coverage():
    """
    Handles the form submission for a new coverage entry, validating that the
    associated metrics exist in the corresponding glean or legacy table.
    """
    tc_id = request.form.get('tc_id')
    tcid_title = request.form.get('tcid_title')
    metric_type = request.form.get('metric_type')  # 'glean' or 'legacy'
    metrics_str = request.form.get('metrics')

    # --- 1. Input Validation ---
    if not all([tc_id, metric_type, metrics_str]):
        flash('TC ID, Metric Type, and at least one Metric are required.', 'error')
        return redirect(url_for('index'))

    if metric_type not in ['glean', 'legacy']:
        flash('Invalid metric type specified.', 'error')
        return redirect(url_for('index'))

    metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]
    if not metric_names:
        flash('At least one valid metric name is required.', 'error')
        return redirect(url_for('index'))

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Use a transaction to ensure all operations succeed or fail together.
            cursor.execute("BEGIN;")

            # --- 2. Metric Existence Validation ---
            non_existent_metrics = []
            table_name = 'glean_metrics' if metric_type == 'glean' else 'legacy_metrics'
            column_name = 'glean_name' if metric_type == 'glean' else 'legacy_name'

            for metric in metric_names:
                metric_exists = cursor.execute(
                    f"SELECT 1 FROM {table_name} WHERE {column_name} = ? AND is_deleted = FALSE",
                    (metric,)
                ).fetchone()
                if not metric_exists:
                    non_existent_metrics.append(metric)

            if non_existent_metrics:
                flash(
                    f"Error: The following {metric_type} metrics do not exist: {', '.join(non_existent_metrics)}. Please add them first.",
                    'error')
                cursor.execute("ROLLBACK;")
                return redirect(url_for('index'))

            # --- 3. Database Insertion ---
            # Find or create the coverage entry for the TCID
            coverage_entry = cursor.execute(
                "SELECT coverage_id FROM coverage WHERE tc_id = ? AND is_deleted = FALSE", (tc_id,)
            ).fetchone()

            if coverage_entry:
                coverage_id = coverage_entry['coverage_id']
                # Optionally update the title if it has changed
                cursor.execute("UPDATE coverage SET tcid_title = ? WHERE coverage_id = ?",
                               (tcid_title or None, coverage_id))
            else:
                # Create a new coverage entry if it's the first time we see this TCID
                cursor.execute(
                    "INSERT INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                    (tc_id, tcid_title or None)
                )
                coverage_id = cursor.lastrowid

            # Insert a record into the link table for each validated metric
            for metric in metric_names:
                # Check if this exact TCID -> Metric link already exists to prevent duplicates
                existing_link = cursor.execute("""
                    SELECT 1 FROM coverage_to_metric_link
                    WHERE coverage_id = ? AND metric_name = ?
                """, (coverage_id, metric)).fetchone()

                if not existing_link:
                    cursor.execute(
                        "INSERT INTO coverage_to_metric_link (coverage_id, metric_name) VALUES (?, ?)",
                        (coverage_id, metric)
                    )

            cursor.execute("COMMIT;")  # Commit the transaction

        flash(f"Successfully added/updated coverage for TC ID '{tc_id}'.", 'success')

    except sqlite3.IntegrityError as e:
        cursor.execute("ROLLBACK;")
        flash(f"Database Error: Could not add entry. (Details: {e})", 'error')
    except Exception as e:
        cursor.execute("ROLLBACK;")
        flash(f"An unexpected error occurred: {e}", 'error')

    return redirect(url_for('index'))


@app.route('/coverage/upload', methods=['POST'])
def upload_coverage_csv():
    """Handles CSV file upload for bulk coverage creation with per-row validation."""
    # MODIFIED: No longer gets metric_type from the form.
    return process_csv_upload(
        request.files.get('file'),
        'coverage',
        # MODIFIED: Expect 4 columns now
        ['tc_id', 'tcid_title', 'metrics', 'metric_type'],
        url_for('index')
    )


@app.route('/glean/add', methods=['POST'])
def add_glean_metric():
    """Adds a single new Glean metric."""
    try:
        # MODIFIED: Handle optional form fields
        glean_name = request.form.get('glean_name')
        metric_type = request.form.get('metric_type') or 'Uncategorized'
        description = request.form.get('description')

        if not glean_name:
            flash("Glean Name is a required field.", 'error')
            return redirect(url_for('index'))

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO glean_metrics (glean_name, metric_type, description) VALUES (?, ?, ?)",
                (glean_name, metric_type, description)
            )
        flash(f"Successfully added Glean metric: {glean_name}", 'success')
    except sqlite3.IntegrityError as e:
        flash(f"Error adding Glean metric: {e}", 'error')
    return redirect(url_for('index'))


@app.route('/legacy/add', methods=['POST'])
def add_legacy_metric():
    """Adds a single new Legacy metric."""
    try:
        # MODIFIED: Handle optional form fields
        legacy_name = request.form.get('legacy_name')
        metric_type = request.form.get('metric_type') or 'Uncategorized'
        description = request.form.get('description')

        if not legacy_name:
            flash("Legacy Name is a required field.", 'error')
            return redirect(url_for('index'))

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO legacy_metrics (legacy_name, metric_type, description) VALUES (?, ?, ?)",
                (legacy_name, metric_type, description)
            )
        flash(f"Successfully added Legacy metric: {legacy_name}", 'success')
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