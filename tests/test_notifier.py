import io
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.notifier import (
    build_batch_report_email,
    build_report_email,
    send_batch_report_email,
    send_report_email,
)


@pytest.fixture
def sample_report_file(tmp_path):
    path = tmp_path / "data_20260101_report.json"
    path.write_text('{"file": "data.csv", "status": "SUCCESS"}')
    return path


@pytest.fixture
def sample_batch_report_files(tmp_path):
    paths = []
    for i in range(3):
        path = tmp_path / f"file{i}_20260101_report.csv"
        path.write_text(f"file,status\nfile{i}.csv,SUCCESS\n")
        paths.append(path)
    return paths


@pytest.fixture
def sample_batch_summary():
    return {
        "schema": "schema.json",
        "timestamp": "20260101_120000",
        "processed": 3,
        "passed": 2,
        "failed": 1,
        "skipped": 0,
    }


@pytest.fixture
def smtp_config():
    return {
        "host": "smtp.example.com",
        "port": 587,
        "username": "bot@example.com",
        "password": "secret",
        "from_address": "bot@example.com",
        "to_address": "team@example.com",
    }


# ---------------------------------------------------------------------------
# build_report_email — pure, no network, tested directly
# ---------------------------------------------------------------------------

class TestBuildReportEmail:
    def test_sets_from_and_to(self, sample_report_file):
        msg = build_report_email(sample_report_file, "team@example.com", "bot@example.com")
        assert msg["From"] == "bot@example.com"
        assert msg["To"] == "team@example.com"

    def test_default_subject_contains_report_stem(self, sample_report_file):
        msg = build_report_email(sample_report_file, "team@example.com", "bot@example.com")
        assert sample_report_file.stem in msg["Subject"]

    def test_custom_subject_used_when_provided(self, sample_report_file):
        msg = build_report_email(
            sample_report_file, "team@example.com", "bot@example.com",
            subject="Custom Subject"
        )
        assert msg["Subject"] == "Custom Subject"

    def test_attachment_filename_matches_report_file(self, sample_report_file):
        msg = build_report_email(sample_report_file, "team@example.com", "bot@example.com")
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == sample_report_file.name

    def test_attachment_content_matches_file_bytes(self, sample_report_file):
        msg = build_report_email(sample_report_file, "team@example.com", "bot@example.com")
        attachment = next(msg.iter_attachments())
        assert attachment.get_content().strip() == sample_report_file.read_bytes().strip()

    def test_json_mime_type(self, tmp_path):
        f = tmp_path / "report.json"
        f.write_text("{}")
        msg = build_report_email(f, "team@example.com", "bot@example.com")
        attachment = next(msg.iter_attachments())
        assert attachment.get_content_type() == "application/json"

    def test_csv_mime_type(self, tmp_path):
        f = tmp_path / "report.csv"
        f.write_text("a,b\n1,2\n")
        msg = build_report_email(f, "team@example.com", "bot@example.com")
        attachment = next(msg.iter_attachments())
        assert attachment.get_content_type() == "text/csv"

    def test_html_mime_type(self, tmp_path):
        f = tmp_path / "report.html"
        f.write_text("<html></html>")
        msg = build_report_email(f, "team@example.com", "bot@example.com")
        attachment = next(msg.iter_attachments())
        assert attachment.get_content_type() == "text/html"

    def test_unknown_extension_falls_back_to_octet_stream(self, tmp_path):
        f = tmp_path / "report.xyz"
        f.write_bytes(b"binary data")
        msg = build_report_email(f, "team@example.com", "bot@example.com")
        attachment = next(msg.iter_attachments())
        assert attachment.get_content_type() == "application/octet-stream"

    def test_body_mentions_filename(self, sample_report_file):
        msg = build_report_email(sample_report_file, "team@example.com", "bot@example.com")
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert sample_report_file.name in body


# ---------------------------------------------------------------------------
# send_report_email — network calls mocked, verifying correct SMTP usage
# ---------------------------------------------------------------------------

