"""Tests for the generated tray-icon subprocess scripts.

The SNI script is executed for real (with a stubbed pydbus session bus), so
these tests exercise the actual code that runs in the tray subprocess.
"""

import io
from unittest.mock import patch

from gi.repository import GLib

from lumux.gui.tray_icon import TrayIcon


class FakeSessionBus:
    def publish(self, name, *objects):
        pass

    def get(self, name, path):
        raise Exception("no StatusNotifierWatcher in test")


def test_sni_tray_quits_on_stdin_eof():
    """When the main app dies, the tray's stdin hits EOF. The tray must exit
    instead of lingering as a zombie icon for a dead app."""
    script = TrayIcon._generate_sni_script(None)
    namespace = {"__name__": "sni_tray_under_test"}

    with (
        patch("pydbus.SessionBus", FakeSessionBus),
        patch("sys.stdin", io.StringIO("")),
    ):
        exec(compile(script, "<sni-tray>", "exec"), namespace)
        app = namespace["TrayApp"]()

        timed_out = []

        def _guard():
            timed_out.append(True)
            app.loop.quit()
            return False

        GLib.timeout_add(2000, _guard)
        app.loop.run()

    assert not timed_out, "tray loop did not quit on stdin EOF"


def test_sni_tray_still_quits_on_quit_command():
    """The regular quit path (main app sends {"action": "quit"}) keeps working."""
    script = TrayIcon._generate_sni_script(None)
    namespace = {"__name__": "sni_tray_under_test"}

    with (
        patch("pydbus.SessionBus", FakeSessionBus),
        patch("sys.stdin", io.StringIO('{"action": "quit"}\n')),
    ):
        exec(compile(script, "<sni-tray>", "exec"), namespace)
        app = namespace["TrayApp"]()

        timed_out = []

        def _guard():
            timed_out.append(True)
            app.loop.quit()
            return False

        GLib.timeout_add(2000, _guard)
        app.loop.run()

    assert not timed_out
