"""
Input validation utilities for RVFitness.
Provides phone number normalization, sanitization, and security checks.
"""

import re
from typing import Optional


# Regular expressions for phone validation
ALPHA_PATTERN = re.compile(r"[a-zA-Z]")
DISALLOWED_SYMBOLS_PATTERN = re.compile(r"[^\d+\s\-().]")
DIGITS_ONLY_PATTERN = re.compile(r"\D")


def validate_and_normalize_phone(
    value: Optional[str],
    required: bool = False,
    field_name: str = "phone",
) -> Optional[str]:
    """
    Validates and normalizes phone numbers.
    Rejects alphabetic characters, invalid symbols, and malformed length.
    Supports Indian mobile formats (10-digit, +91, 0 prefix) and international E.164 formats.

    Args:
        value: Input phone string.
        required: If True, empty or whitespace-only values raise ValueError.
        field_name: Name of field for error reporting.

    Returns:
        Normalized phone string, or None if optional and empty.

    Raises:
        ValueError: If value violates format, length, or character constraints.
    """
    if value is None:
        if required:
            raise ValueError(f"Phone number ({field_name}) is required.")
        return None

    raw_val = str(value).strip()
    if not raw_val:
        if required:
            raise ValueError(f"Phone number ({field_name}) cannot be empty.")
        return None

    # 1. Reject alphabetic characters explicitly
    if ALPHA_PATTERN.search(raw_val):
        raise ValueError("Phone number cannot contain alphabetic characters or words.")

    # 2. Reject disallowed symbols (only digits, +, -, (, ), ., and spaces are permitted)
    if DISALLOWED_SYMBOLS_PATTERN.search(raw_val):
        raise ValueError("Phone number contains invalid special characters.")

    has_leading_plus = raw_val.startswith("+")

    # 3. Extract pure digits
    digits = DIGITS_ONLY_PATTERN.sub("", raw_val)

    if not digits:
        raise ValueError("Phone number must contain numeric digits.")

    # 4. Length constraints
    if len(digits) < 7:
        raise ValueError("Phone number is too short (minimum 7 digits required).")
    if len(digits) > 15:
        raise ValueError("Phone number is too long (maximum 15 digits allowed by E.164 standard).")

    # 5. Format validation
    # Case A: Indian number starting with +91 or 91 country code (e.g. +91, (+91), 91XXXXXXXXXX)
    if (digits.startswith("91") and len(digits) == 12) or (has_leading_plus and raw_val.startswith("+91")):
        national_digits = digits[2:] if digits.startswith("91") else digits
        if len(national_digits) != 10:
            raise ValueError("Indian mobile numbers with +91 must have exactly 10 digits following country code.")
        if national_digits[0] not in {"6", "7", "8", "9"}:
            raise ValueError("Indian mobile numbers must start with digit 6, 7, 8, or 9.")
        return f"+91 {national_digits[:5]} {national_digits[5:]}"

    # Case B: Standard 10-digit Indian mobile number without prefix
    if not has_leading_plus and len(digits) == 10:
        if digits[0] not in {"6", "7", "8", "9"}:
            raise ValueError("10-digit mobile numbers must start with digit 6, 7, 8, or 9.")
        return f"+91 {digits[:5]} {digits[5:]}"

    # Case C: Indian number with leading 0 (e.g. 09822012345)
    if not has_leading_plus and len(digits) == 11 and digits.startswith("0") and digits[1] in {"6", "7", "8", "9"}:
        national = digits[1:]
        return f"+91 {national[:5]} {national[5:]}"

    # Case D: International E.164 format with leading +
    if has_leading_plus:
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("International phone numbers must contain between 7 and 15 digits.")
        return f"+{digits}"

    # Case E: Other standard numeric phone numbers (7 to 15 digits)
    return digits
