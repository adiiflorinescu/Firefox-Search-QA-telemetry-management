# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/management.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, Response
from ..services import database as db
from ..utils import helpers
import re
import csv
import io

bp = Blueprint('management', __name__)


@bp.route('/manage')
def index():
    """Renders the main data management page."""
    coverage_upload_results = session.pop('coverage_upload_results', None)
    glean_upload_results = session.pop('glean_metrics_upload_results', None)
    legacy_upload_results = session.pop('legacy_metrics_upload_results', None)

    # Fetch the list of supported engines to display on the page
    supported_engines = db.get_supported_engines()

    return render_template(
        'index.html',
        coverage_upload_results=coverage_upload_results,
        glean_upload_results=glean_upload_results,
        legacy_upload_results=legacy_upload_results,
        supported_engines=supported_engines,  # Pass engines to the template
        show_management=session.get('show_management', False)
    )


# ... (existing routes for add_coverage, add_glean_metric, etc. remain unchanged) ...
@bp.route('/coverage/add', methods=['POST'])
def add_coverage():
    success, message = db.add_coverage_entry(request.form)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/glean/add', methods=['POST'])
def add_glean_metric():
    success, message = db.add_single_metric('glean', request.form)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/legacy/add', methods=['POST'])
def add_legacy_metric():
    success, message = db.add_single_metric('legacy', request.form)
    flash(message, 'success' if success else 'error')
    return redirect(url_for('management.index'))


@bp.route('/coverage/upload', methods=['POST'])
def upload_coverage_csv():
    message, category = helpers.process_csv_upload(
        request.files.get('file'),
        'coverage',
        ['tc_id', 'tcid_title', 'metrics', 'metric_type', 'region', 'engine'],
        url_for('management.index')
    )
    flash(message, category)
    return redirect(url_for('management.index'))


@bp.route('/glean/upload', methods=['POST'])
def upload_glean_csv():
    message, category = helpers.process_csv_upload(
        request.files.get('file'),
        'glean_metrics',
        ['glean_name', 'metric_type', 'expiration', 'description', 'search_metric', 'legacy_correspondent', 'priority'],
        url_for('management.index')
    )
    flash(message, category)
    return redirect(url_for('management.index'))


@bp.route('/legacy/upload', methods=['POST'])
def upload_legacy_csv():
    message, category = helpers.process_csv_upload(
        request.files.get('file'),
        'legacy_metrics',
        ['legacy_name', 'metric_type', 'expiration', 'description', 'search_metric', 'glean_correspondent', 'priority'],
        url_for('management.index')
    )
    flash(message, category)
    return redirect(url_for('management.index'))


@bp.route('/extract-probes', methods=['POST'])
def extract_probes():
    file = request.files.get('file')
    if not file or not file.filename:
        flash('No file selected for probe extraction.', 'error')
        return redirect(url_for('management.index'))

    output_csv, message, category = helpers.extract_probes_from_csv(file)

    if output_csv is None:
        flash(message, category)
        return redirect(url_for('management.index'))

    return Response(
        output_csv,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=extract_data_with_probes.csv"}
    )


