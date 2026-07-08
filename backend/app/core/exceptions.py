"""Domain exceptions mapped to API errors."""
from __future__ import annotations


class BeelineError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class GuardRailViolation(BeelineError):
    status_code = 422
    code = "guardrail_violation"


class CostThresholdExceeded(BeelineError):
    status_code = 422
    code = "cost_threshold_exceeded"


class ClarificationRequired(BeelineError):
    status_code = 200  # not an error to the user - handled in pipeline
    code = "clarification_required"


class ConnectorError(BeelineError):
    status_code = 502
    code = "connector_error"


class LLMUnavailable(BeelineError):
    status_code = 503
    code = "llm_unavailable"


class NotFound(BeelineError):
    status_code = 404
    code = "not_found"


class ValidationFailed(BeelineError):
    status_code = 422
    code = "validation_failed"
