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
 * Format an ISO/UTC timestamp in the configured IANA timezone, including BOTH
 * the date and the time (the legacy renderer showed only a browser-local
 * date). Falls back to UTC when the zone is invalid/empty so the cell always
 * renders instead of throwing.
 */
export function formatLocalDateTime(isoUtc: string, timezone?: string): string {
    if (!isoUtc) return '';
    const tz = timezone && timezone.trim() ? timezone : DEFAULT_TIMEZONE;
    const instant = new Date(isoUtc);
    if (Number.isNaN(instant.getTime())) return isoUtc;
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
