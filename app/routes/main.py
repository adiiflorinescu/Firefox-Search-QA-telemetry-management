# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/main.py

from flask import Blueprint, render_template, jsonify, current_app, session, request, flash, redirect, url_for, g
from ..services import database as db
from ..utils.decorators import login_required

bp = Blueprint('main', __name__)


# DEFINITIVE FIX: The global before_request has been removed to allow for public routes.
# The @login_required decorator will now be applied to each route individually.


@bp.route('/metrics')
@login_required
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
        tc_base_url=current_app.config.get('TC_BASE_URL', ''),
        show_management=session.get('show_management', False)
    )


@bp.route('/reports')
@login_required
def reports():
    """Renders the reports page."""
    report_data, metric_types, metric_to_tcids = db.get_report_data()
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
        tc_base_url=current_app.config.get('TC_BASE_URL', '')
    )


@bp.route('/activity-log')
@login_required
def activity_log():
    """Displays a searchable log of all user activities."""
    if g.user['role'] != 'admin':
        flash("You don't have permission to view this page.", "error")
        return redirect(url_for('main.metrics'))

    search_term = request.args.get('q', '').strip()
    history = db.get_history(search_term=search_term)
    return render_template('activity_log.html', history=history)


# DEFINITIVE FIX: This route is now public (no @login_required decorator).
@bp.route('/<string:metric_type>/<path:metric_name>/status')
def metric_status(metric_type, metric_name):
    """Renders a read-only status page for a single metric."""
    metric_data = db.get_metric_status_details(metric_type, metric_name)

    if not metric_data:
        flash(f"Metric '{metric_name}' not found.", "error")
        # If a user is not logged in, redirect to login. Otherwise, to metrics.
        if g.user:
            return redirect(url_for('main.metrics'))
        return redirect(url_for('auth.login'))

    return render_template(
        'metric_status.html',
        metric_data=metric_data,
        tc_base_url=current_app.config.get('TC_BASE_URL', '')
    )


@bp.route('/search-suggestions')
@login_required
def search_suggestions():
    """Provides a JSON list of search terms for autofill."""
    suggestions = db.get_search_suggestions()
    return jsonify(suggestions)