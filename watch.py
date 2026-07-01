"""
Watches the configured input folder and automatically triggers validation
for any new or modified CSV file, without needing cron or a manual run.

Runs as a long-lived process:
    python watch.py --schema schema.json

Each detected file is validated independently via main.py's single mode
(`--file X --schema Y`), so a partially-uploaded batch doesn't block other
files, and the DB/report/email behaviour of single mode applies as-is.

Debouncing: a file system 'created' event fires the moment a file appears,
which may be before a large file has finished being written/copied. To
avoid validating a half-written file, this waits for a 'quiet period'
(no further events on that path) before triggering — implemented with a
per-file threading.Timer that gets reset on every new event.
"""

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from validator.logger_config import setup_logger

setup_logger()
logger = logging.getLogger(__name__)


class DebouncedCsvHandler(FileSystemEventHandler):
    """
    Watches for .csv file create/modify events and triggers a validation
    run once a file has been quiet (no further events) for `quiet_seconds`.
    """

    def __init__(self, schema_name, quiet_seconds=2.0, main_script=None):
        super().__init__()
        self.schema_name = schema_name
        self.quiet_seconds = quiet_seconds
        self.main_script = main_script or str(Path(__file__).parent / "main.py")
        self._timers = {}
        self._lock = threading.Lock()

    def on_created(self, event):
        self._handle_event(event)

    def on_modified(self, event):
        self._handle_event(event)

    def _handle_event(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() != ".csv":
            return

        with self._lock:
            existing_timer = self._timers.get(path)
            if existing_timer:
                existing_timer.cancel()

            timer = threading.Timer(self.quiet_seconds, self._trigger, args=[path])
            timer.daemon = True
            self._timers[path] = timer
            timer.start()

    def _trigger(self, path):
        with self._lock:
            self._timers.pop(path, None)

        logger.info(f"[WATCHER] Detected stable file: {path.name}. Triggering validation.")

        cmd = [sys.executable, self.main_script, "--file", path.name, "--schema", self.schema_name]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(
                    f"[WATCHER] Validation run for {path.name} exited with code "
                    f"{result.returncode}. stderr:\n{result.stderr.strip()}"
                )
            else:
                logger.info(f"[WATCHER] Validation run for {path.name} completed successfully.")
        except Exception as e:
            logger.error(f"[WATCHER] Failed to trigger validation for {path.name}: {e}")

    def pending_count(self):
        """Number of files currently in their debounce window (not yet triggered)."""
        with self._lock:
            return len(self._timers)

    def stop(self):
        """
        Cancels all pending debounce timers without triggering them.
        Called on watcher shutdown so a file mid-debounce doesn't fire a
        stray validation run after the process has been told to exit.
        """
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


def load_input_folder():
    try:
        with open("config/config.json") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        logger.critical("Config file 'config/config.json' missing.")
        sys.exit(1)

    return config["input_folder"]


def main():
    parser = argparse.ArgumentParser(
        description="Watch the input folder and validate new CSV files automatically."
    )
    parser.add_argument(
        "--schema", required=True,
        help="Schema filename to validate against (must be in schema folder)."
    )
    parser.add_argument(
        "--quiet-seconds", type=float, default=2.0,
        help="Seconds of inactivity before a file is considered fully written (default: 2.0)."
    )
    args = parser.parse_args()

    input_folder = load_input_folder()

    event_handler = DebouncedCsvHandler(
        schema_name=args.schema,
        quiet_seconds=args.quiet_seconds
    )

    observer = Observer()
    observer.schedule(event_handler, path=input_folder, recursive=False)
    observer.start()

    logger.info(
        f"[WATCHER] Watching '{input_folder}' for new CSV files "
        f"(schema: {args.schema}, quiet period: {args.quiet_seconds}s). "
        f"Press Ctrl+C to stop."
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[WATCHER] Stopping...")
        observer.stop()
        event_handler.stop()

    observer.join()


if __name__ == "__main__":
    main()