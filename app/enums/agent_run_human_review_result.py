from enum import StrEnum


class AgentRunHumanReviewResult(StrEnum):
    ACCEPTED_WITHOUT_EDITING = "accepted_without_editing"
    EDITED = "edited"
