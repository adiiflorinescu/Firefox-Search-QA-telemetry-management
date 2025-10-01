# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/services/database.py

import sqlite3
import re
import csv
import io
from collections import defaultdict
from itertools import product
from werkzeug.security import generate_password_hash
from ..db import get_db


# --- Private Helper Functions ---

def _strip_tcid_prefix(tcid):
    """Removes the leading 'C' from a TC ID string if present."""
    if tcid and isinstance(tcid, str) and tcid.upper().startswith('C'):
        return tcid[1:]
    return tcid


def _get_exception_tcid_set():
    """Returns a set of all non-deleted TCIDs from the exceptions table."""
    db = get_db()
    rows = db.execute("SELECT tc_id FROM exceptions WHERE is_deleted = FALSE").fetchall()
    return {row['tc_id'] for row in rows}


# --- Edit History Logging ---

def log_edit(user_id, action, table_name=None, record_pk=None, details=None):
    """Logs a modification to the edit_history table."""
    if user_id is None:
        return

    db = get_db()
    db.execute(
        "INSERT INTO edit_history (user_id, action, table_name, record_pk, details) VALUES (?, ?, ?, ?, ?)",
        (user_id, action, table_name, record_pk, details)
    )
    db.commit()  # Commit immediately after logging


def get_history(page=1, per_page=50, user_id=None, action=None, start_date=None, end_date=None, search_term=None):
    """
    Fetches a paginated and filtered list of edit history.
    """
    db = get_db()
    params = []
    where_clauses = []

    base_query = """
        SELECT h.*, u.username
        FROM edit_history h
        JOIN users u ON h.user_id = u.user_id
    """

    if user_id:
        where_clauses.append("h.user_id = ?")
        params.append(user_id)
    if action:
        where_clauses.append("h.action = ?")
        params.append(action)
    if start_date:
        where_clauses.append("h.timestamp >= ?")
        params.append(start_date)
    if end_date:
        # Add 1 day to end_date to make it inclusive
        where_clauses.append("h.timestamp < date(?, '+1 day')")
        params.append(end_date)
    if search_term:
        search_like = f"%{search_term}%"
        where_clauses.append("(h.table_name LIKE ? OR h.record_pk LIKE ? OR h.details LIKE ? OR u.username LIKE ?)")
        params.extend([search_like] * 4)

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    # Add ordering and pagination
    base_query += " ORDER BY h.timestamp DESC LIMIT ? OFFSET ?"
    params.append(per_page)
    params.append((page - 1) * per_page)

    return db.execute(base_query, params).fetchall()


def get_history_count(user_id=None, action=None, start_date=None, end_date=None, search_term=None):
    """
    Gets the total count of history items for the given filters.
    """
    db = get_db()
    params = []
    where_clauses = []

    base_query = "SELECT COUNT(h.history_id) FROM edit_history h"

    # Join is only needed if filtering by username (part of search_term)
    if search_term:
        base_query += " JOIN users u ON h.user_id = u.user_id"

    if user_id:
        where_clauses.append("h.user_id = ?")
        params.append(user_id)
    if action:
        where_clauses.append("h.action = ?")
        params.append(action)
    if start_date:
        where_clauses.append("h.timestamp >= ?")
        params.append(start_date)
    if end_date:
        where_clauses.append("h.timestamp < date(?, '+1 day')")
        params.append(end_date)
    if search_term:
        search_like = f"%{search_term}%"
        where_clauses.append("(h.table_name LIKE ? OR h.record_pk LIKE ? OR h.details LIKE ? OR u.username LIKE ?)")
        params.extend([search_like] * 4)

    if where_clauses:
        base_query += " WHERE " + " AND ".join(where_clauses)

    return db.execute(base_query, params).fetchone()[0]


def get_distinct_actions():
    """Returns a list of unique action strings from the history table."""
    db = get_db()
    return db.execute("SELECT DISTINCT action FROM edit_history WHERE action IS NOT NULL ORDER BY action").fetchall()


# --- User Management Functions ---

def get_all_users():
    """Fetches all users from the database."""
    db = get_db()
    return db.execute("SELECT user_id, username, email, role, created_at FROM users ORDER BY username").fetchall()


def get_user_by_id(user_id):
    """Fetches a single user by their ID."""
    db = get_db()
    return db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def add_user(username, email, password_hash, role, current_user_id):
    """Adds a new user to the database."""
    try:
        db = get_db()
        db.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, role)
        )
        log_edit(current_user_id, 'add_user', 'users', username, f"Role: {role}")
        return True, f"Successfully added user: {username}"
    except sqlite3.IntegrityError:
        get_db().rollback()
        return False, f"User with that username or email already exists."
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"Database error: {e}"


def update_user(user_id, form_data, current_user_id):
    """Updates a user's profile information."""
    username = form_data['username']
    email = form_data['email']
    role = form_data['role']
    password = form_data.get('password')

    if not all([username, email, role]):
        return False, "Username, Email, and Role are required."

    try:
        db = get_db()
        if password:
            password_hash = generate_password_hash(password)
            db.execute(
                "UPDATE users SET username = ?, email = ?, role = ?, password_hash = ? WHERE user_id = ?",
                (username, email, role, password_hash, user_id)
            )
            details = f"Updated user {username}. Set role to {role}. Password was changed."
        else:
            db.execute(
                "UPDATE users SET username = ?, email = ?, role = ? WHERE user_id = ?",
                (username, email, role, user_id)
            )
            details = f"Updated user {username}. Set role to {role}."

        log_edit(current_user_id, 'update_user', 'users', username, details)
        return True, f"Successfully updated user {username}."
    except sqlite3.IntegrityError:
        get_db().rollback()
        return False, "Another user with that username or email already exists."
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"A database error occurred: {e}"


