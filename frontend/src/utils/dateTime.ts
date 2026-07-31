/**
 * Configured-timezone date/time rendering helpers.
 *
 * The backend persists timestamps as naive UTC and exposes the configured
 * IANA zone through /settings/public. These helpers render a UTC instant in
 * that zone (date AND time) so the UI matches the server-side report window.
 *
 * Kept pure (no React, no globals) so it is trivially testable.
 */

const DEFAULT_TIMEZONE = 'America/Bogota';

/**
 * Normalise a backend timestamp into a JavaScript Date.
 *
 * The backend persists timestamps as naive UTC; the wire format is
 * self-describing UTC ("…Z") since the schema serializers were fixed. Older
 * cached payloads — and any consumer that sees a suffix-less string — must
 * still resolve the instant as UTC: ECMA-262 parses a date-time without an
 * offset as browser-LOCAL time, which shifts every row by the device's UTC
 * offset and makes two computers render different local times for the same
 * sale. Returns null for values that cannot be parsed.
 */
export function parseUtcInstant(isoUtc: string): Date | null {
    if (!isoUtc) return null;
    const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/.test(isoUtc) ? isoUtc : `${isoUtc}Z`;
    const instant = new Date(normalized);
    return Number.isNaN(instant.getTime()) ? null : instant;
}

/**
 * Format an ISO/UTC timestamp in the configured IANA timezone, including BOTH
 * the date and the time (the legacy renderer showed only a browser-local
 * date). Falls back to UTC when the zone is invalid/empty so the cell always
 * renders instead of throwing.
 */
export function formatLocalDateTime(isoUtc: string, timezone?: string): string {
    if (!isoUtc) return '';
    const tz = timezone && timezone.trim() ? timezone : DEFAULT_TIMEZONE;
    const instant = parseUtcInstant(isoUtc);
    if (!instant) return isoUtc;
    try {
        // toISOString-style parts via Intl so we control the zone exactly.
        return new Intl.DateTimeFormat('en-CA', {
            timeZone: tz,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }).format(instant);
    } catch {
        // Invalid zone — fall back to UTC so the UI keeps rendering.
        return instant.toISOString().replace('T', ' ').slice(0, 16);
    }
}

/**
 * Format a plain ``YYYY-MM-DD`` bucket label without any timezone conversion.
 *
 * Backend report trends bucket by the CONFIGURED app timezone and emit
 * ``YYYY-MM-DD``. `date-fns`'s parseISO treats a date-only string as UTC
 * midnight, and formatting that instant in a browser west of Greenwich would
 * shift the label to the PREVIOUS day. Building the label from the date's own
 * parts keeps the axis identical to the server's buckets on every device.
 */
export function formatDateLabel(dateStr: string): string {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateStr);
    if (!m) return dateStr;
    const [, , month, day] = m;
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const monthName = MONTHS[Number(month) - 1];
    return monthName ? `${monthName} ${day}` : dateStr;
}
