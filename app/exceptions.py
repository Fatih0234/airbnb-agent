"""Scraper-specific exceptions for deterministic error handling."""


class ScraperException(Exception):
    """Base exception for all scraper errors."""

    pass


class CaptchaError(ScraperException):
    """Raised when a CAPTCHA challenge is detected. Fail fast."""

    pass


class RateLimitError(ScraperException):
    """Raised when rate limited by the target site. Backoff and retry."""

    pass


class NoResultsError(ScraperException):
    """Raised when search returns zero results. Valid empty state."""

    pass


class ExtractionError(ScraperException):
    """Raised when data extraction fails for a specific listing. Retry individually."""

    def __init__(self, message: str, listing_id: str | None = None):
        super().__init__(message)
        self.listing_id = listing_id


class NavigationError(ScraperException):
    """Raised when page navigation fails (timeout, blocked, etc.)."""

    pass


class ParseError(ScraperException):
    """Raised when HTML/JSON parsing fails."""

    pass
