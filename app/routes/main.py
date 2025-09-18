# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/main.py

from flask import Blueprint, render_template, redirect, url_for, session, jsonify, request, current_app
from ..services import database as db
# from .. import config  <- REMOVE THIS LINE

bp = Blueprint('main', __name__)

@bp.route('/')
def home():
    """Redirects the base URL to the main metrics view page."""
    return redirect(url_for('main.metrics'))

@bp.route('/metrics')
def metrics():
    """Renders the metrics and coverage view page."""
    glean_metrics = db.get_glean_metrics()
    legacy_metrics = db.get_legacy_metrics()
    coverage_data = db.get_all_coverage_details()

    return render_template(
        'metrics.html',
        glean_metrics=glean_metrics,
        legacy_metrics=legacy_metrics,
        coverage=coverage_data,
        coverage_count=len(coverage_data),
        glean_count=len(glean_metrics),
        legacy_count=len(legacy_metrics),
        # Use current_app.config to access configuration
        tc_base_url=current_app.config['TC_BASE_URL'],
        show_management=session.get('show_management', False)
    )

@bp.route('/reports')
def reports():
    """Renders the new metric reports page with aggregated data."""
    report_data = db.get_report_data()
    metric_to_tcids = db.get_metric_to_tcid_map()
    stats = db.get_general_stats()

    return render_template(
        'reports.html',
        report_data=report_data,
        metric_to_tcids=metric_to_tcids,
        total_glean_metrics=stats['total_glean_metrics'],
        total_legacy_metrics=stats['total_legacy_metrics'],
        glean_covered_tcs=stats['glean_covered_tcs'],
        legacy_covered_tcs=stats['legacy_covered_tcs'],
        # Use current_app.config to access configuration
        tc_base_url=current_app.config['TC_BASE_URL'],
        show_management=session.get('show_management', False)
    )

@bp.route('/search-suggestions')
def search_suggestions():
    """Provides a JSON list of search terms for autofill."""
    suggestion_type = request.args.get('type', 'all')
    suggestions = db.get_search_suggestions(suggestion_type)
    return jsonify(suggestions)