def delete_user(user_id_to_delete, current_user_id):
    """Deletes a user from the database."""
    try:
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id_to_delete,)).fetchone()
        if not user:
            return False, "User not found."
        if user['role'] == 'admin':
            return False, "Admin users cannot be deleted."

        db.execute("DELETE FROM users WHERE user_id = ?", (user_id_to_delete,))
        log_edit(current_user_id, 'delete_user', 'users', user['username'], "User account deleted.")
        return True, "User deleted successfully."
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"Database error: {e}"


# --- Exception Management Functions ---

def get_all_exceptions():
    """Fetches all non-deleted exceptions from the database."""
    db = get_db()
    return db.execute("SELECT * FROM exceptions WHERE is_deleted = FALSE ORDER BY created_at DESC").fetchall()


def add_exception(form_data, user_id):
    """Adds a new TCID to the exceptions list."""
    tc_id = _strip_tcid_prefix(form_data.get('tc_id'))
    title = form_data.get('title') or None
    metrics = form_data.get('metrics') or None

    if not tc_id:
        return False, "TC ID is required to add an exception."

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO exceptions (tc_id, title, metrics, user_id) VALUES (?, ?, ?, ?)",
            (tc_id, title, metrics, user_id)
        )
        log_edit(user_id, 'add_exception', 'exceptions', tc_id, f"Reason: {title or 'N/A'}")
        conn.commit()
        return True, f"Successfully added TCID '{tc_id}' to the exception list."
    except sqlite3.IntegrityError:
        get_db().rollback()
        return False, f"TCID '{tc_id}' is already in the exception list."
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"A database error occurred: {e}"


# --- Data Fetching (Read) Functions ---

def get_metric_status_details(metric_type, metric_name):
    """
    Gathers all details for a single metric for its status page.
    """
    if metric_type not in ['glean', 'legacy']:
        return None

    db = get_db()
    exception_tcids = _get_exception_tcid_set()
    placeholders = ','.join('?' for _ in exception_tcids)

    # 1. Get primary metric details
    metric_table = f"{metric_type}_metrics"
    name_col = f"{metric_type}_name"
    metric_details = db.execute(
        f"SELECT * FROM {metric_table} WHERE {name_col} = ? AND is_deleted = FALSE",
        (metric_name,)
    ).fetchone()

    if not metric_details:
        return None  # Metric not found

    # 2. Get existing coverage, excluding excepted TCIDs
    existing_coverage_query = f"""
        SELECT c.tc_id, c.tcid_title, l.region, l.engine
        FROM coverage_to_metric_link l
        JOIN coverage c ON l.coverage_id = c.coverage_id
        WHERE l.metric_name = ?
          AND l.metric_type = ?
          AND l.is_deleted = FALSE
          AND c.is_deleted = FALSE
          AND c.tc_id NOT IN ({placeholders or '""'})
        ORDER BY c.tc_id, l.engine, l.region
    """
    params = [metric_name, metric_type.capitalize()] + list(exception_tcids)
    existing_coverage = db.execute(existing_coverage_query, params).fetchall()

    # 3. Get planned coverage
    planned_coverage = db.execute(
        "SELECT region, engine FROM planning WHERE metric_name = ? AND metric_type = ? AND is_deleted = FALSE",
        (metric_name, metric_type.capitalize())
    ).fetchall()

    return {
        'details': metric_details,
        'type': metric_type.capitalize(),
        'existing_coverage': existing_coverage,
        'planned_coverage': planned_coverage
    }


def get_supported_engines():
    """Fetches the list of supported search engines."""
    return get_db().execute("SELECT name FROM supported_engines ORDER BY name").fetchall()


def get_glean_metrics():
    """Fetches all non-deleted Glean metrics from the database."""
    db = get_db()
    return db.execute("SELECT * FROM glean_metrics WHERE is_deleted = FALSE ORDER BY glean_name").fetchall()


def get_legacy_metrics():
    """Fetches all non-deleted Legacy metrics from the database."""
    db = get_db()
    return db.execute("SELECT * FROM legacy_metrics WHERE is_deleted = FALSE ORDER BY legacy_name").fetchall()


