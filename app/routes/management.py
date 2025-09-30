# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/management.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, g, session, jsonify, Response
from ..services import database as db

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
    return render_template(
        'index.html',
        supported_engines=supported_engines,
        exceptions=exceptions,
        show_management=session.get('show_management', False)
    )


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


def handle_file_upload(metric_type):
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('management.index'))
    if file and file.filename.endswith('.csv'):
        count, errors = db.bulk_import_metrics_from_csv(metric_type, file, g.user['user_id'])
        flash(
            f"Bulk Import Complete: Added {count} new {metric_type.capitalize()} metrics. Encountered {errors} errors/duplicates.",
            'success')
    else:
        flash('Invalid file type. Please upload a CSV file.', 'error')
    return redirect(url_for('management.index'))


@bp.route('/glean/bulk-import', methods=['POST'])
def bulk_import_glean():
    return handle_file_upload('glean')


@bp.route('/legacy/bulk-import', methods=['POST'])
def bulk_import_legacy():
    return handle_file_upload('legacy')


@bp.route('/coverage/bulk-import', methods=['POST'])
def bulk_import_coverage():
    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('management.index'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('management.index'))
    if file and file.filename.endswith('.csv'):
        count, errors = db.bulk_import_coverage_from_csv(file, g.user['user_id'])
        flash(f"Bulk Import Complete: Processed {count} coverage links. Encountered {errors} errors (including exceptions).", 'success')
    else:
        flash('Invalid file type. Please upload a CSV file.', 'error')
    return redirect(url_for('management.index'))


# --- Extraction and Import Routes ---
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


# --- Other Routes ---
@bp.route('/engines/add', methods=['POST'])
def add_engine():
    engine_name = request.form.get('name', '').strip().lower()
    if not engine_name:
        return jsonify({'success': False, 'error': 'Engine name cannot be empty.'}), 400
    success, message = db.add_engine(engine_name, g.user['user_id'])
    if success:
        return jsonify({'success': True, 'name': engine_name})
    else:
        return jsonify({'success': False, 'error': message}), 409


@bp.route('/engines/delete', methods=['POST'])
def delete_engine():
    engine_name = request.form.get('name')
    if not engine_name:
        return jsonify({'success': False, 'error': 'Engine name not provided.'}), 400
    success, message = db.delete_engine(engine_name, g.user['user_id'])
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': message}), 500


@bp.route('/delete/<string:table_name>/<string:pk>', methods=['POST'])
def soft_delete(table_name, pk):
    success = db.soft_delete_item(table_name, pk, g.user['user_id'])
    return jsonify({'success': success})