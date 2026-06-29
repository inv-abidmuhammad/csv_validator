import json
from pathlib import Path
from datetime import datetime


def generate_report(
    filename,
    schema_name,
    errors,
    report_folder
):
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
        "errors": errors
    }

    report_path = (
        Path(report_folder)
        / f"{Path(filename).stem}_{timestamp}_report.json"
    )

    with open(report_path, "w") as f:
        json.dump(
            report,
            f,
            indent=4,
            default=str
        )

    return report_path