def get_all_coverage_details():
    """
    Gathers and structures all test case coverage data, excluding excepted TCIDs.
    """
    db = get_db()
    exception_tcids = _get_exception_tcid_set()
    placeholders = ','.join('?' for _ in exception_tcids)

    query = f"""
        SELECT
            l.metric_name, l.metric_type, l.region, l.engine, c.tc_id, c.tcid_title
        FROM coverage_to_metric_link l
        JOIN coverage c ON l.coverage_id = c.coverage_id
        WHERE l.is_deleted = FALSE AND c.is_deleted = FALSE
        AND c.tc_id NOT IN ({placeholders or '""'})
        ORDER BY l.metric_name, c.tc_id, l.region, l.engine
    """
    rows = db.execute(query, list(exception_tcids)).fetchall()

    coverage_by_metric = defaultdict(list)
    for row in rows:
        key = (row['metric_name'], row['metric_type'])
        coverage_by_metric[key].append({
            'region': row['region'],
            'engine': row['engine'],
            'tc_id': row['tc_id'],
            'tcid_title': row['tcid_title']
        })

    coverage_data = []
    for (metric_name, metric_type), details in coverage_by_metric.items():
        region_count = len(set(d['region'] for d in details if d['region']))
        engine_count = len(set(d['engine'] for d in details if d['engine']))
        coverage_data.append({
            'metric_name': metric_name,
            'metric_type': metric_type,
            'details': details,
            'region_count': region_count,
            'engine_count': engine_count
        })

    metric_types_query = """
        SELECT DISTINCT metric_type as name, 'Glean' as source FROM glean_metrics WHERE metric_type IS NOT NULL
        UNION
        SELECT DISTINCT metric_type as name, 'Legacy' as source FROM legacy_metrics WHERE metric_type IS NOT NULL
        ORDER BY name
    """
    metric_types = db.execute(metric_types_query).fetchall()

    sorted_coverage_data = sorted(coverage_data, key=lambda x: x['metric_name'].lower())
    return sorted_coverage_data, metric_types


def get_planning_page_data():
    """Gathers and structures all data for the planning page, excluding excepted TCIDs."""
    db = get_db()
    exception_tcids = _get_exception_tcid_set()
    placeholders = ','.join('?' for _ in exception_tcids)

    metrics_query = """
        SELECT glean_name AS metric_name, 'Glean' AS metric_type, metric_type as specific_metric_type, priority, notes
        FROM glean_metrics WHERE is_deleted = FALSE
        UNION ALL
        SELECT legacy_name AS metric_name, 'Legacy' AS metric_type, metric_type as specific_metric_type, priority, notes
        FROM legacy_metrics WHERE is_deleted = FALSE
    """
    all_metrics = db.execute(metrics_query).fetchall()

    existing_coverage_query = f"""
        SELECT l.metric_name, l.metric_type, l.region, l.engine, c.tc_id, c.tcid_title
        FROM coverage_to_metric_link l
        JOIN coverage c ON l.coverage_id = c.coverage_id
        WHERE l.is_deleted = FALSE AND c.is_deleted = FALSE
        AND c.tc_id NOT IN ({placeholders or '""'})
    """
    existing_coverage_rows = db.execute(existing_coverage_query, list(exception_tcids)).fetchall()
    metric_to_existing_tcs = defaultdict(list)
    for row in existing_coverage_rows:
        metric_to_existing_tcs[(row['metric_name'], row['metric_type'])].append(row)

    planned_entries_query = "SELECT * FROM planning WHERE is_deleted = FALSE"
    planned_rows = db.execute(planned_entries_query).fetchall()
    metric_to_planned_tcs = defaultdict(list)
    for row in planned_rows:
        metric_to_planned_tcs[(row['metric_name'], row['metric_type'])].append(row)

    planning_data = []
    for metric in all_metrics:
        key = (metric['metric_name'], metric['metric_type'])
        existing_links = metric_to_existing_tcs.get(key, [])
        tcid_count = len(set(link['tc_id'] for link in existing_links))
        region_count = len(set(link['region'] for link in existing_links if link['region']))
        engine_count = len(set(link['engine'] for link in existing_links if link['engine']))

        planning_data.append({
            'metric_name': metric['metric_name'],
            'metric_type': metric['metric_type'],
            'specific_metric_type': metric['specific_metric_type'],
            'priority': metric['priority'],
            'notes': metric['notes'],
            'tcid_count': tcid_count,
            'region_count': region_count,
            'engine_count': engine_count,
        })

    metric_types_query = """
        SELECT DISTINCT metric_type as name, 'Glean' as source FROM glean_metrics WHERE metric_type IS NOT NULL
        UNION
        SELECT DISTINCT metric_type as name, 'Legacy' as source FROM legacy_metrics WHERE metric_type IS NOT NULL
        ORDER BY name
    """
    metric_types = db.execute(metric_types_query).fetchall()

    return {
        'planning_data': sorted(planning_data, key=lambda x: x['metric_name'].lower()),
        'metric_to_existing_tcs': metric_to_existing_tcs,
        'metric_to_planned_tcs': metric_to_planned_tcs,
        'metric_types': metric_types,
    }


