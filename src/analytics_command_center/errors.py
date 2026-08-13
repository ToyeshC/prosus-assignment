class AccessDenied(PermissionError):
    """Raised before any database or agent context is exposed."""


class ConfigurationError(RuntimeError):
    """Raised when a user requests live agents without runtime configuration."""


class UnsafeSQL(ValueError):
    """Raised for SQL outside the read-only policy."""


class QueryExecutionError(RuntimeError):
    """Sanitized database execution error suitable for agent repair context."""


def safe_live_error(_: Exception) -> str:
    """User-facing external-service failure text that never echoes exception payloads."""
    return "Live agent request failed. Check connectivity and OpenAI configuration, then try again."
