import { describe, it, expect } from 'vitest';
import { formatLocalDateTime } from '../utils/dateTime';

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
});
