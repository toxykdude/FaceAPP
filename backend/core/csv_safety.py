"""CSV safety helpers (spreadsheet formula injection, CWE-1236)."""


def sanitize_csv_cell(value) -> str:
    """Neutralize spreadsheet formula injection.

    A cell whose first character is a spreadsheet formula metacharacter
    (= + - @ \\t \\r) is prefixed with a single quote so Excel/LibreOffice
    treat it as literal text instead of evaluating it as a formula. CSV itself
    has no escaping that prevents this, so the neutralization must happen on
    the cell value before serialization. Non-string values are stringified;
    None becomes the empty string.
    """
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s
