import csv
import json
from pathlib import Path
from datetime import datetime


def generate_summary_stats(df, errors):
    total_rows = len(df)

    # Rows are 1-indexed from row 2 (row 1 is the header), matching the
    # convention used throughout validation_engine.py. Column-level errors
    # (e.g. a missing column) have row=None and don't correspond to a
    # specific data row, so they're excluded from row-based counts.
    failed_rows = {
        error["row"]
        for error in errors
        if error["row"] is not None
    }

    duplicate_count = sum(
        1 for error in errors
        if error["error"] == "Duplicate record"
    )

    error_counts_by_type = {}
    for error in errors:
        error_counts_by_type[error["error"]] = error_counts_by_type.get(error["error"], 0) + 1

    return {
        "rows_processed": total_rows,
        "rows_passed": total_rows - len(failed_rows),
        "rows_failed": len(failed_rows),
        "duplicates_found": duplicate_count,
        "total_errors": len(errors),
        "errors_by_type": error_counts_by_type,
    }


def generate_report(
    filename,
    schema_name,
    df,
    errors,
    report_folder,
    formats=None
):
    """
    Generates a validation report.

    JSON is always written, since the database stores its path and other
    code (e.g. get_report_path) depends on it existing. Additional formats
    can be requested via `formats`, e.g. formats=["csv", "html"].

    Returns the path to the JSON report (kept as the canonical return value
    so existing callers don't need to change).
    """
    if formats is None:
        formats = []

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )
    report = {
        "file": filename,
        "schema": schema_name,
        "status":
            "FAILED"
            if errors
            else "SUCCESS",
        "error_count": len(errors),
        "summary": generate_summary_stats(df, errors),
        "errors": errors
    }

    report_stem = f"{Path(filename).stem}_{timestamp}_report"

    json_path = Path(report_folder) / f"{report_stem}.json"
    with open(json_path, "w") as f:
        json.dump(
            report,
            f,
            indent=4,
            default=str
        )

    if "csv" in formats:
        generate_csv_report(report, report_folder, report_stem)

    if "html" in formats:
        generate_html_report(report, report_folder, report_stem)

    return json_path


def generate_csv_report(report, report_folder, report_stem):
    """
    Writes a flat CSV representation of a report dict. One row per error;
    if there are no errors, a single row indicates a clean pass.

    `report` is the dict produced inside generate_report — same shape as
    the JSON output, so this can be called standalone for re-exporting an
    already-generated report too.
    """
    csv_path = Path(report_folder) / f"{report_stem}.csv"

    fieldnames = ["file", "schema", "status", "row", "column", "value", "error"]

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        if not report["errors"]:
            writer.writerow(
                {
                    "file": report["file"],
                    "schema": report["schema"],
                    "status": report["status"],
                    "row": "",
                    "column": "",
                    "value": "",
                    "error": "",
                }
            )
        else:
            for error in report["errors"]:
                writer.writerow(
                    {
                        "file": report["file"],
                        "schema": report["schema"],
                        "status": report["status"],
                        "row": error["row"] if error["row"] is not None else "",
                        "column": error["column"] if error["column"] is not None else "",
                        "value": error["value"],
                        "error": error["error"],
                    }
                )

    return csv_path


def _escape_html(value):
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def generate_html_report(report, report_folder, report_stem):
    """
    Writes a simple, dependency-free HTML report. Built with plain string
    templating (no Jinja2) since the layout is small and fixed.
    """
    html_path = Path(report_folder) / f"{report_stem}.html"

    status_class = "status-failed" if report["status"] == "FAILED" else "status-success"

    summary = report["summary"]
    summary_rows = "".join(
        f"<tr><td>{_escape_html(key)}</td><td>{_escape_html(value)}</td></tr>"
        for key, value in summary.items()
        if key != "errors_by_type"
    )

    error_type_rows = "".join(
        f"<tr><td>{_escape_html(error_type)}</td><td>{count}</td></tr>"
        for error_type, count in summary.get("errors_by_type", {}).items()
    )

    if report["errors"]:
        error_rows = "".join(
            "<tr>"
            f"<td>{_escape_html(error['row'])}</td>"
            f"<td>{_escape_html(error['column'])}</td>"
            f"<td>{_escape_html(error['value'])}</td>"
            f"<td>{_escape_html(error['error'])}</td>"
            "</tr>"
            for error in report["errors"]
        )
    else:
        error_rows = "<tr><td colspan='4'>No errors found.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Validation Report: {_escape_html(report['file'])}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 10px; text-align: left; font-size: 0.9rem; }}
  th {{ background-color: #f3f3f3; }}
  .status-success {{ color: #1a7f37; font-weight: bold; }}
  .status-failed {{ color: #c0392b; font-weight: bold; }}
</style>
</head>
<body>
  <h1>Validation Report</h1>
  <p><strong>File:</strong> {_escape_html(report['file'])}</p>
  <p><strong>Schema:</strong> {_escape_html(report['schema'])}</p>
  <p><strong>Status:</strong> <span class="{status_class}">{_escape_html(report['status'])}</span></p>

  <h2>Summary</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    {summary_rows}
  </table>

  <h2>Errors by Type</h2>
  <table>
    <tr><th>Error Type</th><th>Count</th></tr>
    {error_type_rows if error_type_rows else "<tr><td colspan='2'>No errors found.</td></tr>"}
  </table>

  <h2>Error Details</h2>
  <table>
    <tr><th>Row</th><th>Column</th><th>Value</th><th>Error</th></tr>
    {error_rows}
  </table>
</body>
</html>
"""

    with open(html_path, "w") as f:
        f.write(html)

    return html_path