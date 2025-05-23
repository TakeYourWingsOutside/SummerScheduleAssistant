from flask import Blueprint, render_template, request
from app import db
from app.models import Kid, ScheduledEvent, Activity # Activity needed if you want to display camp names
from app.forms import CampCostReportForm # Import the new form
from sqlalchemy import func # For using sum() and group_by()
from datetime import date # For default dates in form if not submitting

bp = Blueprint('reports', __name__, url_prefix='/reports')

@bp.route('/camp_costs', methods=['GET', 'POST'])
def camp_cost_report():
    form = CampCostReportForm(request.form) # Pass request.form for POST data handling
    report_data = []
    grand_total_cost = 0.0

    # Set default dates for the form if it's a GET request and form is not pre-filled
    if request.method == 'GET' and not form.start_date.data:
        form.start_date.data = date(date.today().year, 6, 1)
        form.end_date.data = date(date.today().year, 8, 31)

    if form.validate_on_submit(): # This implicitly handles POST requests
        start_date_filter = form.start_date.data
        end_date_filter = form.end_date.data

        # Query to get camp costs:
        # We need events that are camps, have a cost > 0 (meaning it's the first day record for the session cost),
        # and that first day falls within the selected date range.
        # We group by kid to sum costs per kid.

        # Subquery to identify the first day of each camp session for cost attribution
        # This is not strictly needed if we just filter cost > 0 and is_camp = True,
        # as we store cost only on the first day. But good for clarity.
        # We will sum 'cost' from ScheduledEvent where is_camp=True and cost > 0
        # and ScheduledEvent.date is within the filter range.

        results = db.session.query(
            Kid.id.label('kid_id'),
            Kid.name.label('kid_name'),
            func.sum(ScheduledEvent.cost).label('total_kid_cost')
        ).join(ScheduledEvent, Kid.id == ScheduledEvent.kid_id) \
            .filter(
            ScheduledEvent.is_camp == True,
            ScheduledEvent.cost > 0, # Only sum records that hold the session cost
            ScheduledEvent.date >= start_date_filter,
            ScheduledEvent.date <= end_date_filter # The date of the cost-bearing event record
        ).group_by(Kid.id, Kid.name) \
            .order_by(Kid.name) \
            .all()

        # To get individual camp details per kid (more complex query or post-processing)
        # For now, let's just get the total per kid.
        # We can enhance to list individual camps later.

        detailed_report_data = []
        current_grand_total = 0.0

        for kid_id_res, kid_name_res, total_kid_cost_res in results:
            kid_camp_details = []
            # Fetch distinct camp sessions for this kid within the date range
            # This query gets the first day record (which has the cost) for each camp session
            kid_camp_sessions = db.session.query(ScheduledEvent) \
                .join(Activity) \
                .filter(
                ScheduledEvent.kid_id == kid_id_res,
                ScheduledEvent.is_camp == True,
                ScheduledEvent.cost > 0,
                ScheduledEvent.date >= start_date_filter,
                ScheduledEvent.date <= end_date_filter
            ).order_by(ScheduledEvent.date).all()

            for camp_event in kid_camp_sessions:
                kid_camp_details.append({
                    'camp_name': camp_event.activity_details.name,
                    'session_start_date': camp_event.date, # The date of the cost record
                    'session_end_date': camp_event.camp_session_end_date,
                    'cost': camp_event.cost
                })

            if total_kid_cost_res is not None: # Ensure total_kid_cost_res is not None before adding
                detailed_report_data.append({
                    'kid_id': kid_id_res,
                    'kid_name': kid_name_res,
                    'total_cost': total_kid_cost_res,
                    'camps': kid_camp_details
                })
                current_grand_total += total_kid_cost_res

        report_data = detailed_report_data
        grand_total_cost = current_grand_total

    return render_template('reports/camp_cost.html',
                           form=form,
                           report_data=report_data,
                           grand_total_cost=grand_total_cost,
                           # Pass selected dates back to template to display what range report is for
                           selected_start_date=form.start_date.data,
                           selected_end_date=form.end_date.data
                           )