def get_report_data():
    """Gathers aggregated data for the reports page, excluding excepted TCIDs."""
    db = get_db()
    exception_tcids = _get_exception_tcid_set()
    placeholders = ','.join('?' for _ in exception_tcids)

    all_metrics_query = """
        SELECT glean_name AS name, 'Glean' as type, metric_type as specific_type FROM glean_metrics WHERE is_deleted = FALSE
        UNION ALL
        SELECT legacy_name AS name, 'Legacy' as type, metric_type as specific_type FROM legacy_metrics WHERE is_deleted = FALSE
    """
    all_metrics = db.execute(all_metrics_query).fetchall()

    covered_metrics_query = f"""
        SELECT l.metric_name, l.metric_type, c.tc_id
        FROM coverage_to_metric_link l
        JOIN coverage c ON l.coverage_id = c.coverage_id
        WHERE l.is_deleted = FALSE AND c.is_deleted = FALSE
        AND c.tc_id NOT IN ({placeholders or '""'})
    """
    covered_metrics_rows = db.execute(covered_metrics_query, list(exception_tcids)).fetchall()

    metric_to_tcids = defaultdict(set)
    for row in covered_metrics_rows:
        metric_key = (row['metric_name'], row['metric_type'])
        metric_to_tcids[metric_key].add(row['tc_id'])

    report_data = []
    for metric in all_metrics:
        metric_key = (metric['name'], metric['type'])
        tcid_count = len(metric_to_tcids.get(metric_key, set()))
        is_covered = tcid_count > 0

        report_data.append({
            'name': metric['name'],
            'type': metric['type'],
            'specific_type': metric['specific_type'],
            'covered': is_covered,
            'tcid_count': tcid_count
        })

    metric_types = db.execute("""
        SELECT DISTINCT metric_type as name, 'Glean' as source FROM glean_metrics WHERE metric_type IS NOT NULL
        UNION SELECT DISTINCT metric_type as name, 'Legacy' as source FROM legacy_metrics WHERE metric_type IS NOT NULL
        ORDER BY name
    """).fetchall()

    return sorted(report_data, key=lambda x: x['name'].lower()), metric_types, metric_to_tcids


def get_general_stats():
    """Calculates high-level statistics for the reports page, excluding excepted TCIDs."""
    db = get_db()
    exception_tcids = _get_exception_tcid_set()
    placeholders = ','.join('?' for _ in exception_tcids)

    def get_covered_count(metric_type):
        query = f"""
            SELECT COUNT(DISTINCT l.metric_name)
            FROM coverage_to_metric_link l
            JOIN coverage c ON l.coverage_id = c.coverage_id
            WHERE l.metric_type = ?
              AND l.is_deleted = FALSE
              AND c.is_deleted = FALSE
              AND c.tc_id NOT IN ({placeholders or '""'})
        """
        params = [metric_type] + list(exception_tcids)
        return db.execute(query, params).fetchone()[0]

    stats = {
        'total_glean_metrics': db.execute("SELECT COUNT(*) FROM glean_metrics WHERE is_deleted = FALSE").fetchone()[0],
        'total_legacy_metrics': db.execute("SELECT COUNT(*) FROM legacy_metrics WHERE is_deleted = FALSE").fetchone()[
            0],
        'glean_covered_tcs': get_covered_count('Glean'),
        'legacy_covered_tcs': get_covered_count('Legacy'),
    }
    return stats


def get_search_suggestions():
    """Provides a list of terms for search autofill."""
    db = get_db()
    queries = [
        "SELECT glean_name FROM glean_metrics WHERE is_deleted = FALSE",
        "SELECT legacy_name FROM legacy_metrics WHERE is_deleted = FALSE",
        "SELECT tc_id FROM coverage WHERE is_deleted = FALSE",
        "SELECT region FROM coverage_to_metric_link WHERE is_deleted = FALSE AND region IS NOT NULL",
        "SELECT engine FROM coverage_to_metric_link WHERE is_deleted = FALSE AND engine IS NOT NULL",
    ]
    suggestions = set()
    for query in queries:
        for row in db.execute(query).fetchall():
            suggestions.add(row[0])
    return sorted(list(suggestions))


# --- Data Modification (Write) Functions ---

def get_single_metric(metric_type, metric_name):
    """Fetches a single metric's details for editing."""
    if metric_type not in ['glean', 'legacy']:
        return None

    table_name = f"{metric_type}_metrics"
    pk_col = f"{metric_type}_name"

    db = get_db()
    return db.execute(f"SELECT * FROM {table_name} WHERE {pk_col} = ?", (metric_name,)).fetchone()


def update_metric(metric_type, metric_name, form_data, user_id):
    """Updates the details of a specific metric."""
    if metric_type not in ['glean', 'legacy']:
        return False, "Invalid metric type specified."

    table_name = f"{metric_type}_metrics"
    pk_col = f"{metric_type}_name"

    # Extract data from the form
    new_metric_type = form_data.get('metric_type')
    new_description = form_data.get('description')
    new_expiration = form_data.get('expiration')

    try:
        db = get_db()
        db.execute(
            f"""UPDATE {table_name} SET
                metric_type = ?,
                description = ?,
                expiration = ?
            WHERE {pk_col} = ?""",
            (new_metric_type, new_description, new_expiration, metric_name)
        )
        details = (f"Type: {new_metric_type or 'N/A'}, "
                   f"Expiration: {new_expiration or 'N/A'}, "
                   f"Desc: {new_description or 'N/A'}")
        log_edit(user_id, 'update_metric', table_name, metric_name, details)
        return True, f"Successfully updated metric '{metric_name}'."
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"A database error occurred: {e}"


