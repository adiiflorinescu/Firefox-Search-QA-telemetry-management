# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/main.py

from flask import Blueprint, render_template, session, jsonify, current_app
from ..services import database as db

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Redirects to the main metrics view."""
    return render_template('redirect.html', endpoint='main.metrics')


@bp.route('/metrics')
def metrics():
    """Renders the main metrics view page with all data."""
    coverage_data, metric_types = db.get_all_coverage_details()
    glean_metrics = db.get_glean_metrics()
    legacy_metrics = db.get_legacy_metrics()

    return render_template(
        'metrics.html',
        glean_metrics=glean_metrics,
        legacy_metrics=legacy_metrics,
        coverage=coverage_data,
        metric_types=metric_types,
        glean_count=len(glean_metrics),
        legacy_count=len(legacy_metrics),
        coverage_count=len(coverage_data),
        show_management=session.get('show_management', False),
        tc_base_url=current_app.config.get('TC_BASE_URL', '')
    )


@bp.route('/reports')
def reports():
    """Renders the reports page."""
    report_data, metric_types = db.get_report_data()
    metric_to_tcids = db.get_metric_to_tcid_map()
    stats = db.get_general_stats()

    return render_template(
        'reports.html',
        report_data=report_data,
        metric_to_tcids=metric_to_tcids,
        metric_types=metric_types,
        total_glean_metrics=stats['total_glean_metrics'],
        total_legacy_metrics=stats['total_legacy_metrics'],
        glean_covered_tcs=stats['glean_covered_tcs'],
        legacy_covered_tcs=stats['legacy_covered_tcs'],
        show_management=session.get('show_management', False),
        tc_base_url=current_app.config.get('TC_BASE_URL', '')
    )


@bp.route('/search-suggestions')
def search_suggestions():
    """Provides a JSON list of search terms for autofill."""
    suggestion_type = 'all'
    suggestions = db.get_search_suggestions(suggestion_type)
    return jsonify(suggestions)

# --- DEFINITIVE FIX ---
# The template filters below have been removed because they are already
# registered globally in app/__init__.py. Keeping them here causes
# a name collision and prevents the application from starting.