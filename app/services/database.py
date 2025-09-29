# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/services/database.py

import sqlite3
import re
from flask import current_app
from collections import defaultdict
from itertools import product
from app.db import get_db # Import the new get_db function


def get_db_connection():
    """
    DEPRECATED: This function is replaced by the app-context-aware get_db().
    Keeping it here to avoid breaking old code, but new code should use get_db().
    """
    return get_db()


# --- Helper to be used internally ---
def _strip_tcid_prefix(tcid):
    if not tcid or not isinstance(tcid, str):
        return tcid
    match = re.search(r'\d', tcid)
    return tcid[match.start():] if match else tcid


# --- NEW: Helper to fetch metric types ---
def _get_all_metric_types(conn):
    """Fetches and formats all distinct metric types from both tables."""
    glean_types = conn.execute("SELECT DISTINCT metric_type FROM glean_metrics WHERE is_deleted = FALSE").fetchall()
    legacy_types = conn.execute("SELECT DISTINCT metric_type FROM legacy_metrics WHERE is_deleted = FALSE").fetchall()

    all_metric_types = []
    all_metric_types.extend([{'name': row['metric_type'], 'source': 'Glean'} for row in glean_types if row['metric_type']])
    all_metric_types.extend([{'name': row['metric_type'], 'source': 'Legacy'} for row in legacy_types if row['metric_type']])
    return sorted(all_metric_types, key=lambda x: x['name'])


def get_glean_metrics():
    """Fetches all non-deleted Glean metrics."""
    conn = get_db()
    return conn.execute('SELECT * FROM glean_metrics WHERE is_deleted = FALSE ORDER BY glean_name').fetchall()


def get_legacy_metrics():
    """Fetches all non-deleted Legacy metrics."""
    conn = get_db()
    return conn.execute('SELECT * FROM legacy_metrics WHERE is_deleted = FALSE ORDER BY legacy_name').fetchall()


def get_all_coverage_details():
    """
    Fetches and groups all coverage data for the main metrics view.
    Also returns a list of all distinct metric types for filtering.
    """
    # --- DEFINITIVE FIX: Refactored query for robustness and clarity ---
    query = """
        WITH MetricDetails AS (
            SELECT
                l.metric_name,
                l.metric_type as general_metric_type,
                COALESCE(gm.metric_type, lm.metric_type) as specific_metric_type,
                c.tc_id,
                l.region,
                l.engine
            FROM coverage_to_metric_link l
            JOIN coverage c ON l.coverage_id = c.coverage_id
            LEFT JOIN glean_metrics gm ON l.metric_name = gm.glean_name AND l.metric_type = 'glean'
            LEFT JOIN legacy_metrics lm ON l.metric_name = lm.legacy_name AND l.metric_type = 'legacy'
            WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE
        ),
        MetricCounts AS (
            SELECT
                metric_name,
                general_metric_type,
                COUNT(DISTINCT region) as region_count,
                COUNT(DISTINCT engine) as engine_count
            FROM MetricDetails
            GROUP BY metric_name, general_metric_type
        )
        SELECT
            mc.metric_name,
            mc.general_metric_type,
            md.specific_metric_type,
            mc.region_count,
            mc.engine_count,
            md.tc_id,
            md.region,
            md.engine
        FROM MetricCounts mc
        JOIN MetricDetails md ON mc.metric_name = md.metric_name AND mc.general_metric_type = md.general_metric_type
        ORDER BY
            mc.metric_name,
            mc.general_metric_type,
            -- Use COALESCE to treat NULL/empty as a high value for sorting, putting them last
            COALESCE(NULLIF(md.engine, ''), 'zzzz'),
            COALESCE(NULLIF(md.region, ''), 'zzzz');
    """
    conn = get_db()
    raw_data = conn.execute(query).fetchall()
    sorted_metric_types = _get_all_metric_types(conn)

    coverage_grouped = defaultdict(lambda: {'region_count': 0, 'engine_count': 0, 'details': [], 'specific_metric_type': 'N/A'})
    for row in raw_data:
        key = (row['metric_name'], row['general_metric_type'])
        metric = coverage_grouped[key]
        if not metric['details']:
            metric['region_count'] = row['region_count']
            metric['engine_count'] = row['engine_count']
            metric['specific_metric_type'] = row['specific_metric_type'] or 'N/A'
        metric['details'].append(dict(row))

    sorted_coverage = [{'metric_name': k[0], 'metric_type': v['specific_metric_type'], 'general_metric_type': k[1], **v} for k, v in sorted(coverage_grouped.items())]

    return sorted_coverage, sorted_metric_types


