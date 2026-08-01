import { describe, it, expect } from 'vitest';
import { formatDateLabel, formatLocalDateTime } from '../utils/dateTime';

describe('formatLocalDateTime (configured-timezone rendering)', () => {
  it('formats a UTC instant into the configured zone with date AND time', () => {
    // 2026-01-15T12:00:00Z in America/Santiago (DST, UTC-3) -> 09:00 local.
    const out = formatLocalDateTime('2026-01-15T12:00:00Z', 'America/Santiago');
    expect(out).toContain('2026');
    // MUST include a time component — the legacy renderer only showed a date.
    expect(out).toMatch(/09:00/);
  });

  it('applies a different zone than the legacy browser-local path', () => {
    // Same instant, Bogota (UTC-5) -> 07:00; Santiago (UTC-3) -> 09:00.
    const bogota = formatLocalDateTime('2026-01-15T12:00:00Z', 'America/Bogota');
    const santiago = formatLocalDateTime('2026-01-15T12:00:00Z', 'America/Santiago');
    expect(bogota).not.toEqual(santiago);
    expect(bogota).toMatch(/07:00/);
    expect(santiago).toMatch(/09:00/);
  });

  it('falls back gracefully when the timezone is empty/invalid', () => {
    // Invalid zone must not throw — it falls back to UTC so the cell still renders.
    const out = formatLocalDateTime('2026-01-15T12:00:00Z', 'not-a-zone');
    expect(out).toContain('2026');
  });

  it('renders the Santiago DST boundary at the correct local hour', () => {
    // 2026-09-07T03:00:00Z == 2026-09-07 00:00 Santiago (post spring-forward).
    const out = formatLocalDateTime('2026-09-07T03:00:00Z', 'America/Santiago');
    // Midnight may render as 00:00 or 24:00 depending on the ICU version, but
    // both prove the configured-zone offset (UTC-3) was applied.
    expect(out).toMatch(/(00:00|24:00)/);
    expect(out).toContain('2026-09-07');
  });

  it('treats a suffix-less timestamp (naive UTC) as UTC, not browser-local', () => {
    // The backend serializer now emits …Z, but stale/legacy payloads (and any
    // consumer seeing a suffix-less string) must resolve the instant as UTC.
    // '2026-01-15T12:00:00' naive-UTC == 07:00 Bogota; parsing it as LOCAL
    // time would render 07:00 only on UTC-5 machines and something else on
    // every other device.
    const out = formatLocalDateTime('2026-01-15T12:00:00', 'America/Bogota');
    expect(out).toContain('2026-01-15');
    expect(out).toMatch(/07:00/);
  });

  it('formats a YYYY-MM-DD bucket label without shifting the calendar day', () => {
    // Backend trends bucket in the configured app zone and emit date-only
    // strings; the label must never move to the previous local day.
    expect(formatDateLabel('2026-07-31')).toBe('Jul 31');
    expect(formatDateLabel('2026-01-05')).toBe('Jan 05');
    expect(formatDateLabel('garbage')).toBe('garbage');
  });
});
