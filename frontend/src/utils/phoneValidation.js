/**
 * RVFitness Frontend Phone Number Validation Utility.
 * Rejects alphabetic characters, invalid symbols, and malformed lengths.
 * Matches backend validation rules in backend/app/core/validation.py.
 */

export function validatePhoneNumber(value, required = false) {
  if (value === undefined || value === null || String(value).trim() === '') {
    if (required) {
      return 'Phone number is required.';
    }
    return null;
  }

  const raw = String(value).trim();

  // 1. Reject alphabetic characters explicitly
  if (/[a-zA-Z]/.test(raw)) {
    return 'Phone number cannot contain alphabetic characters or words.';
  }

  // 2. Reject disallowed symbols
  if (/[^\d+\s\-().]/.test(raw)) {
    return 'Phone number contains invalid special characters.';
  }

  const digits = raw.replace(/\D/g, '');
  if (!digits) {
    return 'Phone number must contain numeric digits.';
  }

  // 3. Length constraints
  if (digits.length < 7) {
    return 'Phone number is too short (minimum 7 digits required).';
  }
  if (digits.length > 15) {
    return 'Phone number is too long (maximum 15 digits allowed by E.164 standard).';
  }

  const hasLeadingPlus = raw.startsWith('+');

  // 4. Indian number with +91
  if (hasLeadingPlus && raw.startsWith('+91')) {
    const national = digits.startsWith('91') ? digits.slice(2) : digits;
    if (national.length !== 10) {
      return 'Indian mobile numbers with +91 must have exactly 10 digits following country code.';
    }
    if (!['6', '7', '8', '9'].includes(national[0])) {
      return 'Indian mobile numbers must start with digit 6, 7, 8, or 9.';
    }
    return null;
  }

  // 5. 10-digit Indian number without prefix
  if (!hasLeadingPlus && digits.length === 10) {
    if (!['6', '7', '8', '9'].includes(digits[0])) {
      return 'Indian mobile numbers must start with digit 6, 7, 8, or 9.';
    }
    return null;
  }

  // 6. 11-digit Indian number with leading 0
  if (!hasLeadingPlus && digits.length === 11 && digits.startsWith('0')) {
    if (!['6', '7', '8', '9'].includes(digits[1])) {
      return 'Indian mobile numbers must start with digit 6, 7, 8, or 9.';
    }
    return null;
  }

  return null;
}
