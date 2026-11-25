import csv
import unicodedata

from django.http import HttpResponse


def safe_cell(value):
    text = str(value) if value is not None else ""
    safe_start = next(
        (
            char
            for char in text
            if not char.isspace() and not unicodedata.category(char).startswith("C")
        ),
        "",
    )
    if safe_start in ("=", "+", "-", "@") or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def csv_download(name, headers, rows):
    response = HttpResponse(
        "\ufeff",
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}.csv"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
    writer = csv.writer(response)
    writer.writerow(headers)
    writer.writerows(map(safe_cell, row) for row in rows)
    return response
