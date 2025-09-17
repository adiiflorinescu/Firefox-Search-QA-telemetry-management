# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app.py

import sqlite3
import os
import csv
import io
import re
from flask import Flask, jsonify, render_template, request, flash, redirect, url_for, session, Response
from collections import defaultdict
from dotenv import load_dotenv
import logging

# --- Setup Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

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


# --- Custom Template Filters ---
@app.template_filter('strip_tcid_prefix')
def strip_tcid_prefix(tcid):
    """
    A Jinja2 filter that removes leading non-numeric characters from a TCID string.
    e.g., 'C12345' -> '12345', 'TC12345' -> '12345'
    """
    if not tcid or not isinstance(tcid, str):
        return tcid
    match = re.search(r'\d', tcid)
    return tcid[match.start():] if match else tcid

# --- NEW: Custom sort filter for planning sub-table ---
@app.template_filter('sort_details')
def sort_details(details):
    """
    Sorts a list of TCID details (dictionaries) for the planning sub-table.
    - Sorts by engine, then region.
    - 'NoEngine' and 'NoRegion' are sorted last.
    """
    def sort_key(item):
        engine = item.get('engine')
        region = item.get('region')
        # Sort key: (is_NoEngine, engine_name, is_NoRegion, region_name)
        # This places 'NoEngine'/'NoRegion' at the end of their respective groups.
        return (
            engine is None or engine == 'NoEngine',
            engine,
            region is None or region == 'NoRegion',
            region
        )
    return sorted(details, key=sort_key)


