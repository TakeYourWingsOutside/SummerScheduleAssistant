from . import db # Imports the 'db' instance from app/__init__.py
from datetime import datetime, time, timedelta

# Association table for many-to-many relationship between Activity and Kid
activity_kid_association = db.Table('activity_kid_association',
                                    db.Column('activity_id', db.Integer, db.ForeignKey('activity.id'), primary_key=True),
                                    db.Column('kid_id', db.Integer, db.ForeignKey('kid.id'), primary_key=True)
                                    )


class Kid(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    age = db.Column(db.Integer, nullable=False)

    # Relationships
    scheduled_events = db.relationship('ScheduledEvent', backref='kid', lazy='dynamic', cascade="all, delete-orphan")
    # 'activities' relationship will be defined in Activity model via back_populates

    def __repr__(self):
        return f'<Kid {self.name}>'

    def events_needing_supervision_today(self, for_date):
        """Counts events for this kid on for_date that require supervision but don't have it assigned."""
        if not self.scheduled_events: # Should not happen if relationship is defined
            return 0
        count = 0
        # Ensure 'Activity' is imported in this file or accessible
        # from .models import Activity # (if Activity is in the same file, this isn't needed here)
        for event in self.scheduled_events.filter_by(date=for_date).all():
            if event.activity_details and event.activity_details.requires_supervision and not event.supervisor_assigned:
                count += 1
        return count

    def events_needing_transport_today(self, for_date):
        """Counts events for this kid on for_date that require transport but don't have it assigned."""
        if not self.scheduled_events:
            return 0
        count = 0
        for event in self.scheduled_events.filter_by(date=for_date).all():
            if event.activity_details and event.activity_details.requires_transportation and not event.transport_provider:
                count += 1
        return count
    # --- END HELPER METHODS ---


class Activity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60) # Duration in minutes
    requires_supervision = db.Column(db.Boolean, default=False)
    requires_another_person = db.Column(db.Boolean, default=False)
    can_do_alone = db.Column(db.Boolean, default=True)
    requires_transportation = db.Column(db.Boolean, default=False)

    # --- New fields to define an Activity as a "Camp Template" ---
    is_camp_activity = db.Column(db.Boolean, default=False, index=True)
    default_camp_cost = db.Column(db.Float, nullable=True)
    default_is_overnight = db.Column(db.Boolean, default=False)
    default_camp_start_time = db.Column(db.Time, nullable=True) # Optional: if camps have a typical start time
    default_camp_end_time = db.Column(db.Time, nullable=True)   # Optional: if camps have a typical end time for a day

    # Relationships
    kids_assigned = db.relationship('Kid', secondary=activity_kid_association,
                                    lazy='subquery', # or 'dynamic'
                                    backref=db.backref('activities', lazy='dynamic'))
    scheduled_events = db.relationship('ScheduledEvent', backref='activity_details', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Activity {self.name}{" (Camp)" if self.is_camp_activity else ""}>'


class ScheduledEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kid_id = db.Column(db.Integer, db.ForeignKey('kid.id'), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activity.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False) # Calculated or set

    status = db.Column(db.String(50), default='Scheduled') # e.g., 'Scheduled', 'Confirmed', 'Pending Confirmation'
    supervisor_assigned = db.Column(db.String(100), nullable=True)
    transport_provider = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # For multi-person activities needing confirmation
    # If this event is linked to another kid's event (for multi-person activities)
    linked_event_id = db.Column(db.Integer, db.ForeignKey('scheduled_event.id'), nullable=True)
    # Self-referential relationship for linked events
    linked_event_pair = db.relationship("ScheduledEvent", remote_side=[id], uselist=False, post_update=True)

    # for camps
    is_camp = db.Column(db.Boolean, default=False, index=True)
    cost = db.Column(db.Float, nullable=True) # Store cost here
    is_overnight_camp = db.Column(db.Boolean, default=False)
    # To group daily entries of the same multi-day camp session
    camp_session_identifier = db.Column(db.String(100), nullable=True, index=True)
    # If a camp spans multiple days, this would be the actual end date of the whole camp session
    camp_session_end_date = db.Column(db.Date, nullable=True)

    def __repr__(self):
        kid_name = self.kid.name if self.kid else "N/A"
        activity_name = self.activity_details.name if self.activity_details else "N/A"
        return f'<ScheduledEvent Kid: {kid_name} Activity: {activity_name} on {self.date} at {self.start_time}>'

    @property
    def duration(self):
        if self.start_time and self.end_time:
            dummy_date = datetime.min.date() # A dummy date to combine with time for timedelta calculation
            dt_start = datetime.combine(dummy_date, self.start_time)
            dt_end = datetime.combine(dummy_date, self.end_time)
            return (dt_end - dt_start)
        return timedelta(0)

    @property
    def duration_minutes(self):
        return self.duration.total_seconds() / 60
