class CustomerNotFoundError(ValueError):
    pass


class TicketNotFoundError(ValueError):
    pass


class AgentResponseError(RuntimeError):
    pass


class DraftReviewNotFoundError(ValueError):
    pass
