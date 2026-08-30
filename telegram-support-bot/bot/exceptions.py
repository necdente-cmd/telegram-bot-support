"""Application-specific exceptions."""


class BotError(Exception):
    """Base error for expected application failures."""


class DatabaseError(BotError):
    """Raised when a database operation fails."""


class ExternalAPIError(BotError):
    """Raised when a third-party HTTP API call fails."""


class ConfigurationError(BotError):
    """Raised when required settings are missing or invalid."""
