from enum import StrEnum


class AffectedService(StrEnum):
    API = "api"
    AGENT = "agent"
    DASHBOARD = "dashboard"
    USAGE_METERING = "usage_metering"
    WEBHOOKS = "webhooks"
