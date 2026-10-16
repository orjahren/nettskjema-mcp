# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Oliver Ruste Jahren
"""Enums extracted from the Nettskjema v3 OpenAPI spec.

All enums are defined inline on DTO properties in the spec, not as top-level
components/schemas entries. Members are listed in spec order.
"""

from enum import StrEnum


class ElementType(StrEnum):
    """Element types (ElementDTO.elementType)."""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    HEADING = "HEADING"
    PAGE_BREAK = "PAGE_BREAK"
    ACCORDION = "ACCORDION"
    RADIO = "RADIO"
    SELECT = "SELECT"
    CHECKBOX = "CHECKBOX"
    MATRIX_RADIO = "MATRIX_RADIO"
    MATRIX_CHECKBOX = "MATRIX_CHECKBOX"
    DATE = "DATE"
    NAME = "NAME"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    NUMBER = "NUMBER"
    QUESTION = "QUESTION"
    USERNAME = "USERNAME"
    ATTACHMENT = "ATTACHMENT"
    LINEAR_SCALE = "LINEAR_SCALE"
    NATIONAL_ID_NUMBER = "NATIONAL_ID_NUMBER"
    QUESTION_MULTILINE = "QUESTION_MULTILINE"
    SUBMISSION_REFERENCE = "SUBMISSION_REFERENCE"


class FormType(StrEnum):
    """Form types (FormSettingsDTO.formType)."""

    DEFAULT = "DEFAULT"
    HIGH_SECURITY = "HIGH_SECURITY"
    SIGN_UP = "SIGN_UP"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    COURSE_EVALUATION = "COURSE_EVALUATION"


class RespondentGroup(StrEnum):
    """Respondent groups (FormSettingsDTO.respondentGroup)."""

    ALL = "ALL"
    FEIDE = "FEIDE"
    FEIDE_AND_EDUGAIN = "FEIDE_AND_EDUGAIN"
    INVITED = "INVITED"
    INVITED_CHAINED_SIGNING = "INVITED_CHAINED_SIGNING"
    ID_PORTEN_LEVEL_3 = "ID_PORTEN_LEVEL_3"
    ID_PORTEN_LEVEL_4 = "ID_PORTEN_LEVEL_4"
    ID_PORTEN_LEVEL_3_SIGNING = "ID_PORTEN_LEVEL_3_SIGNING"
    ID_PORTEN_LEVEL_4_SIGNING = "ID_PORTEN_LEVEL_4_SIGNING"
    HELSENORGE = "HELSENORGE"
    HELSENORGE_SIGNING = "HELSENORGE_SIGNING"


class DeliveryDestination(StrEnum):
    """Delivery destinations (FormSettingsDTO.deliveryDestination)."""

    DATABASE = "DATABASE"
    DATABASE_ENCRYPTED = "DATABASE_ENCRYPTED"
    EDUCLOUD = "EDUCLOUD"
    TSD = "TSD"


class AnswerType(StrEnum):
    """Answer types (ClientAnswerDTO.type)."""

    SINGLE_OPTION = "SINGLE_OPTION"
    MULTIPLE_OPTIONS = "MULTIPLE_OPTIONS"
    TEXT = "TEXT"
    FILE = "FILE"
    DATE_TIME = "DATE_TIME"
    DATE = "DATE"
    TIME = "TIME"
    NOT_PROVIDED = "NOT_PROVIDED"


class DateFormat(StrEnum):
    """Date formats (ElementDTO.dateFormat)."""

    DATE = "DATE"
    DATE_TIME = "DATE_TIME"
    TIME = "TIME"


class LinearScaleType(StrEnum):
    """Linear scale types (ElementDTO.linearScaleType)."""

    NONE = "NONE"
    START_END = "START_END"
    START_MID_END = "START_MID_END"
    TEXT_AND_NUM = "TEXT_AND_NUM"
    ALL = "ALL"


class NationalIdNumberType(StrEnum):
    """National ID number types (ElementDTO.nationalIdNumberType)."""

    ONLY_NUMBERS = "ONLY_NUMBERS"
    NORWEGIAN_ID_NUMBER = "NORWEGIAN_ID_NUMBER"
    CUSTOM = "CUSTOM"


class ScoreResultDisplayType(StrEnum):
    """Score result display types (FormSettingsDTO.scoreResultDisplayType)."""

    NONE = "NONE"
    SCORE_ONLY = "SCORE_ONLY"
    FULL_SOLUTION_AND_SCORE = "FULL_SOLUTION_AND_SCORE"
    ONLY_CHECK_ANSWER = "ONLY_CHECK_ANSWER"


class EditorsSubmissionEmailType(StrEnum):
    """Editors submission email types (FormSettingsDTO.editorsSubmissionEmailType)."""

    NONE = "NONE"
    MESSAGE = "MESSAGE"
    SUBMISSION = "SUBMISSION"
