from enum import StrEnum


class TicketSupportability(StrEnum):
    UNCHECKED = "unchecked"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
