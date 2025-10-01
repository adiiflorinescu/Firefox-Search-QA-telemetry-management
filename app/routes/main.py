# C:/Users/Adi/PycharmProjects/R-W-TCS/pythonProject/app/routes/main.py

from flask import Blueprint, render_template, jsonify, current_app, session, request, flash, redirect, url_for, g
from ..services import database as db
from ..utils.decorators import login_required
import math

bp = Blueprint('main', __name__)


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
    """Displays a paginated and filterable view of the edit history."""
    if g.user['role'] != 'admin':
        flash('You do not have permission to view the activity log.', 'error')
        return redirect(url_for('main.metrics'))

    # Get filter parameters from the request URL
    page = request.args.get('page', 1, type=int)
    per_page = 50  # Or make this configurable
    user_id_filter = request.args.get('user_id', type=int) if request.args.get('user_id') else None
    action_filter = request.args.get('action', type=str) if request.args.get('action') else None
    start_date_filter = request.args.get('start_date', type=str) if request.args.get('start_date') else None
    end_date_filter = request.args.get('end_date', type=str) if request.args.get('end_date') else None
    search_term = request.args.get('search', type=str) if request.args.get('search') else None

    # Fetch data for filter dropdowns
    filter_users = db.get_all_users()
    filter_actions = db.get_distinct_actions()

    # Fetch the total count of items that match the filters
    total_items = db.get_history_count(
        user_id=user_id_filter,
        action=action_filter,
        start_date=start_date_filter,
        end_date=end_date_filter,
        search_term=search_term
    )
    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 1
    page = max(1, min(page, total_pages))  # Ensure page is within valid range

    # Fetch the paginated history items
    history_items = db.get_history(
        page=page,
        per_page=per_page,
        user_id=user_id_filter,
        action=action_filter,
        start_date=start_date_filter,
        end_date=end_date_filter,
        search_term=search_term
    )

    current_filters = {
        'user_id': user_id_filter,
        'action': action_filter,
        'start_date': start_date_filter,
        'end_date': end_date_filter,
        'search': search_term
    }

    return render_template(
        'activity_log.html',
        history=history_items,
        page=page,
        total_pages=total_pages,
        total_items=total_items,
        filter_users=filter_users,
        filter_actions=filter_actions,
        current_filters=current_filters
    )


@bp.route('/<string:metric_type>/<path:metric_name>/status')
def metric_status(metric_type, metric_name):
    """Renders a read-only status page for a single metric."""
    metric_data = db.get_metric_status_details(metric_type, metric_name)

    if not metric_data:
        flash(f"Metric '{metric_name}' not found.", "error")
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