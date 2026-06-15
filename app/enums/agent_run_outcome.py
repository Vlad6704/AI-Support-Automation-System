from enum import StrEnum


class AgentRunOutcome(StrEnum):
    AUTOMATED = "automated"
    AWAITING_REVIEW = "awaiting_review"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"
