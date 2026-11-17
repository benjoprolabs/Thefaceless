"""Shared exception type and friendly descriptions of file-system errors."""

import errno
from pathlib import Path


class FactoryError(Exception):
    """A user-facing error: the CLI prints the message and exits with code 1."""


def _display_path(filename, root=None):
    if not filename:
        return "a file"
    path = Path(filename)
    if root is not None:
        try:
            return str(path.resolve().relative_to(Path(root).resolve()))
        except (ValueError, OSError):
            pass
    return str(path)


def describe_os_error(error, root=None):
    """Turn an OSError (permission denied, missing file, disk full...) into a
    plain-language message with a suggested fix. Never includes a traceback."""
    path = _display_path(getattr(error, "filename", None), root)
    if isinstance(error, PermissionError):
        return (f"Permission denied: cannot access '{path}'.\n"
                "  - If the file is open in another program (for example Excel), close it and try again.\n"
                "  - Check that your user account is allowed to read and change files in this folder.\n"
                "  - On macOS/Linux, `ls -l` shows the file's permissions.")
    if isinstance(error, FileNotFoundError):
        return f"File or folder not found: '{path}'. It may have been moved, renamed or deleted."
    if isinstance(error, IsADirectoryError):
        return f"Expected a file but found a folder: '{path}'."
    if isinstance(error, NotADirectoryError):
        return f"Expected a folder but found a file: '{path}'."
    if error.errno == errno.ENOSPC:
        return f"Not enough disk space to save '{path}'. Free up some space and try again."
    if error.errno == errno.EROFS:
        return f"Cannot save '{path}': the disk or folder is read-only."
    reason = error.strerror or error.__class__.__name__
    return f"Could not access '{path}': {reason}."
