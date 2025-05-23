from app.models import ScheduledEvent # Import the ScheduledEvent model
from datetime import date # Import date for type hinting if you use it

# It's good practice to ensure 'db' is accessible if utils might grow to need it,
# though this specific function doesn't directly use 'db' from app.
# from app import db # Not strictly necessary for this function

def get_camp_session_start_date(event_item_db: ScheduledEvent) -> 'date':
    """
    Given a ScheduledEvent object that is part of a camp session,
    queries the database to find the actual first date of that session.

    Args:
        event_item_db: The ScheduledEvent database object.
                       It's assumed this object is already part of a session
                       or can be used to initiate queries.

    Returns:
        The start date (datetime.date object) of the camp session if found,
        otherwise the event's own date as a fallback.
    """
    if event_item_db and event_item_db.is_camp and event_item_db.camp_session_identifier:
        # Query for the first event in this specific camp session for this specific kid
        first_day_event = ScheduledEvent.query.filter(
            ScheduledEvent.camp_session_identifier == event_item_db.camp_session_identifier,
            ScheduledEvent.kid_id == event_item_db.kid_id # Crucial to scope to the correct kid
        ).order_by(ScheduledEvent.date.asc()).first() # .asc() is default but explicit

        if first_day_event:
            return first_day_event.date

    # Fallback if not a camp, no identifier, or somehow the first day query fails
    # (though it shouldn't if data is consistent)
    if event_item_db:
        return event_item_db.date

    # Absolute fallback if event_item_db itself is None, though the caller should handle this
    return None # Or raise an error, or return today's date, depending on desired handling