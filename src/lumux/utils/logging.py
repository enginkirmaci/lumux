"""Shared logging utilities for Lumux."""

from datetime import datetime


def timed_print(*args, **kwargs) -> None:
    """Print with timestamp prefix.
    
    Args:
        *args: Values to print
        **kwargs: Keyword arguments passed to print()
    """
    prefix = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(prefix, *args, **kwargs)
