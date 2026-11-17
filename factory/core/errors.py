"""Shared exception type."""


class FactoryError(Exception):
    """A user-facing error: the CLI prints the message and exits with code 1."""
