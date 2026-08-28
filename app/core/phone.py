def normalize_phone(v) -> str | None:
    """Normalize a phone number to a canonical form for matching.

    Strips formatting characters and converts common Ethiopian local
    formats to the international +251 form so that "+251911234567",
    "251911234567", "0911234567" and "911234567" all resolve to the
    same value. Returns None for empty/invalid input.
    """
    if not v:
        return None
    s = str(v).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10 and digits.startswith("0"):
        return "+251" + digits[1:]
    if len(digits) == 9:
        return "+251" + digits
    if len(digits) == 12 and digits.startswith("251"):
        return "+" + digits
    return ("+" + digits) if s.startswith("+") else digits