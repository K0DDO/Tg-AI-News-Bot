"""Domain enums shared across models and services."""

from enum import StrEnum


class MessageStatus(StrEnum):
    RAW = "raw"
    FILTERED_OUT = "filtered_out"
    PROCESSED = "processed"


class ReactionType(StrEnum):
    INTERESTING = "interesting"
    NOT_INTERESTING = "not_interesting"
