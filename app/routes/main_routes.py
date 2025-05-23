from flask import Blueprint, render_template
from app.models import Kid, ScheduledEvent, Activity # Add ScheduledEvent, Activity
from datetime import date, datetime # Add date, datetime

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    today = date.today()
    kids = Kid.query.order_by(Kid.name).all()

    todays_events_by_kid = {}
    for kid_obj in kids:
        events = ScheduledEvent.query.filter_by(kid_id=kid_obj.id, date=today) \
            .join(Activity) \
            .order_by(ScheduledEvent.start_time, Activity.name) \
            .all()
        if events: # Only add kid if they have events today
            todays_events_by_kid[kid_obj] = events

    return render_template('index.html',
                           kids=kids, # Still pass all kids for the general list if you keep it
                           todays_date=today,
                           todays_events_by_kid=todays_events_by_kid)