def update_planning_entry(data, user_id):
    """Handles all AJAX updates from the planning page."""
    action = data.get('action')
    metric_name = data.get('metric_name')
    metric_type = data.get('metric_type')

    conn = get_db()
    cursor = conn.cursor()
    target_table = 'glean_metrics' if metric_type == 'Glean' else 'legacy_metrics'
    pk_column = 'glean_name' if metric_type == 'Glean' else 'legacy_name'

    if action == 'set_priority':
        priority = data.get('priority') if data.get('priority') != '-' else None
        cursor.execute(f"UPDATE {target_table} SET priority = ? WHERE {pk_column} = ?", (priority, metric_name))
        log_edit(user_id, 'set_priority', target_table, metric_name, f"Set priority to {priority or 'None'}")

    elif action == 'save_notes':
        notes = data.get('notes')
        cursor.execute(f"UPDATE {target_table} SET notes = ? WHERE {pk_column} = ?", (notes, metric_name))
        log_edit(user_id, 'save_notes', target_table, metric_name, "Updated notes.")

    elif action == 'add_plan':
        region = data.get('region') or None
        engine = data.get('engine') or None
        cursor.execute(
            "INSERT OR IGNORE INTO planning (metric_name, metric_type, region, engine) VALUES (?, ?, ?, ?)",
            (metric_name, metric_type, region, engine))
        if cursor.rowcount > 0:
            log_edit(user_id, 'add_plan', 'planning', metric_name,
                     f"Added plan for Region: {region or 'N/A'}, Engine: {engine or 'N/A'}")
        conn.commit()
        return {'success': True, 'new_id': cursor.lastrowid}

    elif action == 'remove_plan':
        planning_id = data.get('planning_id')
        plan = cursor.execute("SELECT * FROM planning WHERE planning_id = ?", (planning_id,)).fetchone()
        if plan:
            log_edit(user_id, 'remove_plan', 'planning', plan['metric_name'], f"Removed plan ID {planning_id}")
        cursor.execute("DELETE FROM planning WHERE planning_id = ?", (planning_id,))

    elif action == 'promote_to_coverage':
        planning_id = data.get('planning_id')
        plan = cursor.execute("SELECT * FROM planning WHERE planning_id = ?", (planning_id,)).fetchone()
        if not plan: return {'success': False, 'error': 'Planning entry not found.'}

        new_tc_id = data.get('new_tc_id')
        clean_tc_id = _strip_tcid_prefix(new_tc_id)

        coverage_entry = cursor.execute("SELECT coverage_id FROM coverage WHERE tc_id = ?", (clean_tc_id,)).fetchone()
        if coverage_entry:
            coverage_id = coverage_entry['coverage_id']
        else:
            cursor.execute("INSERT INTO coverage (tc_id) VALUES (?)", (clean_tc_id,))
            coverage_id = cursor.lastrowid
            log_edit(user_id, 'add_coverage_tcid', 'coverage', clean_tc_id, "Created new TCID entry during promotion.")

        try:
            cursor.execute(
                "INSERT INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine) VALUES (?, ?, ?, ?, ?)",
                (coverage_id, plan['metric_name'], plan['metric_type'], plan['region'], plan['engine']))
            log_edit(user_id, 'promote_to_coverage', 'coverage_to_metric_link', new_tc_id,
                     f"Promoted plan for {plan['metric_name']}")
        except sqlite3.IntegrityError:
            pass

        cursor.execute("DELETE FROM planning WHERE planning_id = ?", (planning_id,))
        log_edit(user_id, 'remove_plan', 'planning', plan['metric_name'],
                 f"Removed plan ID {planning_id} after promotion.")

    conn.commit()
    return {'success': True}


def add_single_metric(metric_type, form_data, user_id):
    """Adds a single Glean or Legacy metric to the database."""
    table_name = f"{metric_type}_metrics"
    name_col = f"{metric_type}_name"
    metric_name = form_data.get(name_col)
    metric_cat = form_data.get('metric_type')
    description = form_data.get('description')
    priority = form_data.get('priority')

    if not metric_name:
        return False, f"{metric_type.capitalize()} name is required."

    try:
        conn = get_db()
        conn.execute(
            f"INSERT INTO {table_name} ({name_col}, metric_type, description, priority) VALUES (?, ?, ?, ?)",
            (metric_name, metric_cat, description, priority)
        )
        log_edit(user_id, f'add_{metric_type}_metric', table_name, metric_name,
                 f"Type: {metric_cat or 'N/A'}, Priority: {priority or 'N/A'}")
        conn.commit()
        return True, f"Successfully added {metric_type.capitalize()} metric: {metric_name}"
    except sqlite3.IntegrityError:
        get_db().rollback()
        return False, f"A {metric_type} metric with the name '{metric_name}' already exists."
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"A database error occurred: {e}"


