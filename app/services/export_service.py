from app.models import ScheduledEvent, Kid, Activity
from datetime import datetime, timedelta
from ics import Calendar, Event as ICSEvent # Renamed to avoid conflict with our Event model if we had one
import csv
import io # For creating CSV in memory


def generate_ics_for_kid_range(kid_id, start_date, end_date):
    """
    Generates an iCalendar (.ics) string for a given kid over a date range.
    """
    kid = Kid.query.get(kid_id)
    if not kid:
        return None # Or raise error

    events_query = ScheduledEvent.query.filter(
        ScheduledEvent.kid_id == kid_id,
        ScheduledEvent.date >= start_date,
        ScheduledEvent.date <= end_date
    ).order_by(ScheduledEvent.date, ScheduledEvent.start_time).all()

    cal = Calendar()
    for event_item in events_query:
        activity = event_item.activity_details

        # Combine date and time for start and end
        dt_start = datetime.combine(event_item.date, event_item.start_time)
        dt_end = datetime.combine(event_item.date, event_item.end_time)

        ics_e = ICSEvent()
        ics_e.name = f"{kid.name}: {activity.name}"
        ics_e.begin = dt_start
        ics_e.end = dt_end

        description_parts = [activity.description or ""]
        if event_item.supervisor_assigned:
            description_parts.append(f"Supervisor: {event_item.supervisor_assigned}")
        if event_item.transport_provider:
            description_parts.append(f"Transport: {event_item.transport_provider} (Pickup: {event_item.start_time.strftime('%I:%M %p')}, Drop-off: {event_item.end_time.strftime('%I:%M %p')})")
        if event_item.status and event_item.status != "Scheduled":
            description_parts.append(f"Status: {event_item.status}")
        if event_item.notes:
            description_parts.append(f"Notes: {event_item.notes}")

        ics_e.description = "\n".join(filter(None, description_parts)) # Join non-empty parts

        # Optional: Add location, alarms, etc.
        # ics_e.location = "Home"

        cal.events.add(ics_e)

    return str(cal) # Returns the iCalendar string


def generate_csv_for_kid_range(kid_id, start_date, end_date):
    """
    Generates a CSV string for a given kid over a date range.
    """
    kid = Kid.query.get(kid_id)
    if not kid:
        return None

    events_query = ScheduledEvent.query.filter(
        ScheduledEvent.kid_id == kid_id,
        ScheduledEvent.date >= start_date,
        ScheduledEvent.date <= end_date
    ).order_by(ScheduledEvent.date, ScheduledEvent.start_time).all()

    output = io.StringIO() # Create an in-memory text stream
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        'Date', 'Kid Name', 'Activity Name', 'Start Time', 'End Time',
        'Duration (min)', 'Status', 'Supervisor', 'Transport Provider',
        'Transport Pickup', 'Transport Drop-off', 'Notes', 'Activity Description'
    ])

    for event_item in events_query:
        activity = event_item.activity_details
        writer.writerow([
            event_item.date.strftime('%Y-%m-%d'),
            kid.name,
            activity.name,
            event_item.start_time.strftime('%H:%M'),
            event_item.end_time.strftime('%H:%M'),
            activity.duration_minutes,
            event_item.status,
            event_item.supervisor_assigned or '',
            event_item.transport_provider or '',
            event_item.start_time.strftime('%I:%M %p') if event_item.transport_provider else '',
            event_item.end_time.strftime('%I:%M %p') if event_item.transport_provider else '',
            event_item.notes or '',
            activity.description or ''
        ])

    return output.getvalue()