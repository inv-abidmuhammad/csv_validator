import sys


class ProgressReporter:
    """
    Renders a simple, self-overwriting progress bar for interactive
    terminals only.

    In non-interactive contexts (output redirected to a file or pipe, as
    happens under cron) rendering is skipped entirely. The existing
    per-file log lines already provide progress visibility there, and
    \\r-based output would just dump garbage control characters into a
    log file.

    `stream` and `interactive` can be overridden explicitly for testing —
    by default `interactive` is auto-detected from `stream.isatty()`.
    """

    BAR_WIDTH = 30

    def __init__(self, total, label="Processing", stream=None, interactive=None):
        self.total = total
        self.label = label
        self.current = 0
        self.stream = stream if stream is not None else sys.stdout
        self.interactive = (
            self.stream.isatty() if interactive is None else interactive
        )
        self._finished = False

    def update(self, item_name=""):
        """Advances progress by one item and re-renders the bar (if interactive)."""
        self.current += 1

        if not self.interactive or self.total == 0:
            return

        self._render(item_name)

    def _render(self, item_name):
        fraction = min(self.current / self.total, 1.0)
        filled = int(self.BAR_WIDTH * fraction)
        bar = "#" * filled + "-" * (self.BAR_WIDTH - filled)
        percent = int(fraction * 100)

        line = f"\r{self.label}: |{bar}| {self.current}/{self.total} ({percent}%) {item_name}"
        # Pad with trailing spaces so a shorter line fully overwrites a
        # longer previous one (e.g. a long filename followed by a short one).
        self.stream.write(line.ljust(len(line) + 10))
        self.stream.flush()

        if self.current >= self.total:
            self.stream.write("\n")
            self.stream.flush()

    def finish(self):
        """
        Ensures the cursor ends on a fresh line even if the reporter never
        reached 100% (e.g. the run exited early). Safe to call multiple
        times or when nothing was ever rendered.
        """
        if self._finished:
            return

        self._finished = True

        if self.interactive and 0 < self.current < self.total:
            self.stream.write("\n")
            self.stream.flush()