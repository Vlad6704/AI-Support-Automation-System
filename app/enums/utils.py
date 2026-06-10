from enum import StrEnum


def enum_values(enum_type: type[StrEnum]) -> list[str]:
    return [item.value for item in enum_type]
