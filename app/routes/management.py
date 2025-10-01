# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/management.py

from flask import (
    Blueprint, flash, g, redirect, render_template, request, url_for, session,
    make_response, current_app
)
from werkzeug.security import generate_password_hash

from ..services import database as db
from ..utils.decorators import admin_required
import os
import datetime

bp = Blueprint('management', __name__, url_prefix='/manage')


@bp.route('/')
@admin_required
def index():
    """Renders the main data management page."""
    import_results = session.get('import_results')
    return render_template(
        'index.html',
        supported_engines=db.get_supported_engines(),
        exceptions=db.get_all_exceptions(),
        import_results=import_results
    )


@bp.route('/clear-import-results')
@admin_required
def clear_import_results():
    """Clears the import results from the session."""
    if 'import_results' in session:
        # Clean up the report file if it exists
        results = session.pop('import_results')
        if results.get('report_filename'):
            try:
                os.remove(os.path.join(current_app.instance_path, results['report_filename']))
            except OSError:
                pass  # Ignore if file doesn't exist
    return redirect(url_for('management.index'))


@bp.route('/download-last-report')
@admin_required
def download_last_report():
    """Downloads the last generated import report."""
    import_results = session.get('import_results')
    if not import_results or not import_results.get('report_filename'):
        flash('No report available for download.', 'error')
        return redirect(url_for('management.index'))

    try:
        with open(os.path.join(current_app.instance_path, import_results['report_filename']), 'r') as f:
            csv_content = f.read()
    except FileNotFoundError:
        flash('Report file not found. It may have been cleared.', 'error')
        return redirect(url_for('management.index'))

    response = make_response(csv_content)
    response.headers["Content-Disposition"] = f"attachment; filename=import_report_{import_results['timestamp']}.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


# --- Metric Management ---