def get_report_data():
    """Fetches aggregated data for the reports page."""
    conn = get_db()
    query = """
        SELECT metric_name, metric_type, COUNT(link_id) as tcid_count
        FROM coverage_to_metric_link WHERE is_deleted = FALSE
        GROUP BY metric_name, metric_type ORDER BY metric_name, metric_type;
    """
    report_data = conn.execute(query).fetchall()
    metric_types = _get_all_metric_types(conn)
    return report_data, metric_types


def get_planning_page_data():
    """Fetches and processes all data needed for the coverage planning page."""
    conn = get_db()
    all_metrics = conn.execute("""
        SELECT glean_name as name, 'Glean' as type, priority, notes, metric_type as specific_metric_type
        FROM glean_metrics WHERE is_deleted = FALSE
        UNION ALL
        SELECT legacy_name as name, 'Legacy' as type, priority, notes, metric_type as specific_metric_type
        FROM legacy_metrics WHERE is_deleted = FALSE
    """).fetchall()

    coverage_data = conn.execute("""
        SELECT c.tc_id, l.metric_name, l.metric_type, l.region, l.engine
        FROM coverage c JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE;
    """).fetchall()

    planning_entries = conn.execute("SELECT * FROM planning WHERE is_deleted = FALSE").fetchall()
    metric_types = _get_all_metric_types(conn)

    metric_to_existing_tcs = defaultdict(list)
    for row in coverage_data:
        metric_to_existing_tcs[(row['metric_name'], row['metric_type'])].append(dict(row))

    metric_to_planned_tcs = defaultdict(list)
    for entry in planning_entries:
        if not entry['tc_id']:
            metric_to_planned_tcs[(entry['metric_name'], entry['metric_type'].lower())].append(dict(entry))

    planning_data = []
    for metric in sorted(all_metrics, key=lambda x: x['name']):
        key = (metric['name'], metric['type'].lower())
        existing_tcs = metric_to_existing_tcs.get(key, [])
        planning_data.append({
            'metric_name': metric['name'],
            'metric_type': metric['type'],
            'specific_metric_type': metric['specific_metric_type'] or 'N/A',
            'priority': metric['priority'],
            'notes': metric['notes'],
            'tcid_count': len(existing_tcs),
            'region_count': len({tc['region'] for tc in existing_tcs if tc.get('region')}),
            'engine_count': len({tc['engine'] for tc in existing_tcs if tc.get('engine')})
        })

    return planning_data, metric_to_existing_tcs, metric_to_planned_tcs, metric_types


def get_metric_to_tcid_map():
    """Fetches a dictionary mapping metrics to their TCIDs."""
    query = """
        SELECT c.tc_id, c.tcid_title, l.metric_name, l.metric_type, l.region, l.engine
        FROM coverage c JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE;
    """
    metric_to_tcids = defaultdict(list)
    conn = get_db()
    for row in conn.execute(query).fetchall():
        key = (row['metric_name'], row['metric_type'])
        tcid_info = (row['tc_id'], row['tcid_title'], row['region'], row['engine'])
        metric_to_tcids[key].append(tcid_info)
    return metric_to_tcids


def get_general_stats():
    """Fetches general statistics for the reports dashboard."""
    conn = get_db()
    return {
        'total_glean_metrics':
            conn.execute("SELECT COUNT(*) FROM glean_metrics WHERE is_deleted = FALSE").fetchone()[0],
        'total_legacy_metrics':
            conn.execute("SELECT COUNT(*) FROM legacy_metrics WHERE is_deleted = FALSE").fetchone()[0],
        'glean_covered_tcs': conn.execute(
            "SELECT COUNT(DISTINCT coverage_id) FROM coverage_to_metric_link WHERE metric_type = 'glean'").fetchone()[
            0],
        'legacy_covered_tcs': conn.execute(
            "SELECT COUNT(DISTINCT coverage_id) FROM coverage_to_metric_link WHERE metric_type = 'legacy'").fetchone()[
            0]
    }