def _parse_rotation_csv(file_stream):
    """
    Parses a CSV with 'ID', 'Title', 'rotation' to extract structured data.
    """
    # --- MODIFICATION START: Dynamically build engine pattern ---
    engines = db.get_supported_engines()
    if not engines:
        # Fallback or raise an error if no engines are configured
        engine_pattern = re.compile(r'a^', re.IGNORECASE)  # A pattern that never matches
    else:
        # Escape engine names to be safe in regex and join with |
        engine_list_pattern = '|'.join(re.escape(engine['name']) for engine in engines)
        engine_pattern = re.compile(fr'\b({engine_list_pattern})\b', re.IGNORECASE)
    # --- MODIFICATION END ---

    # Flexible regex patterns to find common regions.
    region_pattern = re.compile(r'\b(US|EU|APAC|DE|UK|FR)\b', re.IGNORECASE)

    reader = csv.DictReader(io.TextIOWrapper(file_stream, 'utf-8'))

    # Make the check case-insensitive by converting all fieldnames to lowercase
    fieldnames_lower = {name.lower() for name in reader.fieldnames}
    required_cols = {'id', 'title', 'rotation'}  # Use lowercase for comparison

    if not required_cols.issubset(fieldnames_lower):
        missing = required_cols - fieldnames_lower
        raise ValueError(f"CSV is missing required columns: {', '.join(missing)}")

    output_rows = []
    output_headers = reader.fieldnames + ['Found Region', 'Found Engine', 'Found Metric Type', 'Found Metrics']

    for row in reader:
        row_lower = {k.lower(): v for k, v in row.items()}
        title = row_lower.get('title', '')
        rotation = row_lower.get('rotation', '')

        region_match = region_pattern.search(title)
        engine_match = engine_pattern.search(title)

        row['Found Region'] = region_match.group(0).upper() if region_match else 'N/A'
        row['Found Engine'] = engine_match.group(0).capitalize() if engine_match else 'N/A'

        all_parts = [part.strip() for part in rotation.split(',') if part.strip()]
        metric_type = 'N/A'
        valid_metrics = []

        if all_parts:
            first_part_lower = all_parts[0].lower()
            if first_part_lower in ['glean', 'legacy']:
                metric_type = first_part_lower.capitalize()
            valid_metrics = [part for part in all_parts[1:] if '.' in part]

        row['Found Metric Type'] = metric_type
        row['Found Metrics'] = ', '.join(valid_metrics) if valid_metrics else 'N/A'

        output_rows.append(row)

    return output_headers, output_rows


@bp.route('/extract-from-rotation', methods=['POST'])
def extract_from_rotation():
    """
    Handles uploading a test case rotation CSV to extract region, engine, and metrics.
    """
    file = request.files.get('file')
    if not file or not file.filename:
        flash('No file selected for rotation extraction.', 'error')
        return redirect(url_for('management.index'))

    if not file.filename.lower().endswith('.csv'):
        flash('Invalid file type. Please upload a CSV.', 'error')
        return redirect(url_for('management.index'))

    try:
        headers, rows = _parse_rotation_csv(file.stream)

        string_io = io.StringIO()
        writer = csv.DictWriter(string_io, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

        return Response(
            string_io.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=extracted_rotations.csv"}
        )
    except ValueError as ve:
        flash(str(ve), 'error')
    except Exception as e:
        flash(f"An unexpected error occurred: {e}", 'error')

    return redirect(url_for('management.index'))


# --- NEW ROUTES FOR ENGINE MANAGEMENT ---
@bp.route('/engines/add', methods=['POST'])
def add_engine():
    engine_name = request.form.get('name', '').strip().lower()
    if not engine_name:
        return jsonify({'success': False, 'error': 'Engine name cannot be empty.'}), 400

    success, message = db.add_engine(engine_name)
    if success:
        return jsonify({'success': True, 'name': engine_name})
    else:
        return jsonify({'success': False, 'error': message}), 409  # 409 Conflict for duplicates


@bp.route('/engines/delete', methods=['POST'])
def delete_engine():
    engine_name = request.form.get('name')
    if not engine_name:
        return jsonify({'success': False, 'error': 'Engine name not provided.'}), 400

    success, message = db.delete_engine(engine_name)
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': message}), 500


# --- END NEW ROUTES ---


@bp.route('/delete/<string:table_name>/<string:pk>', methods=['POST'])
def soft_delete(table_name, pk):
    success = db.soft_delete_item(table_name, pk)
    return jsonify({'success': success})


@bp.route('/toggle-management-view', methods=['POST'])
def toggle_management_view():
    session['show_management'] = not session.get('show_management', False)
    return jsonify({'success': True, 'show_management': session['show_management']})