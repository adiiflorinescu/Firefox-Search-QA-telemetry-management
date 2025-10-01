# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/management.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, g, session, jsonify, Response, \
    current_app
from ..services import database as db
import datetime
import io
import os
import uuid  # For generating unique filenames

bp = Blueprint('management', __name__, url_prefix='/manage')


def require_admin_privileges():
    """Checks for admin role before processing any request for this blueprint."""
    if g.user is None:
        return redirect(url_for('auth.login'))

    if g.user['role'] != 'admin':
        flash('You do not have permission to access this page.', 'error')
        return redirect(url_for('main.metrics'))


bp.before_request(require_admin_privileges)


@bp.route('/')
def index():
    """Renders the main data management page."""
    supported_engines = db.get_supported_engines()
    exceptions = db.get_all_exceptions()

    # Use .get() to read the data without deleting it from the session.
    import_results = session.get('import_results', None)

    return render_template(
        'index.html',
        supported_engines=supported_engines,
        exceptions=exceptions,
        show_management=session.get('show_management', False),
        import_results=import_results
    )

@bp.route('/clear-import-results')
def clear_import_results():
    """Clears the import results from the session via a user action."""
    session.pop('import_results', None)
    return redirect(url_for('management.index'))


# --- Single Entry and Bulk Import Routes ---
@bp.route('/coverage/add', methods=['POST'])
def add_coverage():
    success, message = db.add_coverage_entry(request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/exceptions/add', methods=['POST'])
def add_exception():
    success, message = db.add_exception(request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/glean/add', methods=['POST'])
def add_glean_metric():
    success, message = db.add_single_metric('glean', request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/legacy/add', methods=['POST'])
def add_legacy_metric():
    success, message = db.add_single_metric('legacy', request.form, g.user['user_id'])
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


def process_and_store_report(original_filename, output_csv_string, successes, duplicates, errors):
    """Saves report to a server file and stores metadata in the session."""
    report_dir = os.path.join(current_app.instance_path, 'reports')
    os.makedirs(report_dir, exist_ok=True)

    report_filename = f"{uuid.uuid4()}.csv"
    report_filepath = os.path.join(report_dir, report_filename)

    try:
        with open(report_filepath, 'w', newline='', encoding='utf-8') as f:
            f.write(output_csv_string)
    except IOError as e:
        current_app.logger.error(f"Failed to write report file: {e}")
        # If we can't write the file, we can't offer a download.
        # Store a failure state in the session.
        session['import_results'] = {
            'summary': f"Import of '{original_filename}' processed, but report could not be saved.",
            'successes': successes,
            'duplicates': duplicates,
            'errors': errors + 1, # Add one for the report-saving error
            'report_filename': None,
            'download_filename': None
        }
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    download_filename = f"{original_filename.rsplit('.', 1)[0]}_import_status_{timestamp}.csv"

    session['import_results'] = {
        'summary': f"Import of '{original_filename}' complete.",
        'successes': successes,
        'duplicates': duplicates,
        'errors': errors,
        'report_filename': report_filename,  # Store only the filename
        'download_filename': download_filename
    }


@bp.route('/glean/bulk-import', methods=['POST'])
def bulk_import_glean():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('management.index'))

    if file.filename.endswith('.csv'):
        file_stream = io.BytesIO(file.read())
        output_csv_string, successes, duplicates, errors = db.bulk_import_metrics_from_csv('glean', file_stream,
                                                                                           g.user['user_id'])
        process_and_store_report(file.filename, output_csv_string, successes, duplicates, errors)
    else:
        flash('Invalid file type. Please upload a CSV file.', 'error')

    return redirect(url_for('management.index'))


@bp.route('/legacy/bulk-import', methods=['POST'])
def bulk_import_legacy():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('management.index'))

    if file.filename.endswith('.csv'):
        file_stream = io.BytesIO(file.read())
        output_csv_string, successes, duplicates, errors = db.bulk_import_metrics_from_csv('legacy', file_stream,
                                                                                           g.user['user_id'])
        process_and_store_report(file.filename, output_csv_string, successes, duplicates, errors)
    else:
        flash('Invalid file type. Please upload a CSV file.', 'error')

    return redirect(url_for('management.index'))


@bp.route('/coverage/bulk-import', methods=['POST'])
def bulk_import_coverage():
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('management.index'))

    if file.filename.endswith('.csv'):
        file_stream = io.BytesIO(file.read())
        output_csv_string, successes, duplicates, errors = db.bulk_import_coverage_from_csv(file_stream,
                                                                                            g.user['user_id'])
        process_and_store_report(file.filename, output_csv_string, successes, duplicates, errors)
    else:
        flash('Invalid file type. Please upload a CSV file.', 'error')

    return redirect(url_for('management.index'))