def update_planning_entry(data):
    """Handles all AJAX updates from the planning page."""
    action = data.get('action')
    metric_name = data.get('metric_name')
    metric_type = data.get('metric_type')

    conn = get_db()
    cursor = conn.cursor()
    target_table = 'glean_metrics' if metric_type == 'glean' else 'legacy_metrics'
    pk_column = 'glean_name' if metric_type == 'glean' else 'legacy_name'

    if action == 'set_priority':
        cursor.execute(f"UPDATE {target_table} SET priority = ? WHERE {pk_column} = ?",
                       (data.get('priority') if data.get('priority') != '-' else None, metric_name))
    elif action == 'save_notes':
        cursor.execute(f"UPDATE {target_table} SET notes = ? WHERE {pk_column} = ?",
                       (data.get('notes'), metric_name))
    elif action == 'add_plan':
        cursor.execute(
            "INSERT OR IGNORE INTO planning (metric_name, metric_type, region, engine) VALUES (?, ?, ?, ?)",
            (metric_name, metric_type, data.get('region') or None, data.get('engine') or None))
        conn.commit()
        return {'success': True, 'new_id': cursor.lastrowid}
    elif action == 'remove_plan':
        cursor.execute("DELETE FROM planning WHERE planning_id = ?", (data.get('planning_id'),))
    elif action == 'promote_to_coverage':
        plan = cursor.execute("SELECT * FROM planning WHERE planning_id = ?", (data.get('planning_id'),)).fetchone()
        if not plan: return {'success': False, 'error': 'Planning entry not found.'}

        clean_tc_id = _strip_tcid_prefix(data.get('new_tc_id'))

        coverage_entry = cursor.execute("SELECT coverage_id FROM coverage WHERE tc_id = ?",
                                        (clean_tc_id,)).fetchone()
        if coverage_entry:
            coverage_id = coverage_entry['coverage_id']
        else:
            cursor.execute("INSERT INTO coverage (tc_id) VALUES (?)", (clean_tc_id,))
            coverage_id = cursor.lastrowid

        try:
            cursor.execute(
                "INSERT INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine) VALUES (?, ?, ?, ?, ?)",
                (coverage_id, plan['metric_name'], plan['metric_type'], plan['region'], plan['engine']))
        except sqlite3.IntegrityError:
            pass

        cursor.execute("DELETE FROM planning WHERE planning_id = ?", (data.get('planning_id'),))

    conn.commit()
    return {'success': True}


def add_single_metric(metric_type, form_data):
    """Adds a single new Glean or Legacy metric from form data."""
    table_name = f"{metric_type}_metrics"
    name_col = f"{metric_type}_name"
    metric_name = form_data.get(name_col)
    metric_cat = form_data.get('metric_type') or 'Uncategorized'
    description = form_data.get('description')
    priority = form_data.get('priority')

    if not metric_name:
        return False, f"{metric_type.capitalize()} Name is a required field."

    try:
        conn = get_db()
        conn.execute(
            f"INSERT INTO {table_name} ({name_col}, metric_type, description, priority) VALUES (?, ?, ?, ?)",
            (metric_name, metric_cat, description, priority)
        )
        conn.commit()
        return True, f"Successfully added {metric_type.capitalize()} metric: {metric_name}"
    except sqlite3.IntegrityError as e:
        return False, f"Error adding {metric_type.capitalize()} metric: {e}"


