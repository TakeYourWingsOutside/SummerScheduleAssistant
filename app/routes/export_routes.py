from flask import Blueprint, render_template, request, Response, flash, redirect, url_for
from app.forms import ExportForm
from app.services.export_service import generate_ics_for_kid_range, generate_csv_for_kid_range
from app.models import Kid
from datetime import datetime

bp = Blueprint('export', __name__, url_prefix='/export')

@bp.route('/', methods=['GET', 'POST'])
def generate_export_file():
    form = ExportForm()
    if form.validate_on_submit():
        kid_id = form.kid_id.data
        start_date = form.start_date.data
        end_date = form.end_date.data
        export_format = form.export_format.data

        if kid_id == 0:
            flash("Please select a kid for export.", "error")
            return render_template('export/generate.html', form=form)

        kid = Kid.query.get(kid_id)
        if not kid:
            flash("Selected kid not found.", "error")
            return render_template('export/generate.html', form=form)

        filename_kid_name = "".join(c if c.isalnum() else "_" for c in kid.name) # Sanitize name for filename
        filename_date_range = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}"

        if export_format == 'ics':
            ics_data = generate_ics_for_kid_range(kid_id, start_date, end_date)
            if not ics_data or ics_data.strip() == "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:ics.py - http://git.io/lLljaA\nEND:VCALENDAR": # Check if empty
                flash(f"No events found for {kid.name} in the selected date range to export as iCalendar.", "info")
                return redirect(url_for('export.generate_export_file'))

            return Response(
                ics_data,
                mimetype="text/calendar",
                headers={"Content-disposition": f"attachment; filename={filename_kid_name}_schedule_{filename_date_range}.ics"}
            )
        elif export_format == 'csv':
            csv_data = generate_csv_for_kid_range(kid_id, start_date, end_date)
            # Check if CSV data is more than just the header
            if not csv_data or len(csv_data.splitlines()) <= 1:
                flash(f"No events found for {kid.name} in the selected date range to export as CSV.", "info")
                return redirect(url_for('export.generate_export_file'))

            return Response(
                csv_data,
                mimetype="text/csv",
                headers={"Content-disposition": f"attachment; filename={filename_kid_name}_schedule_{filename_date_range}.csv"}
            )
        else:
            flash("Invalid export format selected.", "error")

    # For GET request or form validation failure
    return render_template('export/generate.html', form=form)
