"""Provider error taxonomy.

The workflow engine only needs to know one thing about a failure:
is it worth retrying automatically? Network blips and timeouts are
(transient=True); a missing model or invalid configuration is not.
"""


class ProviderError(Exception):
    def __init__(self, message: str, *, transient: bool = False):
        super().__init__(message)
        self.transient = transient


class ProviderUnavailable(ProviderError):
    """The provider is intentionally disabled or not installed (use a fallback)."""

    def __init__(self, message: str):
        super().__init__(message, transient=False)
