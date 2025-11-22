import sys
import types
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch


class _DummyObserver:
    def __init__(self, *args, **kwargs):
        pass

    def schedule(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def join(self):
        pass


class _DummyFileSystemEventHandler:
    pass


def _install_watchdog_stubs():
    watchdog_mod = types.ModuleType("watchdog")
    observers_mod = types.ModuleType("watchdog.observers")
    events_mod = types.ModuleType("watchdog.events")

    observers_mod.Observer = _DummyObserver
    events_mod.FileSystemEventHandler = _DummyFileSystemEventHandler

    watchdog_mod.observers = observers_mod
    watchdog_mod.events = events_mod

    sys.modules.setdefault("watchdog", watchdog_mod)
    sys.modules.setdefault("watchdog.observers", observers_mod)
    sys.modules.setdefault("watchdog.events", events_mod)


_install_watchdog_stubs()

import pelagos_daemon


class ConfirmActionExecutionTests(unittest.TestCase):
    def setUp(self):
        self.file_path = Path("sample.zip")
        self.base_action = {"name": "Manga", "type": "scp", "target": "manga"}

    def _mock_run(self, returncode=0, stdout="", stderr=""):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    @patch("pelagos_daemon.subprocess.run")
    def test_execute_selection_returns_accepted(self, mock_run):
        mock_run.return_value = self._mock_run(stdout="Execute")

        confirmed, reason = pelagos_daemon.confirm_action_execution(self.file_path, dict(self.base_action))

        self.assertTrue(confirmed)
        self.assertEqual(reason, "accepted")

    @patch("pelagos_daemon.subprocess.run")
    def test_skip_selection_returns_user_skip(self, mock_run):
        mock_run.return_value = self._mock_run(stdout="Skip")

        confirmed, reason = pelagos_daemon.confirm_action_execution(self.file_path, dict(self.base_action))

        self.assertFalse(confirmed)
        self.assertEqual(reason, "user_skip")

    @patch("pelagos_daemon.subprocess.run")
    def test_timeout_when_dialog_gives_up(self, mock_run):
        mock_run.return_value = self._mock_run(stdout="GAVE_UP")

        confirmed, reason = pelagos_daemon.confirm_action_execution(self.file_path, dict(self.base_action))

        self.assertFalse(confirmed)
        self.assertEqual(reason, "timeout")

    @patch("pelagos_daemon.subprocess.run")
    def test_error_when_subprocess_fails(self, mock_run):
        mock_run.return_value = self._mock_run(returncode=1, stderr="349:356: syntax error")

        confirmed, reason = pelagos_daemon.confirm_action_execution(self.file_path, dict(self.base_action))

        self.assertFalse(confirmed)
        self.assertEqual(reason, "error")

    @patch("pelagos_daemon.subprocess.run")
    def test_blank_stdout_counts_as_timeout(self, mock_run):
        mock_run.return_value = self._mock_run(stdout="")

        confirmed, reason = pelagos_daemon.confirm_action_execution(self.file_path, dict(self.base_action))

        self.assertFalse(confirmed)
        self.assertEqual(reason, "timeout")


if __name__ == "__main__":
    unittest.main()