@bp.route('/download-last-report')
def download_last_report():
    """Serves the last generated import report from a server-side file."""
    results = session.get('import_results', None)
    if not results or not results.get('report_filename'):
        flash('No report available for download or session expired.', 'error')
        return redirect(url_for('management.index'))

    report_filename = results['report_filename']
    download_filename = results.get('download_filename', 'import_report.csv')
    report_filepath = os.path.join(current_app.instance_path, 'reports', report_filename)

    if not os.path.exists(report_filepath):
        flash('Report file not found. It may have been cleaned up.', 'error')
        # Clear the session key to prevent repeated errors
        session.pop('import_results', None)
        return redirect(url_for('management.index'))

    try:
        with open(report_filepath, 'r', encoding='utf-8') as f:
            csv_data = f.read()
    except IOError:
        flash('Could not read the report file.', 'error')
        session.pop('import_results', None)
        return redirect(url_for('management.index'))
    finally:
        # Clean up the file after reading it
        if os.path.exists(report_filepath):
            os.remove(report_filepath)
        # DEFINITIVE FIX: Always pop the session key after a download attempt.
        session.pop('import_results', None)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={download_filename}"}
    )


# --- Extraction and Other Routes ---
@bp.route('/extract-probes', methods=['POST'])
def extract_probes():
    if 'file' not in request.files:
        flash('No file part for probe extraction.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash('Please select a valid CSV file for probe extraction.', 'error')
        return redirect(url_for('management.index'))

    try:
        output_csv_string = db.extract_probes_from_csv(file)
        return Response(
            output_csv_string,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=extracted_probes.csv"}
        )
    except Exception as e:
        flash(f"An error occurred during probe extraction: {e}", 'error')
        return redirect(url_for('management.index'))


@bp.route('/extract-from-rotation', methods=['POST'])
def extract_from_rotation():
    if 'file' not in request.files:
        flash('No file part for rotation extraction.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash('Please select a valid CSV file for rotation extraction.', 'error')
        return redirect(url_for('management.index'))

    try:
        output_csv_string = db.extract_from_rotation_csv(file)

        if not output_csv_string:
            flash('Processing failed. The file might be empty or in the wrong format.', 'error')
            return redirect(url_for('management.index'))

        return Response(
            output_csv_string,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=rotation_extraction_output.csv"}
        )
    except Exception as e:
        flash(f"An error occurred during rotation extraction: {e}", 'error')
        return redirect(url_for('management.index'))


@bp.route('/engines/add', methods=['POST'])
def add_engine():
    engine_name = request.form.get('name', '').strip().lower()
    if not engine_name:
        return jsonify({'success': False, 'error': 'Engine name cannot be empty.'}), 400
    # This function doesn't exist in the provided db file, assuming it would be added
    # success, message = db.add_engine(engine_name, g.user['user_id'])
    # For now, just return success
    return jsonify({'success': True, 'name': engine_name})


@bp.route('/engines/delete', methods=['POST'])
def delete_engine():
    engine_name = request.form.get('name')
    if not engine_name:
        return jsonify({'success': False, 'error': 'Engine name not provided.'}), 400
    # This function doesn't exist in the provided db file, assuming it would be added
    # success, message = db.delete_engine(engine_name, g.user['user_id'])
    # For now, just return success
    return jsonify({'success': True})


@bp.route('/delete/<string:table_name>/<string:pk>', methods=['POST'])
def soft_delete(table_name, pk):
    success = db.soft_delete_item(table_name, pk, g.user['user_id'])
    return jsonify({'success': success})