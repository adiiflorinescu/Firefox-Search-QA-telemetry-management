# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/services/database.py

import sqlite3
import re  # Import re for the prefix stripper
from flask import current_app
from collections import defaultdict


def get_db_connection():
    """Creates a connection to the SQLite database."""
    conn = sqlite3.connect(current_app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


# --- Helper to be used internally ---
def _strip_tcid_prefix(tcid):
    if not tcid or not isinstance(tcid, str):
        return tcid
    match = re.search(r'\d', tcid)
    return tcid[match.start():] if match else tcid


# --- Metric & Coverage Read Operations ---

def get_glean_metrics():
    """Fetches all non-deleted Glean metrics."""
    with get_db_connection() as conn:
        return conn.execute('SELECT * FROM glean_metrics WHERE is_deleted = FALSE ORDER BY glean_name').fetchall()


def get_legacy_metrics():
    """Fetches all non-deleted Legacy metrics."""
    with get_db_connection() as conn:
        return conn.execute('SELECT * FROM legacy_metrics WHERE is_deleted = FALSE ORDER BY legacy_name').fetchall()


def get_all_coverage_details():
    """Fetches and groups all coverage data for the main metrics view."""
    query = """
        WITH MetricDetails AS (
            SELECT l.metric_name, l.metric_type, c.tc_id, l.region, l.engine
            FROM coverage_to_metric_link l
            JOIN coverage c ON l.coverage_id = c.coverage_id
            WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE
        ),
        MetricCounts AS (
            SELECT metric_name, metric_type, COUNT(DISTINCT region) as region_count, COUNT(DISTINCT engine) as engine_count
            FROM MetricDetails GROUP BY metric_name, metric_type
        )
        SELECT mc.metric_name, mc.metric_type, mc.region_count, mc.engine_count, md.tc_id, md.region, md.engine
        FROM MetricCounts mc
        JOIN MetricDetails md ON mc.metric_name = md.metric_name AND mc.metric_type = md.metric_type
        ORDER BY mc.metric_name, mc.metric_type,
                 CASE WHEN md.engine IS NULL OR md.engine = '' or md.engine = 'NoEngine' THEN 1 ELSE 0 END, md.engine,
                 CASE WHEN md.region IS NULL OR md.region = '' or md.region = 'NoRegion' THEN 1 ELSE 0 END, md.region;
    """
    with get_db_connection() as conn:
        raw_data = conn.execute(query).fetchall()

    coverage_grouped = defaultdict(lambda: {'region_count': 0, 'engine_count': 0, 'details': []})
    for row in raw_data:
        key = (row['metric_name'], row['metric_type'])
        metric = coverage_grouped[key]
        if not metric['details']:
            metric['region_count'] = row['region_count']
            metric['engine_count'] = row['engine_count']
        metric['details'].append(dict(row))

    return [{'metric_name': k[0], 'metric_type': k[1], **v} for k, v in sorted(coverage_grouped.items())]


# --- Reports Page Operations ---

def get_report_data():
    """Fetches aggregated data for the reports page."""
    query = """
        SELECT metric_name, metric_type, COUNT(link_id) as tcid_count
        FROM coverage_to_metric_link WHERE is_deleted = FALSE
        GROUP BY metric_name, metric_type ORDER BY metric_name, metric_type;
    """
    with get_db_connection() as conn:
        return conn.execute(query).fetchall()


def get_metric_to_tcid_map():
    """Fetches a dictionary mapping metrics to their TCIDs."""
    query = """
        SELECT c.tc_id, c.tcid_title, l.metric_name, l.metric_type, l.region, l.engine
        FROM coverage c JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
        WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE;
    """
    metric_to_tcids = defaultdict(list)
    with get_db_connection() as conn:
        for row in conn.execute(query).fetchall():
            key = (row['metric_name'], row['metric_type'])
            tcid_info = (row['tc_id'], row['tcid_title'], row['region'], row['engine'])
            metric_to_tcids[key].append(tcid_info)
    return metric_to_tcids


def get_general_stats():
    """Fetches general statistics for the reports dashboard."""
    with get_db_connection() as conn:
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


# --- Planning Page Operations ---

def get_planning_page_data():
    """Fetches and processes all data needed for the coverage planning page."""
    with get_db_connection() as conn:
        all_metrics = conn.execute("""
            SELECT glean_name as name, 'Glean' as type, priority FROM glean_metrics WHERE is_deleted = FALSE
            UNION ALL
            SELECT legacy_name as name, 'Legacy' as type, priority FROM legacy_metrics WHERE is_deleted = FALSE
        """).fetchall()

        coverage_data = conn.execute("""
            SELECT c.tc_id, l.metric_name, l.metric_type, l.region, l.engine
            FROM coverage c JOIN coverage_to_metric_link l ON c.coverage_id = l.coverage_id
            WHERE c.is_deleted = FALSE AND l.is_deleted = FALSE;
        """).fetchall()

        planning_entries = conn.execute("SELECT * FROM planning WHERE is_deleted = FALSE").fetchall()

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
            'priority': metric['priority'],
            'tcid_count': len(existing_tcs),
            'region_count': len({tc['region'] for tc in existing_tcs if tc.get('region')}),
            'engine_count': len({tc['engine'] for tc in existing_tcs if tc.get('engine')})
        })

    return planning_data, metric_to_existing_tcs, metric_to_planned_tcs


