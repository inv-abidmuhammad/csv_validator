import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validator.progress import ProgressReporter


class FakeStream(io.StringIO):
    """io.StringIO with a controllable isatty() result, since real
    io.StringIO always reports False."""

    def __init__(self, is_tty):
        super().__init__()
        self._is_tty = is_tty

    def isatty(self):
        return self._is_tty


# ---------------------------------------------------------------------------
# Interactive mode (TTY) — bar should render
# ---------------------------------------------------------------------------

class TestProgressReporterInteractive:
    def test_writes_nothing_before_first_update(self):
        stream = FakeStream(is_tty=True)
        ProgressReporter(total=5, stream=stream)
        assert stream.getvalue() == ""

    def test_writes_output_on_update(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.update("file1.csv")
        assert stream.getvalue() != ""

    def test_output_contains_current_and_total(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.update("file1.csv")
        assert "1/5" in stream.getvalue()

    def test_output_contains_item_name(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.update("customers.csv")
        assert "customers.csv" in stream.getvalue()

    def test_output_contains_percentage(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=4, stream=stream)
        reporter.update()
        assert "25%" in stream.getvalue()

    def test_uses_carriage_return_not_newline_between_updates(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=3, stream=stream)
        reporter.update("a.csv")
        reporter.update("b.csv")
        output = stream.getvalue()
        # Only the final update (100%) should add a trailing newline;
        # updates should be separated by \r, not \n
        assert output.count("\r") == 2

    def test_reaching_total_adds_trailing_newline(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=2, stream=stream)
        reporter.update("a.csv")
        reporter.update("b.csv")
        assert stream.getvalue().endswith("\n")

    def test_bar_fully_filled_at_100_percent(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=1, stream=stream)
        reporter.update("only.csv")
        assert "#" * ProgressReporter.BAR_WIDTH in stream.getvalue()

    def test_current_increments_correctly(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=3, stream=stream)
        reporter.update()
        reporter.update()
        assert reporter.current == 2

    def test_multiple_updates_show_progress(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=10, stream=stream)
        for i in range(10):
            reporter.update(f"file{i}.csv")
        assert "10/10" in stream.getvalue()
        assert "100%" in stream.getvalue()


# ---------------------------------------------------------------------------
# Non-interactive mode (redirected output) — nothing should render
# ---------------------------------------------------------------------------

class TestProgressReporterNonInteractive:
    def test_writes_nothing_on_update(self):
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.update("file1.csv")
        assert stream.getvalue() == ""

    def test_writes_nothing_across_many_updates(self):
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=50, stream=stream)
        for i in range(50):
            reporter.update(f"file{i}.csv")
        assert stream.getvalue() == ""

    def test_current_still_increments(self):
        """Internal state tracking should work even though nothing renders."""
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=3, stream=stream)
        reporter.update()
        reporter.update()
        assert reporter.current == 2

    def test_no_carriage_returns_ever_written(self):
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=5, stream=stream)
        for i in range(5):
            reporter.update(f"file{i}.csv")
        assert "\r" not in stream.getvalue()

    def test_finish_writes_nothing(self):
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.update("file1.csv")
        reporter.finish()
        assert stream.getvalue() == ""


# ---------------------------------------------------------------------------
# Auto-detection via stream.isatty()
# ---------------------------------------------------------------------------

class TestProgressReporterAutoDetection:
    def test_defaults_to_stream_isatty_true(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream)
        assert reporter.interactive is True

    def test_defaults_to_stream_isatty_false(self):
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=5, stream=stream)
        assert reporter.interactive is False

    def test_explicit_interactive_overrides_isatty(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream, interactive=False)
        reporter.update("a.csv")
        assert stream.getvalue() == ""

    def test_explicit_non_interactive_stream_can_be_forced_interactive(self):
        stream = FakeStream(is_tty=False)
        reporter = ProgressReporter(total=5, stream=stream, interactive=True)
        reporter.update("a.csv")
        assert stream.getvalue() != ""


# ---------------------------------------------------------------------------
# finish()
# ---------------------------------------------------------------------------

class TestProgressReporterFinish:
    def test_finish_adds_newline_when_stopped_early(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=10, stream=stream)
        reporter.update("a.csv")
        reporter.update("b.csv")  # only 2 of 10 — stopped "early"
        reporter.finish()
        assert stream.getvalue().endswith("\n")

    def test_finish_is_noop_if_already_complete(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=1, stream=stream)
        reporter.update("only.csv")
        output_before = stream.getvalue()
        reporter.finish()
        assert stream.getvalue() == output_before  # no duplicate newline added

    def test_finish_is_noop_if_never_updated(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.finish()
        assert stream.getvalue() == ""

    def test_finish_safe_to_call_multiple_times(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=5, stream=stream)
        reporter.update("a.csv")
        reporter.finish()
        output_after_first = stream.getvalue()
        reporter.finish()
        assert stream.getvalue() == output_after_first


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestProgressReporterEdgeCases:
    def test_total_zero_does_not_crash(self):
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=0, stream=stream)
        reporter.update("a.csv")  # should not raise ZeroDivisionError
        assert stream.getvalue() == ""

    def test_more_updates_than_total_does_not_crash(self):
        """Defensive: if update() is somehow called more times than total,
        percentage should cap at 100% rather than exceeding it."""
        stream = FakeStream(is_tty=True)
        reporter = ProgressReporter(total=2, stream=stream)
        reporter.update("a.csv")
        reporter.update("b.csv")
        reporter.update("c.csv")  # 3rd update beyond total
        assert "100%" in stream.getvalue()

    def test_default_stream_is_stdout(self):
        reporter = ProgressReporter(total=5)
        assert reporter.stream is sys.stdout