def add_coverage_entry(form_data, user_id):
    """Adds a test case and links it to specified metrics, regions, and engines."""
    tc_id = _strip_tcid_prefix(form_data.get('tc_id'))

    exception_tcids = _get_exception_tcid_set()
    if tc_id in exception_tcids:
        return False, f"TCID '{tc_id}' is on the exception list and cannot be added."

    tcid_title = form_data.get('tcid_title')
    metric_type = form_data.get('metric_type')
    metric_names_str = form_data.get('metrics', '')
    regions_str = form_data.get('region', '')
    engines_str = form_data.get('engine', '')

    if not all([tc_id, metric_type, metric_names_str]):
        return False, "TC ID, Metric Type, and at least one Metric are required."

    metric_names = [m.strip() for m in metric_names_str.split(',') if m.strip()]
    regions = [r.strip() for r in regions_str.split(',') if r.strip()] or [None]
    engines = [e.strip() for e in engines_str.split(',') if e.strip()] or [None]

    try:
        conn = get_db()
        cursor = conn.cursor()

        table_name = f"{metric_type.lower()}_metrics"
        pk_col = f"{metric_type.lower()}_name"
        placeholders = ','.join('?' for _ in metric_names)
        existing_metrics = cursor.execute(
            f"SELECT {pk_col} FROM {table_name} WHERE {pk_col} IN ({placeholders})",
            metric_names
        ).fetchall()
        existing_metrics_set = {row[pk_col] for row in existing_metrics}

        valid_metric_names = [name for name in metric_names if name in existing_metrics_set]
        invalid_metric_names = [name for name in metric_names if name not in existing_metrics_set]

        if not valid_metric_names:
            error_msg = "No valid metrics found. The following metrics do not exist: " + ", ".join(invalid_metric_names)
            return False, error_msg

        cursor.execute("INSERT OR IGNORE INTO coverage (tc_id, tcid_title) VALUES (?, ?)", (tc_id, tcid_title))
        if cursor.rowcount > 0:
            log_edit(user_id, 'add_coverage_tcid', 'coverage', tc_id, "Created new TCID entry.")
        else:
            if tcid_title:
                cursor.execute("UPDATE coverage SET tcid_title = ? WHERE tc_id = ?", (tcid_title, tc_id))

        coverage_id = cursor.execute("SELECT coverage_id FROM coverage WHERE tc_id = ?", (tc_id,)).fetchone()[
            'coverage_id']

        all_combinations = product(valid_metric_names, regions, engines)
        for metric_name, region, engine in all_combinations:
            conn.execute("""
                INSERT OR IGNORE INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine)
                VALUES (?, ?, ?, ?, ?)""",
                         (coverage_id, metric_name, metric_type.capitalize(), region, engine))

        log_edit(user_id, 'add_coverage', 'coverage', tc_id, f"Linked to metrics: {', '.join(valid_metric_names)}")
        conn.commit()

        success_message = f"Successfully added/updated coverage for TC ID '{tc_id}' for metrics: {', '.join(valid_metric_names)}."
        if invalid_metric_names:
            success_message += f" Skipped non-existent metrics: {', '.join(invalid_metric_names)}."

        return True, success_message
    except sqlite3.Error as e:
        get_db().rollback()
        return False, f"A database error occurred: {e}"


def soft_delete_item(table_name, pk, user_id):
    """Marks an item as deleted in the specified table."""
    pk_columns = {
        'glean_metrics': 'glean_name',
        'legacy_metrics': 'legacy_name',
        'coverage': 'coverage_id',
        'coverage_to_metric_link': 'link_id',
        'exceptions': 'exception_id'
    }
    if table_name not in pk_columns:
        return False

    try:
        conn = get_db()
        conn.execute(f"UPDATE {table_name} SET is_deleted = TRUE WHERE {pk_columns[table_name]} = ?", (pk,))
        log_edit(user_id, 'soft_delete', table_name, pk, "Marked as deleted.")
        conn.commit()
        return True
    except sqlite3.Error:
        get_db().rollback()
        return False


# --- Service functions for CSV and extractions ---

def bulk_import_metrics_from_csv(metric_type, file_stream, user_id):
    """
    Bulk imports metrics from a CSV, returning a new CSV string with an 'Import Status' column.
    """
    if metric_type not in ['glean', 'legacy']:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Error", "Details", "Import Status"])
        writer.writerow(["Invalid metric type", "The system received an unsupported metric type for import.", "Error"])
        return output.getvalue(), 0, 0, 1

    conn = get_db()
    cursor = conn.cursor()
    table_name = f"{metric_type}_metrics"
    name_col = f"{metric_type}_name"

    output = io.StringIO()
    writer = csv.writer(output)

    inserted_count = 0
    duplicate_count = 0
    error_count = 0
    header = []

    try:
        content = file_stream.read().decode('utf-8-sig')
        content_stream = io.StringIO(content)
        reader = csv.reader(content_stream)
        header = [h.lower() for h in next(reader, [])]
        writer.writerow(header + ["Import Status"])

        # Find column indices, case-insensitively
        try:
            name_idx = header.index('name')
            type_idx = header.index('type')
            desc_idx = header.index('description')
            exp_idx = header.index('expiration')
        except ValueError:
            # Handle case where a required column is missing or optional one isn't there
            exp_idx = -1  # Sentinel for not found
            # Re-check for required columns to give a better error
            if 'name' not in header:
                raise ValueError("Required column 'Name' is missing from the CSV.")

        metric_name_extract_regex = re.compile(r"^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+")

        for row in reader:
            status = ""
            original_row = list(row)
            try:
                if not original_row or not original_row[0]:
                    status = "Error: Empty or malformed row."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                metric_names_str = original_row[name_idx]
                potential_metric_strings = [name.strip() for name in metric_names_str.split(',') if name.strip()]
                metric_names = [match.group(0) for s in potential_metric_strings if
                                (match := metric_name_extract_regex.match(s))]

                if not metric_names:
                    status = f"Error: No valid metric names found in '{metric_names_str}'."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                metric_cat = original_row[type_idx].strip() if type_idx < len(original_row) and original_row[
                    type_idx] else None
                description = original_row[desc_idx].strip() if desc_idx < len(original_row) and original_row[
                    desc_idx] else None

                # Handle optional expiration column
                expiration = None
                if exp_idx != -1 and exp_idx < len(original_row):
                    expiration = original_row[exp_idx].strip() or 'Not defined'

                row_successes = 0
                row_duplicates = 0
                for name in metric_names:
                    try:
                        cursor.execute(
                            f"INSERT INTO {table_name} ({name_col}, metric_type, description, expiration) VALUES (?, ?, ?, ?)",
                            (name, metric_cat, description, expiration)
                        )
                        if cursor.rowcount > 0:
                            inserted_count += 1
                            row_successes += 1
                            log_edit(user_id, f'bulk_add_{metric_type}', table_name, name,
                                     f"Type: {metric_cat}, Exp: {expiration} (from CSV)")
                    except sqlite3.IntegrityError:
                        duplicate_count += 1
                        row_duplicates += 1
                    except Exception as inner_e:
                        status = f"Error processing metric '{name}': {inner_e}"
                        error_count += 1
                        break

                if status.startswith("Error"):
                    pass
                elif row_successes > 0 and row_duplicates > 0:
                    status = f"Partial Success: {row_successes} added, {row_duplicates} duplicates."
                elif row_successes > 0:
                    status = "Success"
                elif row_duplicates > 0:
                    status = "Duplicate"
                else:
                    status = "Error: No metrics processed for this row."
                    error_count += 1
                writer.writerow(original_row + [status])
            except Exception as e:
                error_count += 1
                writer.writerow(original_row + [f"Error: {e}"])
    except Exception as e:
        error_count += 1
        if not header:
            writer.writerow(["Error", "Details", "Import Status"])
        writer.writerow(["File-level error", str(e), "Error"])
        inserted_count = 0
        duplicate_count = 0

    conn.commit()
    return output.getvalue(), inserted_count, duplicate_count, error_count