def update_planning_entry(data):
    """Handles all AJAX updates from the planning page."""
    action = data.get('action')
    metric_name = data.get('metric_name')
    metric_type = data.get('metric_type')

    with get_db_connection() as conn:
        cursor = conn.cursor()
        if action == 'set_priority':
            target_table = 'glean_metrics' if metric_type == 'glean' else 'legacy_metrics'
            pk_column = 'glean_name' if metric_type == 'glean' else 'legacy_name'
            cursor.execute(f"UPDATE {target_table} SET priority = ? WHERE {pk_column} = ?",
                           (data.get('priority') if data.get('priority') != '-' else None, metric_name))
        elif action == 'add_plan':
            cursor.execute(
                "INSERT OR IGNORE INTO planning (metric_name, metric_type, region, engine) VALUES (?, ?, ?, ?)",
                (metric_name, metric_type, data.get('region') or None, data.get('engine') or None))
            # We must commit here to get the lastrowid
            conn.commit()
            return {'success': True, 'new_id': cursor.lastrowid}
        elif action == 'remove_plan':
            cursor.execute("DELETE FROM planning WHERE planning_id = ?", (data.get('planning_id'),))
        elif action == 'promote_to_coverage':
            plan = cursor.execute("SELECT * FROM planning WHERE planning_id = ?", (data.get('planning_id'),)).fetchone()
            if not plan: return {'success': False, 'error': 'Planning entry not found.'}

            # --- DEFINITIVE FIX: Clean the TCID on the backend ---
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
                pass  # Ignore if it already exists

            cursor.execute("DELETE FROM planning WHERE planning_id = ?", (data.get('planning_id'),))

        conn.commit()
    return {'success': True}


# --- Data Write/Delete Operations ---

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
        with get_db_connection() as conn:
            conn.execute(
                f"INSERT INTO {table_name} ({name_col}, metric_type, description, priority) VALUES (?, ?, ?, ?)",
                (metric_name, metric_cat, description, priority)
            )
            conn.commit()
        return True, f"Successfully added {metric_type.capitalize()} metric: {metric_name}"
    except sqlite3.IntegrityError as e:
        return False, f"Error adding {metric_type.capitalize()} metric: {e}"


def add_coverage_entry(form_data):
    """Adds a new coverage entry and links it to metrics."""
    tc_id = form_data.get('tc_id')
    metric_type = form_data.get('metric_type')
    metrics_str = form_data.get('metrics')

    if not all([tc_id, metric_type, metrics_str]):
        return False, 'TC ID, Metric Type, and at least one Metric are required.'

    metric_names = [m.strip() for m in metrics_str.split(',') if m.strip()]
    if not metric_names:
        return False, 'At least one valid metric name is required.'

    try:
        with get_db_connection() as conn:
            # Check if all metrics exist
            val_table_name = 'glean_metrics' if metric_type == 'glean' else 'legacy_metrics'
            val_column_name = 'glean_name' if metric_type == 'glean' else 'legacy_name'
            for metric in metric_names:
                metric_exists = conn.execute(
                    f"SELECT 1 FROM {val_table_name} WHERE {val_column_name} = ? AND is_deleted = FALSE",
                    (metric,)
                ).fetchone()
                if not metric_exists:
                    return False, f"Error: The {metric_type} metric '{metric}' does not exist. Please add it first."

            # Upsert coverage entry
            coverage_entry = conn.execute("SELECT coverage_id FROM coverage WHERE tc_id = ?", (tc_id,)).fetchone()
            if coverage_entry:
                coverage_id = coverage_entry['coverage_id']
                conn.execute("UPDATE coverage SET tcid_title = ? WHERE coverage_id = ?",
                             (form_data.get('tcid_title') or None, coverage_id))
            else:
                cursor = conn.execute("INSERT INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                                      (tc_id, form_data.get('tcid_title') or None))
                coverage_id = cursor.lastrowid

            # Insert links
            for metric in metric_names:
                conn.execute("""
                    INSERT OR IGNORE INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine)
                    VALUES (?, ?, ?, ?, ?)""",
                             (coverage_id, metric, metric_type, form_data.get('region') or None,
                              form_data.get('engine') or None))
            conn.commit()
        return True, f"Successfully added/updated coverage for TC ID '{tc_id}'."
    except sqlite3.Error as e:
        return False, f"Database Error: Could not add entry. (Details: {e})"


def soft_delete_item(table_name, pk):
    """Marks an item as deleted in the database."""
    pk_columns = {'glean_metrics': 'glean_name', 'legacy_metrics': 'legacy_name'}
    if table_name not in pk_columns: return False

    with get_db_connection() as conn:
        conn.execute(f"UPDATE {table_name} SET is_deleted = TRUE WHERE {pk_columns[table_name]} = ?", (pk,))
        conn.commit()
    return True


def get_search_suggestions(suggestion_type):
    """Provides a JSON list of search terms for autofill."""
    with get_db_connection() as conn:
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