class TestSendReportEmail:
    @patch("validator.notifier.smtplib.SMTP")
    def test_connects_to_configured_host_and_port(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_report_email(sample_report_file, smtp_config)

        mock_smtp_class.assert_called_once_with(
            smtp_config["host"], smtp_config["port"], timeout=30
        )

    @patch("validator.notifier.smtplib.SMTP")
    def test_calls_starttls_by_default(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_report_email(sample_report_file, smtp_config)

        mock_server.starttls.assert_called_once()

    @patch("validator.notifier.smtplib.SMTP")
    def test_skips_starttls_when_use_tls_false(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        smtp_config["use_tls"] = False

        send_report_email(sample_report_file, smtp_config)

        mock_server.starttls.assert_not_called()

    @patch("validator.notifier.smtplib.SMTP")
    def test_logs_in_with_credentials(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_report_email(sample_report_file, smtp_config)

        mock_server.login.assert_called_once_with(
            smtp_config["username"], smtp_config["password"]
        )

    @patch("validator.notifier.smtplib.SMTP")
    def test_skips_login_when_no_credentials(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server
        smtp_config.pop("username")
        smtp_config.pop("password")

        send_report_email(sample_report_file, smtp_config)

        mock_server.login.assert_not_called()

    @patch("validator.notifier.smtplib.SMTP")
    def test_sends_message(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_report_email(sample_report_file, smtp_config)

        mock_server.send_message.assert_called_once()
        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg["To"] == smtp_config["to_address"]
        assert sent_msg["From"] == smtp_config["from_address"]

    @patch("validator.notifier.smtplib.SMTP")
    def test_raises_when_smtp_connection_fails(self, mock_smtp_class, sample_report_file, smtp_config):
        mock_smtp_class.side_effect = ConnectionRefusedError("connection refused")

        with pytest.raises(ConnectionRefusedError):
            send_report_email(sample_report_file, smtp_config)

    @patch("validator.notifier.smtplib.SMTP")
    def test_raises_when_login_fails(self, mock_smtp_class, sample_report_file, smtp_config):
        import smtplib
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad credentials")
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        with pytest.raises(smtplib.SMTPAuthenticationError):
            send_report_email(sample_report_file, smtp_config)


# ---------------------------------------------------------------------------
# build_batch_report_email — pure, no network, tested directly
# ---------------------------------------------------------------------------

class TestBuildBatchReportEmail:
    def test_sets_from_and_to(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        assert msg["From"] == "bot@example.com"
        assert msg["To"] == "team@example.com"

    def test_subject_contains_timestamp(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        assert sample_batch_summary["timestamp"] in msg["Subject"]

    def test_custom_subject_used_when_provided(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary,
            subject="Custom Batch Subject"
        )
        assert msg["Subject"] == "Custom Batch Subject"

    def test_single_zip_attachment_regardless_of_file_count(self, sample_batch_report_files, sample_batch_summary):
        """Core requirement: N reports should produce exactly 1 attachment, not N."""
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_content_type() == "application/zip"

    def test_zip_contains_all_report_files(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        attachment = next(msg.iter_attachments())
        zip_bytes = attachment.get_content()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names_in_zip = set(zf.namelist())

        expected_names = {p.name for p in sample_batch_report_files}
        assert names_in_zip == expected_names

    def test_zip_file_contents_preserved(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        attachment = next(msg.iter_attachments())
        zip_bytes = attachment.get_content()

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            first_file = sample_batch_report_files[0]
            extracted = zf.read(first_file.name).decode()
            assert extracted == first_file.read_text()

    def test_body_contains_schema(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert sample_batch_summary["schema"] in body

    def test_body_contains_counts(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert "3" in body  # processed
        assert "2" in body  # passed
        assert "1" in body  # failed

    def test_body_contains_timestamp(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        body = msg.get_body(preferencelist=("plain",)).get_content()
        assert sample_batch_summary["timestamp"] in body

    def test_missing_summary_keys_do_not_crash(self, sample_batch_report_files):
        """A partial summary dict should not raise — missing fields are simply omitted."""
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", {}
        )
        assert msg["Subject"] is not None

    def test_zip_filename_contains_timestamp(self, sample_batch_report_files, sample_batch_summary):
        msg = build_batch_report_email(
            sample_batch_report_files, "team@example.com", "bot@example.com", sample_batch_summary
        )
        attachment = next(msg.iter_attachments())
        assert sample_batch_summary["timestamp"] in attachment.get_filename()

    def test_single_report_still_zipped(self, tmp_path, sample_batch_summary):
        """Even a batch of 1 file should still go through the zip path, for consistency."""
        single_file = tmp_path / "only_report.csv"
        single_file.write_text("file,status\nonly.csv,SUCCESS\n")

        msg = build_batch_report_email(
            [single_file], "team@example.com", "bot@example.com", sample_batch_summary
        )
        attachments = list(msg.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_content_type() == "application/zip"


# ---------------------------------------------------------------------------
# send_batch_report_email — network calls mocked
# ---------------------------------------------------------------------------

class TestSendBatchReportEmail:
    @patch("validator.notifier.smtplib.SMTP")
    def test_connects_to_configured_host_and_port(
        self, mock_smtp_class, sample_batch_report_files, smtp_config, sample_batch_summary
    ):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_batch_report_email(sample_batch_report_files, smtp_config, sample_batch_summary)

        mock_smtp_class.assert_called_once_with(
            smtp_config["host"], smtp_config["port"], timeout=30
        )

    @patch("validator.notifier.smtplib.SMTP")
    def test_sends_exactly_one_message(
        self, mock_smtp_class, sample_batch_report_files, smtp_config, sample_batch_summary
    ):
        """Core requirement: regardless of file count, send_message is called once."""
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_batch_report_email(sample_batch_report_files, smtp_config, sample_batch_summary)

        mock_server.send_message.assert_called_once()

    @patch("validator.notifier.smtplib.SMTP")
    def test_logs_in_with_credentials(
        self, mock_smtp_class, sample_batch_report_files, smtp_config, sample_batch_summary
    ):
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        send_batch_report_email(sample_batch_report_files, smtp_config, sample_batch_summary)

        mock_server.login.assert_called_once_with(
            smtp_config["username"], smtp_config["password"]
        )

    @patch("validator.notifier.smtplib.SMTP")
    def test_raises_when_smtp_connection_fails(
        self, mock_smtp_class, sample_batch_report_files, smtp_config, sample_batch_summary
    ):
        mock_smtp_class.side_effect = ConnectionRefusedError("connection refused")

        with pytest.raises(ConnectionRefusedError):
            send_batch_report_email(sample_batch_report_files, smtp_config, sample_batch_summary)