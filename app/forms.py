from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, IntegerField, BooleanField, SubmitField,
    SelectMultipleField, widgets, DateField, TimeField, SelectField, FloatField
)
from wtforms.validators import DataRequired, NumberRange, Length, Optional, ValidationError
from .models import Kid, Activity
from datetime import date, timedelta

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class ActivityForm(FlaskForm):
    # ... (definition as before) ...
    name = StringField('Activity Name', validators=[DataRequired(), Length(min=2, max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    duration_minutes = IntegerField('Default Duration per instance/day (minutes)',
                                    validators=[DataRequired(), NumberRange(min=5, max=1440)])
    requires_supervision = BooleanField('Typically Requires Supervision')
    requires_another_person = BooleanField('Typically Requires Another Person')
    can_do_alone = BooleanField('Typically Can Be Done Alone', default=True)
    requires_transportation = BooleanField('Typically Requires Transportation')
    is_camp_activity = BooleanField('This defines a type of Camp (rather than a regular activity)')
    default_camp_cost = FloatField('Default Cost for a Camp Session (e.g., for one week)',
                                   validators=[Optional(), NumberRange(min=0)])
    default_is_overnight = BooleanField('Default: This type of camp is Overnight')
    kids_assigned = MultiCheckboxField('Eligible Kids for this Activity/Camp Type', coerce=int)
    submit = SubmitField('Save Definition')
    def __init__(self, *args, **kwargs):
        super(ActivityForm, self).__init__(*args, **kwargs)
        self.kids_assigned.choices = [(k.id, k.name) for k in Kid.query.order_by(Kid.name).all()]

class SelectDateKidForm(FlaskForm):
    # ... (definition as before) ...
    date = DateField('Select Date', validators=[DataRequired()], format='%Y-%m-%d', default=lambda: date.today())
    kid_id = SelectField('Select Kid', coerce=int, validators=[DataRequired()])
    submit_select = SubmitField('View Schedule')
    def __init__(self, *args, **kwargs):
        super(SelectDateKidForm, self).__init__(*args, **kwargs)
        self.kid_id.choices = [(0, "--- Select a Kid ---")] + [(k.id, k.name) for k in Kid.query.order_by(Kid.name).all()]

class ScheduleActivityForm(FlaskForm): # For single, regular events
    # ... (definition as before) ...
    activity_id = SelectField('Activity', coerce=int, validators=[DataRequired()])
    start_time = TimeField('Start Time', validators=[DataRequired()], format='%H:%M')
    supervisor_assigned = StringField('Supervisor (if needed)', validators=[Optional(), Length(max=100)])
    transport_provider = StringField('Transport Provider (if needed)', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes for this event', validators=[Optional(), Length(max=500)])
    submit_schedule = SubmitField('Add to Daily Schedule')
    def __init__(self, kid_id=None, *args, **kwargs):
        super(ScheduleActivityForm, self).__init__(*args, **kwargs)
        self.activity_id.choices = [(0, "--- Select Activity ---")]
        activities_to_show = []; query = Activity.query.filter_by(is_camp_activity=False)
        if kid_id:
            kid = Kid.query.get(kid_id)
            if kid:
                try: activities_to_show.extend(kid.activities.filter_by(is_camp_activity=False).order_by(Activity.name).all())
                except AttributeError:
                    if isinstance(kid.activities, list): activities_to_show.extend(sorted([act for act in kid.activities if not act.is_camp_activity], key=lambda act: act.name))
            else: activities_to_show.extend(query.order_by(Activity.name).all())
        else: activities_to_show.extend(query.order_by(Activity.name).all())
        if activities_to_show: self.activity_id.choices.extend([(act.id, act.name) for act in activities_to_show])
        if len(self.activity_id.choices) <= 1: self.activity_id.choices = [(0, "No regular activities available")]

class EditScheduledEventDetailsForm(FlaskForm):
    # ... (definition as before) ...
    supervisor_assigned = StringField('Supervisor', validators=[Optional(), Length(max=100)])
    transport_provider = StringField('Transport Provider', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Notes for this event', validators=[Optional(), Length(max=500)])
    status = SelectField('Status', choices=[ ('Scheduled', 'Scheduled'), ('Confirmed', 'Confirmed'), ('Pending Confirmation', 'Pending Confirmation'), ('Scheduled (Camp)', 'Scheduled (Camp)'), ('Scheduled (Auto)', 'Scheduled (Auto)'), ('Scheduled (Batch)', 'Scheduled (Batch)'), ('Needs Partner', 'Needs Partner'), ('Needs Partner (Modal Add)', 'Needs Partner (Modal Add)'), ('Cancelled', 'Cancelled'), ('Declined', 'Declined')], validators=[Optional()])
    is_camp = BooleanField('Is Camp Event')
    cost = FloatField('Camp Session Cost (if first day)', validators=[Optional(), NumberRange(min=0)])
    is_overnight_camp = BooleanField('Is Overnight Camp')
    submit_edit_details = SubmitField('Update Details')

class ScheduleRangeForm(FlaskForm):
    # ... (definition as before) ...
    kid_id = SelectField('Select Kid', coerce=int, validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d', default=lambda: date.today())
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d', default=lambda: date.today() + timedelta(days=6))
    submit_range_schedule = SubmitField('Auto-Schedule Regular Activities for Range')
    def __init__(self, *args, **kwargs):
        super(ScheduleRangeForm, self).__init__(*args, **kwargs)
        self.kid_id.choices = [(0, "--- Select a Kid ---")] + [(k.id, k.name) for k in Kid.query.order_by(Kid.name).all()]
    def validate_end_date(self, field):
        if self.start_date.data and field.data:
            if field.data < self.start_date.data: raise ValidationError('End date must not be earlier than start date.')
            if (field.data - self.start_date.data).days > 30 : raise ValidationError('Date range cannot exceed 31 days for auto-scheduling.')

class ExportForm(FlaskForm):
    # ... (definition as before) ...
    kid_id = SelectField('Select Kid', coerce=int, validators=[DataRequired()])
    start_date = DateField('Start Date', validators=[DataRequired()], format='%Y-%m-%d', default=lambda: date.today())
    end_date = DateField('End Date', validators=[DataRequired()], format='%Y-%m-%d', default=lambda: date.today() + timedelta(days=6))
    export_format = SelectField('Export Format', choices=[('ics', 'iCalendar (.ics)'), ('csv', 'CSV (.csv)')], validators=[DataRequired()])
    submit_export = SubmitField('Generate Export')
    def __init__(self, *args, **kwargs):
        super(ExportForm, self).__init__(*args, **kwargs)
        self.kid_id.choices = [(0, "--- Select a Kid ---")] + [(k.id, k.name) for k in Kid.query.order_by(Kid.name).all()]
    def validate_end_date(self, field):
        if self.start_date.data and field.data:
            if field.data < self.start_date.data: raise ValidationError('End date must not be earlier than start date.')
            if (field.data - self.start_date.data).days > 90: raise ValidationError('Date range for export cannot exceed 90 days.')

class ScheduleCampSessionForm(FlaskForm):
    # ... (definition as before) ...
    kid_id = SelectField('Select Kid for this Camp Session', coerce=int, validators=[DataRequired()])
    session_start_date = DateField('Camp Session Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    session_end_date = DateField('Camp Session End Date', validators=[DataRequired()], format='%Y-%m-%d')
    session_cost = FloatField('Cost for this Camp Session', validators=[Optional(), NumberRange(min=0)])
    session_is_overnight = BooleanField('This Session is Overnight')
    notes = TextAreaField('Notes for this Camp Session', validators=[Optional(), Length(max=500)])
    submit_schedule_camp = SubmitField('Schedule Camp Session')
    def __init__(self, activity_obj=None, *args, **kwargs):
        super(ScheduleCampSessionForm, self).__init__(*args, **kwargs)
        self.kid_id.choices = [(0, "--- Select a Kid ---")] + [(k.id, k.name) for k in Kid.query.order_by(Kid.name).all()]
        if activity_obj and not self.is_submitted():
            if self.session_cost.data is None and activity_obj.default_camp_cost is not None: self.session_cost.data = activity_obj.default_camp_cost
            if 'session_is_overnight' not in kwargs and (not hasattr(self, '_formdata') or self._formdata is None): self.session_is_overnight.data = activity_obj.default_is_overnight
    def validate_session_end_date(self, field):
        if self.session_start_date.data and field.data:
            if field.data < self.session_start_date.data: raise ValidationError('Camp end date cannot be earlier than start date.')
            if (field.data - self.session_start_date.data).days > 60: raise ValidationError('Camp session cannot exceed 60 days.')

class BatchScheduleMultiDateForm(FlaskForm):
    # ... (definition as before) ...
    activity_id = SelectField('Select Activity', coerce=int, validators=[DataRequired()])
    kid_id = SelectField('Select Kid', coerce=int, validators=[DataRequired()])
    selected_dates = StringField('Select Dates (comma-separated YYYY-MM-DD)', validators=[DataRequired()])
    start_time = TimeField('Start Time (for all selected dates)', validators=[DataRequired()], format='%H:%M')
    supervisor_assigned = StringField('Supervisor (Optional - for all entries)', validators=[Optional(), Length(max=100)])
    transport_provider = StringField('Transport Provider (Optional - for all entries)', validators=[Optional(), Length(max=100)])
    notes = TextAreaField('Common Notes (Optional - for all entries)', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Schedule on Selected Dates')
    def __init__(self, *args, **kwargs):
        super(BatchScheduleMultiDateForm, self).__init__(*args, **kwargs)
        reg_activities = Activity.query.filter_by(is_camp_activity=False).order_by(Activity.name).all()
        self.activity_id.choices = [(0, "--- Select Regular Activity ---")] + [(act.id, act.name) for act in reg_activities]
        self.kid_id.choices = [(0, "--- Select a Kid ---")] +  [(k.id, k.name) for k in Kid.query.order_by(Kid.name).all()]

# --- ADD THIS FORM DEFINITION ---
class CampCostReportForm(FlaskForm):
    start_date = DateField('Report Start Date',
                           validators=[DataRequired()],
                           format='%Y-%m-%d',
                           default=lambda: date(date.today().year, 6, 1))
    end_date = DateField('Report End Date',
                         validators=[DataRequired()],
                         format='%Y-%m-%d',
                         default=lambda: date(date.today().year, 8, 31))
    submit_report = SubmitField('Generate Camp Cost Report')

    def validate_end_date(self, field):
        if self.start_date.data and field.data: # Ensure both dates are present
            if field.data < self.start_date.data:
                raise ValidationError('End date must not be earlier than start date.')
# --- END ADD THIS FORM DEFINITION ---

class EditCampSessionForm(FlaskForm):
    # These fields represent the properties of the ENTIRE camp session
    session_start_date = DateField('New Camp Session Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    session_end_date = DateField('New Camp Session End Date', validators=[DataRequired()], format='%Y-%m-%d')

    session_cost = FloatField('New Total Cost for this Camp Session', validators=[Optional(), NumberRange(min=0)])
    session_is_overnight = BooleanField('This Entire Session is Overnight')

    session_notes = TextAreaField('Common Notes for this Camp Session', validators=[Optional(), Length(max=500)])

    submit_update_session = SubmitField('Update Camp Session')

    # activity_obj and kid_obj can be passed for context if needed for __init__ or choices
    def __init__(self, *args, **kwargs):
        super(EditCampSessionForm, self).__init__(*args, **kwargs)
        # No dynamic choices needed here unless you add kid/activity selection

    def validate_session_end_date(self, field):
        if self.session_start_date.data and field.data:
            if field.data < self.session_start_date.data:
                raise ValidationError('Camp session end date cannot be earlier than start date.')
            if (field.data - self.session_start_date.data).days > 60:
                raise ValidationError('Camp session duration cannot exceed 60 days.')