@bp.route('/add/glean', methods=['POST'])
@admin_required
def add_glean_metric():
    """Handles the form submission for adding a new Glean metric."""
    success, message = db.add_single_metric('glean', request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/add/legacy', methods=['POST'])
@admin_required
def add_legacy_metric():
    """Handles the form submission for adding a new Legacy metric."""
    success, message = db.add_single_metric('legacy', request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/edit/<string:metric_type>/<path:metric_name>', methods=['GET', 'POST'])
@admin_required
def edit_metric(metric_type, metric_name):
    """Displays a form to edit a metric and handles the update."""
    if metric_type not in ['glean', 'legacy']:
        flash('Invalid metric type specified.', 'error')
        return redirect(url_for('main.metrics'))

    if request.method == 'POST':
        success, message = db.update_metric(metric_type, metric_name, request.form, g.user['user_id'])
        flash(message, 'success' if success else 'error')
        return redirect(url_for('main.metrics'))

    metric = db.get_single_metric(metric_type, metric_name)
    if not metric:
        flash(f"Metric '{metric_name}' not found.", 'error')
        return redirect(url_for('main.metrics'))

    return render_template('edit_metric.html', metric=metric, metric_type=metric_type)


@bp.route('/bulk-import/glean', methods=['POST'])
@admin_required
def bulk_import_glean():
    """Handles the bulk import of Glean metrics from a CSV file."""
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected for uploading.', 'error')
        return redirect(url_for('management.index'))

    if file and file.filename.endswith('.csv'):
        report_content, successes, duplicates, errors = db.bulk_import_metrics_from_csv('glean', file.stream,
                                                                                        g.user['user_id'])

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        report_filename = f"report_{timestamp}.csv"
        with open(os.path.join(current_app.instance_path, report_filename), 'w', newline='', encoding='utf-8') as f:
            f.write(report_content)

        summary = f"Import complete: {successes} new metrics added, {duplicates} duplicates found, and {errors} errors encountered."
        session['import_results'] = {
            'summary': summary,
            'successes': successes,
            'duplicates': duplicates,
            'errors': errors,
            'report_filename': report_filename,
            'timestamp': timestamp
        }
        flash(summary, 'success' if errors == 0 else 'error')
    else:
        flash('Invalid file type. Please upload a .csv file.', 'error')

    return redirect(url_for('management.index'))


@bp.route('/bulk-import/legacy', methods=['POST'])
@admin_required
def bulk_import_legacy():
    """Handles the bulk import of Legacy metrics from a CSV file."""
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected for uploading.', 'error')
        return redirect(url_for('management.index'))

    if file and file.filename.endswith('.csv'):
        report_content, successes, duplicates, errors = db.bulk_import_metrics_from_csv('legacy', file.stream,
                                                                                        g.user['user_id'])

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        report_filename = f"report_{timestamp}.csv"
        with open(os.path.join(current_app.instance_path, report_filename), 'w', newline='', encoding='utf-8') as f:
            f.write(report_content)

        summary = f"Import complete: {successes} new metrics added, {duplicates} duplicates found, and {errors} errors encountered."
        session['import_results'] = {
            'summary': summary,
            'successes': successes,
            'duplicates': duplicates,
            'errors': errors,
            'report_filename': report_filename,
            'timestamp': timestamp
        }
        flash(summary, 'success' if errors == 0 else 'error')
    else:
        flash('Invalid file type. Please upload a .csv file.', 'error')

    return redirect(url_for('management.index'))


# --- Coverage Management ---

@bp.route('/add/coverage', methods=['POST'])
@admin_required
def add_coverage():
    """Handles the form submission for adding a new coverage entry."""
    success, message = db.add_coverage_entry(request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/bulk-import/coverage', methods=['POST'])
@admin_required
def bulk_import_coverage():
    """Handles the bulk import of coverage data from a CSV file."""
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected for uploading.', 'error')
        return redirect(url_for('management.index'))

    if file and file.filename.endswith('.csv'):
        report_content, successes, duplicates, errors = db.bulk_import_coverage_from_csv(file.stream, g.user['user_id'])

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        report_filename = f"report_{timestamp}.csv"
        with open(os.path.join(current_app.instance_path, report_filename), 'w', newline='', encoding='utf-8') as f:
            f.write(report_content)

        summary = f"Import complete: {successes} new links created, {duplicates} duplicates found, and {errors} errors encountered."
        session['import_results'] = {
            'summary': summary,
            'successes': successes,
            'duplicates': duplicates,
            'errors': errors,
            'report_filename': report_filename,
            'timestamp': timestamp
        }
        flash(summary, 'success' if errors == 0 else 'error')
    else:
        flash('Invalid file type. Please upload a .csv file.', 'error')

    return redirect(url_for('management.index'))


# --- Exception Management ---

@bp.route('/add/exceptions', methods=['POST'])
@admin_required
def add_exception():
    """Handles adding a new TCID to the exception list."""
    success, message = db.add_exception(request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/delete/exceptions/<int:exception_id>', methods=['POST'])
@admin_required
def delete_exception(exception_id):
    """Handles soft-deleting an exception."""
    if db.soft_delete_item('exceptions', exception_id, g.user['user_id']):
        return {'success': True}
    return {'success': False, 'error': 'Could not delete the exception.'}


# --- Engine Management ---

@bp.route('/add/engine', methods=['POST'])
@admin_required
def add_engine():
    """Adds a new supported engine."""
    # This is a simplified example; you might want more robust handling
    engine_name = request.form.get('name')
    if engine_name:
        try:
            conn = db.get_db()
            conn.execute("INSERT INTO supported_engines (name) VALUES (?)", (engine_name,))
            conn.commit()
            db.log_edit(g.user['user_id'], 'add_engine', 'supported_engines', engine_name)
        except conn.IntegrityError:
            pass  # Ignore if it already exists
    return redirect(url_for('management.index'))


@bp.route('/delete/engine', methods=['POST'])
@admin_required
def delete_engine():
    """Deletes a supported engine."""
    engine_name = request.form.get('name')
    if engine_name:
        conn = db.get_db()
        conn.execute("DELETE FROM supported_engines WHERE name = ?", (engine_name,))
        conn.commit()
        db.log_edit(g.user['user_id'], 'delete_engine', 'supported_engines', engine_name)
    return redirect(url_for('management.index'))


# --- Generic Deletion ---

@bp.route('/delete/<table>/<path:pk>', methods=['POST'])
@admin_required
def delete_item(table, pk):
    """Handles soft-deleting a generic item from various tables."""
    if db.soft_delete_item(table, pk, g.user['user_id']):
        return {'success': True}
    return {'success': False, 'error': f'Could not delete the item from {table}.'}


# --- Extraction Tools ---

@bp.route('/extract-probes', methods=['POST'])
@admin_required
def extract_probes():
    """Extracts probes from a TestRail CSV export."""
    if 'file' not in request.files or not request.files['file'].filename:
        flash('No file provided for probe extraction.', 'error')
        return redirect(url_for('management.index'))

    file = request.files['file']
    if file and file.filename.endswith('.csv'):
        csv_output = db.extract_probes_from_csv(file.stream)
        if not csv_output:
            flash('Could not process the file. It might be empty or malformed.', 'error')
            return redirect(url_for('management.index'))

        response = make_response(csv_output)
        response.headers["Content-Disposition"] = "attachment; filename=extracted_probes.csv"
        response.headers["Content-Type"] = "text/csv"
        return response
    else:
        flash('Invalid file type. Please upload a .csv file.', 'error')
        return redirect(url_for('management.index'))


@bp.route('/extract-from-rotation', methods=['POST'])
@admin_required
def extract_from_rotation():
    """Extracts coverage data from a rotation CSV."""
    if 'file' not in request.files or not request.files['file'].filename:
        flash('No file provided for rotation extraction.', 'error')
        return redirect(url_for('management.index'))

    file = request.files['file']
    if file and file.filename.endswith('.csv'):
        csv_output = db.extract_from_rotation_csv(file.stream)
        if not csv_output:
            flash('Could not process the file. It might be empty or malformed.', 'error')
            return redirect(url_for('management.index'))

        response = make_response(csv_output)
        response.headers["Content-Disposition"] = "attachment; filename=extracted_rotation_coverage.csv"
        response.headers["Content-Type"] = "text/csv"
        return response
    else:
        flash('Invalid file type. Please upload a .csv file.', 'error')
        return redirect(url_for('management.index'))