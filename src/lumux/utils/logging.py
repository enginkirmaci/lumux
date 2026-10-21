"""Shared logging utilities for Lumux."""

from datetime import datetime


def timed_print(*args, **kwargs) -> None:
    """Print with timestamp prefix.
    
    Args:
        *args: Values to print
        **kwargs: Keyword arguments passed to print()
    """
    prefix = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    # Flush by default: stdout is block-buffered when piped (e.g. to
    # journald), and unflushed lines are lost exactly when they matter -
    # on a crash.
    kwargs.setdefault("flush", True)
    print(prefix, *args, **kwargs)