def bulk_import_coverage_from_csv(file_stream, user_id):
    """
    Bulk imports coverage from a CSV, returning a new CSV string with an 'Import Status' column.
    """
    conn = get_db()
    cursor = conn.cursor()
    exception_tcids = _get_exception_tcid_set()

    output = io.StringIO()
    writer = csv.writer(output)

    processed_count = 0
    duplicate_count = 0
    error_count = 0
    header = []

    try:
        content = file_stream.read().decode('utf-8-sig')
        content_stream = io.StringIO(content)
        reader = csv.reader(content_stream)
        header = next(reader, [])
        writer.writerow(header + ["Import Status"])

        metric_name_extract_regex = re.compile(r"^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+")

        for row in reader:
            status = ""
            original_row = list(row)
            try:
                if not original_row or len(original_row) < 4:
                    status = "Error: Row is malformed or has too few columns."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                tc_id_raw, title, metric_names_str, metric_type_raw = original_row[0], original_row[1], original_row[2], \
                original_row[3]
                tc_id = _strip_tcid_prefix(tc_id_raw.strip())
                metric_type = metric_type_raw.strip()

                if not tc_id:
                    status = "Error: TC ID is missing."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                if tc_id in exception_tcids:
                    status = f"Error: TCID '{tc_id}' is on the exception list."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                region = original_row[4].strip() if len(original_row) > 4 and original_row[4] else None
                engine = original_row[5].strip() if len(original_row) > 5 and original_row[5] else None

                potential_metric_strings = [name.strip() for name in metric_names_str.split(',') if name.strip()]
                metric_names = [match.group(0) for s in potential_metric_strings if
                                (match := metric_name_extract_regex.match(s))]

                if not all([metric_names, metric_type]):
                    status = "Error: Metric Name or Metric Type is missing."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                table_name = f"{metric_type.lower()}_metrics"
                pk_col = f"{metric_type.lower()}_name"
                placeholders = ','.join('?' for _ in metric_names)
                existing_metrics = cursor.execute(
                    f"SELECT {pk_col} FROM {table_name} WHERE {pk_col} IN ({placeholders})", metric_names
                ).fetchall()
                existing_metrics_set = {r[pk_col] for r in existing_metrics}

                valid_metric_names = [name for name in metric_names if name in existing_metrics_set]
                invalid_metric_names = [name for name in metric_names if name not in existing_metrics_set]

                if not valid_metric_names:
                    status = f"Error: No valid metrics found. Invalid: {', '.join(invalid_metric_names)}."
                    error_count += 1
                    writer.writerow(original_row + [status])
                    continue

                cursor.execute("INSERT OR IGNORE INTO coverage (tc_id, tcid_title) VALUES (?, ?)",
                               (tc_id, title.strip() if title else None))
                coverage_id = cursor.execute("SELECT coverage_id FROM coverage WHERE tc_id = ?", (tc_id,)).fetchone()[
                    'coverage_id']

                row_successes = 0
                row_duplicates = 0
                for metric_name in valid_metric_names:
                    try:
                        cursor.execute(
                            "INSERT OR IGNORE INTO coverage_to_metric_link (coverage_id, metric_name, metric_type, region, engine) VALUES (?, ?, ?, ?, ?)",
                            (coverage_id, metric_name, metric_type.capitalize(), region, engine)
                        )
                        if cursor.rowcount > 0:
                            processed_count += 1
                            row_successes += 1
                            log_edit(user_id, 'bulk_add_coverage', 'coverage_to_metric_link', tc_id,
                                     f"Linked to {metric_name} (from CSV)")
                    except sqlite3.IntegrityError:
                        duplicate_count += 1
                        row_duplicates += 1
                    except Exception as inner_e:
                        status = f"Error processing metric '{metric_name}': {inner_e}"
                        error_count += 1
                        break

                if status.startswith("Error"):
                    pass
                elif row_successes > 0:
                    status = "Success"
                    if invalid_metric_names:
                        status += f" (Skipped invalid: {', '.join(invalid_metric_names)})"
                elif row_duplicates > 0:
                    status = "Duplicate"
                else:
                    status = f"Error: All metrics for this row were invalid or skipped."
                    error_count += 1
                writer.writerow(original_row + [status])
            except Exception as e:
                error_count += 1
                writer.writerow(original_row + [f"Error: {e}"])
    except Exception as e:
        error_count += 1
        if not header:
            writer.writerow(["Error", "Details", "Import Status"])
        writer.writerow(["File-level error", str(e), "Error"])
        processed_count = 0
        duplicate_count = 0

    conn.commit()
    return output.getvalue(), processed_count, duplicate_count, error_count


