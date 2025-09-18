# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/management.py

from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, Response
from ..services import database as db
from ..utils import helpers

bp = Blueprint('management', __name__)


@bp.route('/manage')
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


@bp.route('/delete/<string:table_name>/<string:pk>', methods=['POST'])
def soft_delete(table_name, pk):
    success = db.soft_delete_item(table_name, pk)
    return jsonify({'success': success})


@bp.route('/toggle-management-view', methods=['POST'])
def toggle_management_view():
    session['show_management'] = not session.get('show_management', False)
    return jsonify({'success': True, 'show_management': session['show_management']})