# --- Generic CSV Upload Logic ---
def process_csv_upload(file, table_name, columns, redirect_url):
    """
    Generic function to process a CSV file upload and store results in session.
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
        stream_content = file.stream.read().decode("UTF8")

        # This local import is fine for this structure
        from db.import_data import get_csv_stream_from_content
        with get_csv_stream_from_content(stream_content, table_name, len(columns)) as csv_stream:
            csv_reader = csv.reader(csv_stream)
            header = next(csv_reader)

            with get_db_connection() as conn:
                cursor = conn.cursor()

                if table_name == 'coverage':
                    for i, row in enumerate(csv_reader, 2):
                        if len(row) != len(columns):
                            skipped_rows.append(
                                f"Line {i}: Incorrect column count. Expected {len(columns)}, got {len(row)}.")
                            continue

                        tc_id, tcid_title, metrics_str, metric_type, region, engine = (
                            row[0], row[1], row[2], row[3].lower().strip(), row[4], row[5]
                        )
                        metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]

                        if not tc_id or not metric_names:
                            skipped_rows.append(f"Line {i}: TC ID and at least one metric are required.")
                            continue

                        if metric_type not in ['glean', 'legacy']:
                            skipped_rows.append(
                                f"Line {i} (TCID: {tc_id}): Invalid metric_type '{row[3]}'. Must be 'glean' or 'legacy'.")
                            continue

                        try:
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
                                continue

                            cursor.execute("SAVEPOINT csv_row;")

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

                            # Insert with the metric_type into the link table.
                            for metric in metric_names:
                                try:
                                    cursor.execute(
                                        """INSERT INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine)
                                           VALUES (?, ?, ?, ?, ?)""",
                                        (coverage_id, metric, metric_type, region or None, engine or None)
                                    )
                                except sqlite3.IntegrityError:
                                    # This combination already exists, which is fine. Just skip it.
                                    pass

                            cursor.execute("RELEASE SAVEPOINT csv_row;")
                            inserted_count += 1
                        except sqlite3.Error as e:
                            cursor.execute("ROLLBACK TO SAVEPOINT csv_row;")
                            skipped_rows.append(f"Line {i} (TCID: {tc_id}): Database error - {e}")

                else:  # Logic for Glean/Legacy uploads
                    placeholders = ', '.join(['?'] * len(columns))
                    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders});"

                    for i, row in enumerate(csv_reader, 2):
                        if not row or not row[0].strip():
                            skipped_rows.append(f"Line {i}: Skipped because the metric name is missing.")
                            continue

                        padded_row = (row + [None] * len(columns))[:len(columns)]
                        row_values = list(padded_row)

                        if not row_values[1] or not row_values[1].strip():
                            row_values[1] = 'Uncategorized'

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
    coverage_upload_results = session.pop('coverage_upload_results', None)
    glean_upload_results = session.pop('glean_metrics_upload_results', None)
    legacy_upload_results = session.pop('legacy_metrics_upload_results', None)

    return render_template(
        'index.html',
        coverage_upload_results=coverage_upload_results,
        glean_upload_results=glean_upload_results,
        legacy_upload_results=legacy_upload_results,
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

    # This query is now much simpler because the link table has all the info.
    coverage_query = """
        WITH MetricDetails AS (
            SELECT
                l.metric_name,
                l.metric_type,
                c.tc_id,
                l.region,
                l.engine
            FROM coverage_to_metric_link l
            JOIN coverage c ON l.coverage_id = c.coverage_id
            WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE
        ),
        MetricCounts AS (
            SELECT
                metric_name,
                metric_type,
                COUNT(DISTINCT region) as region_count,
                COUNT(DISTINCT engine) as engine_count,
                COUNT(tc_id) as tcid_count
            FROM MetricDetails
            GROUP BY metric_name, metric_type
        )
        SELECT
            mc.metric_name,
            mc.metric_type,
            mc.region_count,
            mc.engine_count,
            mc.tcid_count,
            md.tc_id,
            md.region,
            md.engine
        FROM MetricCounts mc
        JOIN MetricDetails md ON mc.metric_name = md.metric_name AND mc.metric_type = md.metric_type
        ORDER BY
            mc.metric_name,
            mc.metric_type,
            CASE WHEN md.engine IS NULL OR md.engine = '' or md.engine = 'NoEngine' THEN 1 ELSE 0 END,
            md.engine,
            CASE WHEN md.region IS NULL OR md.region = '' or md.region = 'NoRegion' THEN 1 ELSE 0 END,
            md.region;
    """
    raw_coverage_data = conn.execute(coverage_query).fetchall()
    conn.close()

    # Group the pre-sorted data by a (metric_name, metric_type) tuple
    coverage_grouped = defaultdict(lambda: {'region_count': 0, 'engine_count': 0, 'tcid_count': 0, 'details': []})
    for row in raw_coverage_data:
        key = (row['metric_name'], row['metric_type'])
        metric = coverage_grouped[key]

        if not metric['details']:  # Set counts only on the first item
            metric['region_count'] = row['region_count']
            metric['engine_count'] = row['engine_count']
            metric['tcid_count'] = row['tcid_count']

        metric['details'].append(dict(row))

    # Convert defaultdict to a list of dicts for the template
    coverage = [
        {'metric_name': key[0], 'metric_type': key[1], **value}
        for key, value in sorted(coverage_grouped.items())
    ]

    return render_template(
        'metrics.html',
        glean_metrics=glean_metrics,
        legacy_metrics=legacy_metrics,
        coverage=coverage,
        coverage_count=len(coverage),
        glean_count=len(glean_metrics),
        legacy_count=len(legacy_metrics),
        tc_base_url=config.TC_BASE_URL,
        show_management=session.get('show_management', False)
    )


# --- Metric Reports Page Route ---
@app.route('/reports')
def reports():
    """Renders the new metric reports page with aggregated data."""
    conn = get_db_connection()

    total_glean_metrics = conn.execute("SELECT COUNT(*) FROM glean_metrics WHERE is_deleted = FALSE").fetchone()[0]
    total_legacy_metrics = conn.execute("SELECT COUNT(*) FROM legacy_metrics WHERE is_deleted = FALSE").fetchone()[0]

    glean_covered_tcs = conn.execute(
        "SELECT COUNT(DISTINCT coverage_id) FROM coverage_to_metric_link WHERE metric_type = 'glean'").fetchone()[0]
    legacy_covered_tcs = conn.execute(
        "SELECT COUNT(DISTINCT coverage_id) FROM coverage_to_metric_link WHERE metric_type = 'legacy'").fetchone()[0]

    # The main report query is now simpler and more accurate
    report_query = """
        SELECT
            metric_name,
            metric_type,
            COUNT(link_id) as tcid_count
        FROM coverage_to_metric_link
        WHERE is_deleted = FALSE
        GROUP BY metric_name, metric_type
        ORDER BY metric_name, metric_type;
    """
    report_data = conn.execute(report_query).fetchall()

    # The details query is also simpler
    coverage_data_query = """
        SELECT c.tc_id, c.tcid_title, l.metric_name, l.metric_type, l.region, l.engine
        FROM coverage c
        JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE;
    """
    coverage_data = conn.execute(coverage_data_query).fetchall()

    # Use a (name, type) tuple as the key
    metric_to_tcids = defaultdict(list)
    for row in coverage_data:
        key = (row['metric_name'], row['metric_type'])
        tcid_info = (row['tc_id'], row['tcid_title'], row['region'], row['engine'])
        metric_to_tcids[key].append(tcid_info)

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
        show_management=session.get('show_management', False)
    )


# --- Coverage Planning Routes ---
@app.route('/planning')
def planning():
    """Renders the new Coverage Planning page."""
    logging.debug("--- Starting planning() route ---")
    conn = get_db_connection()

    # 1. Get all metrics first. This is our base list.
    all_metrics_query = """
        SELECT glean_name as name, 'Glean' as type FROM glean_metrics WHERE is_deleted = FALSE
        UNION ALL
        SELECT legacy_name as name, 'Legacy' as type FROM legacy_metrics WHERE is_deleted = FALSE
    """
    all_metrics = conn.execute(all_metrics_query).fetchall()
    logging.debug(f"Step 1: Found {len(all_metrics)} total metrics.")

    # 2. Get all existing coverage links.
    coverage_data_query = """
        SELECT c.tc_id, l.metric_name, l.metric_type, l.region, l.engine
        FROM coverage c
        JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE;
    """
    coverage_data = conn.execute(coverage_data_query).fetchall()
    logging.debug(f"Step 2: Found {len(coverage_data)} existing coverage links.")

    # 3. Get all planned entries.
    planning_entries_query = "SELECT * FROM planning WHERE is_deleted = FALSE"
    planning_entries = conn.execute(planning_entries_query).fetchall()
    logging.debug(f"Step 3: Found {len(planning_entries)} planning entries.")
    conn.close()

    # --- Process data in Python for clarity and correctness ---
    logging.debug("Step 4: Processing data into dictionaries...")

    # 4a. Create dictionary for existing TCIDs.
    metric_to_existing_tcs = defaultdict(list)
    for row in coverage_data:
        # The metric_type from the link table is already lowercase.
        key = (row['metric_name'], row['metric_type'])
        metric_to_existing_tcs[key].append(dict(row))

    # 4b. Create dictionaries for planned TCIDs and priorities.
    metric_to_planned_tcs = defaultdict(list)
    metric_to_priority = {}
    for entry in planning_entries:
        metric_type = entry['metric_type']
        if metric_type:
            # Normalize to lowercase to match existing_tcs keys
            key = (entry['metric_name'], metric_type.lower())
            if entry['priority']:
                metric_to_priority[key] = entry['priority']
            # A planned entry is any entry that does NOT have a TCID.
            if not entry['tc_id']:
                metric_to_planned_tcs[key].append(dict(entry))

    logging.debug(f"Processed {len(metric_to_existing_tcs)} metrics with existing coverage.")
    logging.debug(f"Processed {len(metric_to_planned_tcs)} metrics with planned entries.")

    # 5. Build the final `planning_data` list for the main grid.
    logging.debug("Step 5: Building final planning_data for template...")
    planning_data = []
    for metric in sorted(all_metrics, key=lambda x: x['name']):
        # The key for lookup must be normalized to lowercase to match the dictionary keys.
        key = (metric['name'], metric['type'].lower())
        existing_tcs = metric_to_existing_tcs.get(key, [])

        # The counts for the main grid should ONLY reflect existing coverage.
        regions = {tc['region'] for tc in existing_tcs if tc.get('region')}
        engines = {tc['engine'] for tc in existing_tcs if tc.get('engine')}

        data_point = {
            'metric_name': metric['name'],
            'metric_type': metric['type'], # Keep original case for display
            'tcid_count': len(existing_tcs),
            'region_count': len(regions),
            'engine_count': len(engines)
        }
        planning_data.append(data_point)

        # Log the data for the first few metrics to verify
        if len(planning_data) <= 5:
            logging.debug(f"Built data point: {data_point}")

    logging.debug("--- Finished planning() route ---")
    return render_template(
        'planning.html',
        planning_data=planning_data,
        metric_to_existing_tcs=metric_to_existing_tcs,
        metric_to_planned_tcs=metric_to_planned_tcs,
        metric_to_priority=metric_to_priority,
        tc_base_url=config.TC_BASE_URL,
        show_management=session.get('show_management', False)
    )


@app.route('/planning/update', methods=['POST'])
def update_planning_entry():
    """Adds/updates/deletes a planning entry via AJAX."""
    data = request.get_json()
    action = data.get('action')
    metric_name = data.get('metric_name')
    metric_type = data.get('metric_type')  # Now passed from frontend

    if not metric_name or not metric_type:
        return jsonify({'success': False, 'error': 'Metric name and type are required.'}), 400

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if action == 'set_priority':
                priority = data.get('priority')
                cursor.execute("""
                    INSERT INTO planning (metric_name, metric_type, priority) VALUES (?, ?, ?)
                    ON CONFLICT(metric_name, metric_type) WHERE tc_id IS NULL
                    DO UPDATE SET priority=excluded.priority;
                """, (metric_name, metric_type, priority if priority != '-' else None))

            elif action == 'add_plan':
                region = data.get('region') or None
                engine = data.get('engine') or None

                if not region and not engine:
                    return jsonify(
                        {'success': False, 'error': 'At least a Region or Engine is required to add a plan.'}), 400

                cursor.execute("""
                    INSERT OR IGNORE INTO planning (metric_name, metric_type, tc_id, region, engine)
                    VALUES (?, ?, ?, ?, ?)
                """, (metric_name, metric_type, None, region, engine))

                new_id = cursor.lastrowid
                return jsonify({'success': True, 'new_id': new_id})

            elif action == 'remove_plan':
                planning_id = data.get('planning_id')
                cursor.execute("DELETE FROM planning WHERE planning_id = ?", (planning_id,))

            elif action == 'promote_to_coverage':
                planning_id = data.get('planning_id')
                new_tc_id = data.get('new_tc_id')

                if not new_tc_id:
                    return jsonify(
                        {'success': False, 'error': 'A valid TC ID is required to promote to coverage.'}), 400

                plan = cursor.execute("SELECT * FROM planning WHERE planning_id = ?", (planning_id,)).fetchone()
                if not plan:
                    return jsonify({'success': False, 'error': 'Planning entry not found.'}), 404

                coverage_entry = cursor.execute(
                    "SELECT coverage_id FROM coverage WHERE tc_id = ? AND is_deleted = FALSE", (new_tc_id,)
                ).fetchone()

                if coverage_entry:
                    coverage_id = coverage_entry['coverage_id']
                else:
                    cursor.execute("INSERT INTO coverage (tc_id) VALUES (?)", (new_tc_id,))
                    coverage_id = cursor.lastrowid

                try:
                    cursor.execute(
                        """INSERT INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine)
                           VALUES (?, ?, ?, ?, ?)""",
                        (coverage_id, plan['metric_name'], plan['metric_type'], plan['region'], plan['engine'])
                    )
                except sqlite3.IntegrityError:
                    pass  # Already exists, which is fine.

                cursor.execute("DELETE FROM planning WHERE planning_id = ?", (planning_id,))

            return jsonify({'success': True})

    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- Probe Extraction Route ---
@app.route('/extract-probes', methods=['POST'])
def extract_probes():
    """
    Handles file upload, extracts telemetry probes, regions, and engines,
    and returns a new CSV file.
    """
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected for probe extraction.', 'error')
        return redirect(url_for('index'))
    if not file.filename.endswith('.csv'):
        flash('Invalid file type. Please upload a .csv file.', 'error')
        return redirect(url_for('index'))

    probe_regex = re.compile(r'(?:browser|urlbar|contextservices)\.[\w.-]+')
    region_regex = re.compile(r'\b(US|DE|CA|CN)\b', re.IGNORECASE)
    engine_regex = re.compile(r'(google|duckduckgo|ecosia|qwant|bing|wikipedia|baidu)', re.IGNORECASE)

    try:
        stream_content = file.stream.read().decode("UTF8")
        infile = io.StringIO(stream_content)
        reader = csv.reader(infile)

        outfile = io.StringIO()
        writer = csv.writer(outfile)

        header = next(reader)
        writer.writerow(header + ['Found Probes', 'Found Region', 'Found Engine'])

        try:
            title_col_index = header.index('Title')
            steps_col_index = header.index('Steps')
            expected_steps_col_index = header.index('Steps (Expected Result)')
        except ValueError as e:
            flash(f"Error processing CSV: Missing required column in header - {e}", 'error')
            return redirect(url_for('index'))

        for row in reader:
            if len(row) <= max(title_col_index, steps_col_index, expected_steps_col_index):
                writer.writerow(row + ['malformed row', '', ''])
                continue

            title_text = row[title_col_index]
            steps_text = row[steps_col_index] + " " + row[expected_steps_col_index]

            found_probes = set(probe_regex.findall(steps_text))
            probes_result = ', '.join(sorted(list(found_probes))) if found_probes else 'nothing found'

            found_region = region_regex.search(title_text)
            region_result = found_region.group(1).upper() if found_region else 'NoRegion'

            found_engine = engine_regex.search(title_text)
            engine_result = found_engine.group(1).lower() if found_engine else 'NoEngine'

            writer.writerow(row + [probes_result, region_result, engine_result])

        output = outfile.getvalue()
        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=extract_data_with_probes.csv"}
        )

    except Exception as e:
        flash(f"An unexpected error occurred during probe extraction: {e}", 'error')
        return redirect(url_for('index'))


# --- Soft Delete Route ---
@app.route('/delete/<string:table_name>/<string:pk>', methods=['POST'])
def soft_delete(table_name, pk):
    """Marks an item as deleted in the database."""
    pk_columns = {
        'coverage': 'link_id',
        'glean_metrics': 'glean_name',
        'legacy_metrics': 'legacy_name'
    }

    if table_name not in pk_columns:
        return jsonify({'success': False, 'error': 'Invalid table name'}), 400

    pk_column = pk_columns[table_name]
    target_table = 'coverage_to_metric_link' if table_name == 'coverage' else table_name

    try:
        with get_db_connection() as conn:
            if table_name == 'coverage':
                conn.execute(f"UPDATE {target_table} SET is_deleted = TRUE WHERE {pk_column} = ?", (pk,))
            else:
                conn.execute(f"UPDATE {target_table} SET is_deleted = TRUE WHERE {pk_column} = ?", (pk,))
        return jsonify({'success': True})
    except sqlite3.Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# --- Toggle Management View Route ---
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
    region = request.form.get('region')
    engine = request.form.get('engine')
    metric_type = request.form.get('metric_type')
    metrics_str = request.form.get('metrics')

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
            cursor.execute("BEGIN;")

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
                flash(
                    f"Error: The following {metric_type} metrics do not exist: {', '.join(non_existent_metrics)}. Please add them first.",
                    'error')
                cursor.execute("ROLLBACK;")
                return redirect(url_for('index'))

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

            # Insert with the metric_type into the link table.
            for metric in metric_names:
                try:
                    cursor.execute(
                        """INSERT INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine)
                           VALUES (?, ?, ?, ?, ?)""",
                        (coverage_id, metric, metric_type, region or None, engine or None)
                    )
                except sqlite3.IntegrityError:
                    # This combination already exists, which is fine. Just skip it.
                    pass

            cursor.execute("COMMIT;")

        flash(f"Successfully added/updated coverage for TC ID '{tc_id}'.", 'success')

    except sqlite3.Error as e:
        cursor.execute("ROLLBACK;")
        flash(f"Database Error: Could not add entry. (Details: {e})", 'error')
    except Exception as e:
        cursor.execute("ROLLBACK;")
        flash(f"An unexpected error occurred: {e}", 'error')

    return redirect(url_for('index'))


@app.route('/coverage/upload', methods=['POST'])
def upload_coverage_csv():
    """Handles CSV file upload for bulk coverage creation with per-row validation."""
    return process_csv_upload(
        request.files.get('file'),
        'coverage',
        ['tc_id', 'tcid_title', 'metrics', 'metric_type', 'region', 'engine'],
        url_for('index')
    )


@app.route('/glean/add', methods=['POST'])
def add_glean_metric():
    """Adds a single new Glean metric."""
    try:
        glean_name = request.form.get('glean_name')
        metric_type_form = request.form.get('metric_type') or 'Uncategorized'
        description = request.form.get('description')

        if not glean_name:
            flash("Glean Name is a required field.", 'error')
            return redirect(url_for('index'))

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO glean_metrics (glean_name, metric_type, description) VALUES (?, ?, ?)",
                (glean_name, metric_type_form, description)
            )
        flash(f"Successfully added Glean metric: {glean_name}", 'success')
    except sqlite3.IntegrityError as e:
        flash(f"Error adding Glean metric: {e}", 'error')
    return redirect(url_for('index'))


@app.route('/legacy/add', methods=['POST'])
def add_legacy_metric():
    """Adds a single new Legacy metric."""
    try:
        legacy_name = request.form.get('legacy_name')
        metric_type_form = request.form.get('metric_type') or 'Uncategorized'
        description = request.form.get('description')

        if not legacy_name:
            flash("Legacy Name is a required field.", 'error')
            return redirect(url_for('index'))

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO legacy_metrics (legacy_name, metric_type, description) VALUES (?, ?, ?)",
                (legacy_name, metric_type_form, description)
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