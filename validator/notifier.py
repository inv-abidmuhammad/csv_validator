import io
import smtplib
import ssl
import zipfile
from email.message import EmailMessage
from pathlib import Path


def build_report_email(report_path, recipient, sender, subject=None):
    """
    Builds an EmailMessage with the report file attached.

    Kept separate from send_report_email so the message construction can
    be unit-tested without touching the network.
    """
    report_path = Path(report_path)

    msg = EmailMessage()
    msg["Subject"] = subject or f"CSV Validation Report: {report_path.stem}"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "CSV validation has completed. The report is attached.\n\n"
        f"File: {report_path.name}"
    )

    with open(report_path, "rb") as f:
        file_bytes = f.read()

    maintype, _, subtype = _guess_mime_type(report_path.suffix).partition("/")
    msg.add_attachment(
        file_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=report_path.name
    )

    return msg


def _guess_mime_type(suffix):
    mime_types = {
        ".json": "application/json",
        ".csv": "text/csv",
        ".html": "text/html",
    }
    return mime_types.get(suffix.lower(), "application/octet-stream")


def send_report_email(report_path, smtp_config):
    """
    Sends a single report file as an email attachment. Used by single/
    independent mode, where there's exactly one report and no batching
    is needed.

    smtp_config is expected to contain:
        host, port, username, password, from_address, to_address
    `use_tls` is optional and defaults to True.

    Raises on failure — callers should catch and log rather than let a
    flaky mail server crash the whole validation run.
    """
    msg = build_report_email(
        report_path,
        recipient=smtp_config["to_address"],
        sender=smtp_config["from_address"],
    )

    use_tls = smtp_config.get("use_tls", True)

    with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=30) as server:
        if use_tls:
            server.starttls(context=ssl.create_default_context())
        if smtp_config.get("username") and smtp_config.get("password"):
            server.login(smtp_config["username"], smtp_config["password"])
        server.send_message(msg)


def build_batch_report_email(report_paths, recipient, sender, summary, subject=None):
    """
    Builds an EmailMessage with all given report files zipped into a
    single attachment, plus a human-readable summary in the body.

    `summary` is expected to contain:
        schema, timestamp, processed, passed, failed, skipped
    All keys are optional — missing ones are simply omitted from the body.

    Kept separate from send_batch_report_email so the message construction
    can be unit-tested without touching the network.
    """
    timestamp = summary.get("timestamp", "unknown")

    msg = EmailMessage()
    msg["Subject"] = subject or f"CSV Validator Batch Report — {timestamp}"
    msg["From"] = sender
    msg["To"] = recipient

    body_lines = [
        "CSV Validator — Batch Run Summary",
        "",
        f"Run completed: {timestamp}",
    ]

    if "schema" in summary:
        body_lines.append(f"Schema used: {summary['schema']}")
    if "processed" in summary:
        body_lines.append(f"Files processed: {summary['processed']}")
    if "passed" in summary:
        body_lines.append(f"Files passed: {summary['passed']}")
    if "failed" in summary:
        body_lines.append(f"Files failed: {summary['failed']}")
    if "skipped" in summary:
        body_lines.append(f"Files skipped (already processed): {summary['skipped']}")

    body_lines += ["", "Individual CSV reports are attached as a zip archive."]

    msg.set_content("\n".join(body_lines))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for report_path in report_paths:
            report_path = Path(report_path)
            zf.write(report_path, arcname=report_path.name)

    msg.add_attachment(
        zip_buffer.getvalue(),
        maintype="application",
        subtype="zip",
        filename=f"validation_reports_{timestamp}.zip"
    )

    return msg


def send_batch_report_email(report_paths, smtp_config, summary):
    """
    Sends a single email containing all reports in `report_paths`, zipped
    into one attachment, along with a run summary in the body.

    Raises on failure — callers should catch and log rather than let a
    flaky mail server crash the whole validation run.
    """
    msg = build_batch_report_email(
        report_paths,
        recipient=smtp_config["to_address"],
        sender=smtp_config["from_address"],
        summary=summary,
    )

    use_tls = smtp_config.get("use_tls", True)

    with smtplib.SMTP(smtp_config["host"], smtp_config["port"], timeout=30) as server:
        if use_tls:
            server.starttls(context=ssl.create_default_context())
        if smtp_config.get("username") and smtp_config.get("password"):
            server.login(smtp_config["username"], smtp_config["password"])
        server.send_message(msg)