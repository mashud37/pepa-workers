"""Locate an indexed document's text and summary files inside the configured source folders.
The index stores bare file names, so moving the folders never breaks it.
"""
from pathlib import PureWindowsPath

import config


def text_file(stored):
    """The pepa-prep text file for a stored name, or None when the document has none.

    Older indexes hold a full path; only its file name is used, whichever slashes it has.
    """
    if not stored:
        return None
    return config.TEXT_DIR / PureWindowsPath(stored).name


def sum_file(stored):
    """The pepa-sum summary file for a stored name, or None when the document has none."""
    if not stored:
        return None
    return config.SUM_DIR / PureWindowsPath(stored).name
