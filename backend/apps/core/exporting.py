"""Private, spreadsheet-safe CSV responses for explicit report exports."""

import csv
import io

from django.http import HttpResponse


def csv_response(rows, *, name, columns):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(columns)
    for row in rows:
        values = [str(row.get(key, "")) for key in columns]
        writer.writerow(
            [
                "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
                for value in values
            ]
        )
    response = HttpResponse(stream.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
    response["Cache-Control"] = "private, no-store"
    return response