def extract_probes_from_csv(file_stream):
    """Parses a TestRail CSV export to find probes, regions, and engines from any column."""
    db_engines = get_supported_engines()
    engine_names = [re.escape(engine['name']) for engine in db_engines]

    probe_regex = re.compile(r'([a-zA-Z0-9\._-]+(\.glean|\.telemetry)[a-zA-Z0-9\._-]+)')
    region_regex = re.compile(r'\b(US|DE|JP|FR|GB|IT|ES|CA|IN)\b', re.IGNORECASE)
    engine_regex = re.compile(r'\b(' + '|'.join(engine_names) + r')\b', re.IGNORECASE) if engine_names else None

    valid_metric_regex = re.compile(r"^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$")

    output = io.StringIO()
    try:
        decoded_file = io.TextIOWrapper(file_stream, 'utf-8-sig')
        reader = csv.reader(decoded_file)

        header = next(reader, [])
        new_header = header + ["Found Probes", "Found Region", "Found Engine"]
        writer = csv.writer(output)
        writer.writerow(new_header)

        for row in reader:
            text_to_search = " ".join(row)
            found_probes = set(probe_regex.findall(text_to_search))
            valid_found_probes = {p[0] for p in found_probes if valid_metric_regex.match(p[0])}
            found_regions = set(region_regex.findall(text_to_search))
            found_engines = set(engine_regex.findall(text_to_search)) if engine_regex else set()

            found_probes_str = ", ".join(sorted(valid_found_probes)) or "N/A"
            found_regions_str = ", ".join(sorted(found_regions)) or "N/A"
            found_engines_str = ", ".join(sorted(found_engines)) or "N/A"

            output_row = row + [
                found_probes_str,
                found_regions_str,
                found_engines_str
            ]
            writer.writerow(output_row)
    except Exception:
        return ""

    return output.getvalue()


def extract_from_rotation_csv(file_stream):
    """
    Extracts coverage data from a rotation CSV by column order (tcsid, title, rotation).
    Auto-detects region/engine from title and parses metrics from rotation.
    Returns a new CSV string with the extracted data.
    """
    db_engines = get_supported_engines()
    engine_names = [re.escape(engine['name']) for engine in db_engines]
    region_regex = re.compile(r'\b(US|DE|JP|FR|GB|IT|ES|CA|IN)\b', re.IGNORECASE)
    engine_regex = re.compile(r'\b(' + '|'.join(engine_names) + r')\b', re.IGNORECASE) if engine_names else None

    valid_metric_regex = re.compile(r"^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$")

    output = io.StringIO()
    try:
        decoded_file = io.TextIOWrapper(file_stream, 'utf-8-sig')
        reader = csv.reader(decoded_file)

        header = next(reader, [])
        new_header = header + ["Found Region", "Found Engine", "Found Metric Type", "Found Metrics"]
        writer = csv.writer(output)
        writer.writerow(new_header)

        for row in reader:
            try:
                title = row[1] if len(row) > 1 else ''
                rotation_str = row[2] if len(row) > 2 else ''

                region_match = region_regex.search(title)
                found_region = region_match.group(0).upper() if region_match else "N/A"

                engine_match = engine_regex.search(title) if engine_regex else None
                found_engine = engine_match.group(0).lower() if engine_match else "N/A"

                found_metric_type = "N/A"
                found_metrics = "N/A"
                if rotation_str:
                    rotation_parts = [part.strip() for part in rotation_str.split(',')]
                    if len(rotation_parts) >= 1:
                        metric_type_candidate = rotation_parts[0].strip().capitalize()
                        if metric_type_candidate in ['Glean', 'Legacy']:
                            found_metric_type = metric_type_candidate
                            potential_metrics = [name for name in rotation_parts[1:] if name]
                            valid_metrics = [m for m in potential_metrics if valid_metric_regex.match(m)]
                            found_metrics = ", ".join(valid_metrics) or "N/A"

                output_row = row + [found_region, found_engine, found_metric_type, found_metrics]
                writer.writerow(output_row)
            except IndexError:
                writer.writerow(row + ["N/A", "N/A", "N/A", "N/A"])
                continue

    except Exception:
        return ""

    return output.getvalue()