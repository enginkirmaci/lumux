from unittest.mock import patch

from lumux.utils.logging import timed_print


def test_timed_print_flushes():
    """Log output must not sit in the stdout block buffer: when stdout is a
    journald pipe, unflushed lines are lost on a crash - exactly when they
    are needed."""
    with patch("builtins.print") as mock_print:
        timed_print("hello")

    assert mock_print.call_args.kwargs.get("flush") is True


def test_timed_print_respects_explicit_flush_false():
    with patch("builtins.print") as mock_print:
        timed_print("hello", flush=False)

    assert mock_print.call_args.kwargs.get("flush") is False