def add_coverage_entry(form_data):
    """
    Adds a new coverage entry and links it to metrics.
    Handles comma-separated values for metrics, regions, and engines.
    """
    tc_id = form_data.get('tc_id')
    metric_type = form_data.get('metric_type')

    metrics_str = form_data.get('metrics', '')
    regions_str = form_data.get('region', '')
    engines_str = form_data.get('engine', '')

    if not all([tc_id, metric_type, metrics_str]):
        return False, 'TC ID, Metric Type, and at least one Metric are required.'

    metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]
    regions = [r.strip() for r in regions_str.split(',') if r.strip()]
    engines = [e.strip() for e in engines_str.split(',') if e.strip()]

    if not metric_names:
        return False, 'At least one valid metric name is required.'
    if not regions:
        regions = [None]
    if not engines:
        engines = [None]

    try:
        conn = get_db()
        val_table_name = 'glean_metrics' if metric_type == 'glean' else 'legacy_metrics'
        val_column_name = 'glean_name' if metric_type == 'glean' else 'legacy_name'
        for metric in metric_names:
            metric_exists = conn.execute(
                f"SELECT 1 FROM {val_table_name} WHERE {val_column_name} = ? AND is_deleted = FALSE",
                (metric,)
            ).fetchone()
            if not metric_exists:
                return False, f"Error: The {metric_type} metric '{metric}' does not exist. Please add it first."

        coverage_entry = conn.execute("SELECT coverage_id FROM coverage WHERE tc_id = ?", (tc_id,)).fetchone()
        if coverage_entry:
            coverage_id = coverage_entry['coverage_id']
            conn.execute("UPDATE coverage SET tcid_title = ? WHERE coverage_id = ?",
                         (form_data.get('tcid_title') or None, coverage_id))
        else:
            cursor = conn.execute("INSERT INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                                  (tc_id, form_data.get('tcid_title') or None))
            coverage_id = cursor.lastrowid

        all_combinations = product(metric_names, regions, engines)

        for metric_name, region, engine in all_combinations:
            conn.execute("""
                INSERT OR IGNORE INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine)
                VALUES (?, ?, ?, ?, ?)""",
                         (coverage_id, metric_name, metric_type, region, engine))

        conn.commit()
        return True, f"Successfully added/updated coverage for TC ID '{tc_id}'."
    except sqlite3.Error as e:
        current_app.logger.error(f"Database error in add_coverage_entry: {e}")
        return False, f"Database Error: Could not add entry. (Details: {e})"


def soft_delete_item(table_name, pk):
    """Marks an item as deleted in the database."""
    pk_columns = {'glean_metrics': 'glean_name', 'legacy_metrics': 'legacy_name'}
    if table_name not in pk_columns: return False

    conn = get_db()
    conn.execute(f"UPDATE {table_name} SET is_deleted = TRUE WHERE {pk_columns[table_name]} = ?", (pk,))
    conn.commit()
    return True


def get_search_suggestions(suggestion_type):
    """Provides a JSON list of search terms for autofill."""
    conn = get_db()
    suggestions = []
    if suggestion_type in ['all', 'glean', 'metrics']:
        suggestions.extend([r['glean_name'] for r in
                            conn.execute('SELECT glean_name FROM glean_metrics WHERE is_deleted = FALSE')])
    if suggestion_type in ['all', 'legacy', 'metrics']:
        suggestions.extend([r['legacy_name'] for r in
                            conn.execute('SELECT legacy_name FROM legacy_metrics WHERE is_deleted = FALSE')])
    if suggestion_type == 'all':
        suggestions.extend(
            [r['tc_id'] for r in conn.execute('SELECT DISTINCT tc_id FROM coverage WHERE is_deleted = FALSE')])
    return sorted(list(set(suggestions)))

# --- NEW FUNCTIONS FOR ENGINE MANAGEMENT ---

def get_supported_engines():
    """Fetches all supported engines from the database."""
    conn = get_db()
    return conn.execute('SELECT name FROM supported_engines ORDER BY name').fetchall()

def add_engine(engine_name):
    """Adds a new supported engine to the database."""
    try:
        conn = get_db()
        conn.execute("INSERT INTO supported_engines (name) VALUES (?)", (engine_name,))
        conn.commit()
        return True, f"Successfully added engine: {engine_name}"
    except sqlite3.IntegrityError:
        return False, f"Engine '{engine_name}' already exists."
    except sqlite3.Error as e:
        current_app.logger.error(f"Database error in add_engine: {e}")
        return False, f"Database error: {e}"

def delete_engine(engine_name):
    """Deletes a supported engine from the database."""
    try:
        conn = get_db()
        conn.execute("DELETE FROM supported_engines WHERE name = ?", (engine_name,))
        conn.commit()
        return True, f"Successfully deleted engine: {engine_name}"
    except sqlite3.Error as e:
        current_app.logger.error(f"Database error in delete_engine: {e}")
        return False, f"Database error: {e}"
