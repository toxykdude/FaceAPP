import { describe, it, expect } from 'vitest';
import { buildReportRange, type ReportRangeParams } from '../api/reportRange';

describe('buildReportRange', () => {
  describe('preset ranges', () => {
    it('maps the "today" preset to days=1', () => {
      expect(buildReportRange('today')).toEqual({ days: 1 });
    });

    it('maps the "30days" preset to days=30', () => {
      expect(buildReportRange('30days')).toEqual({ days: 30 });
    });

    it('maps the "year" preset to days=365', () => {
      expect(buildReportRange('year')).toEqual({ days: 365 });
    });

    it('falls back to 30 days for an unknown preset', () => {
      expect(buildReportRange('whatever')).toEqual({ days: 30 });
    });
  });

  describe('custom ranges', () => {
    it('returns start_date/end_date params for a valid custom interval', () => {
      const params = buildReportRange('custom', '2026-01-10', '2026-01-20');
      expect(params).toEqual({ start_date: '2026-01-10', end_date: '2026-01-20' });
    });

    it('accepts a single-day custom interval (start == end)', () => {
      const params = buildReportRange('custom', '2026-02-03', '2026-02-03');
      expect(params).toEqual({ start_date: '2026-02-03', end_date: '2026-02-03' });
    });

    it('throws on a reversed custom interval', () => {
      expect(() => buildReportRange('custom', '2026-01-20', '2026-01-10')).toThrow();
    });

    it('throws when custom is selected but a date is missing', () => {
      expect(() => buildReportRange('custom', '2026-01-10', undefined)).toThrow();
      expect(() => buildReportRange('custom', undefined, '2026-01-20')).toThrow();
    });
  });

  describe('return shape', () => {
    it('never mixes days and custom params', () => {
      const preset: ReportRangeParams = buildReportRange('7days');
      expect(preset).not.toHaveProperty('start_date');
      expect(preset).toHaveProperty('days');

      const custom: ReportRangeParams = buildReportRange('custom', '2026-01-10', '2026-01-11');
      expect(custom).not.toHaveProperty('days');
      expect(custom).toHaveProperty('start_date');
      expect(custom).toHaveProperty('end_date');
    });
  });

  // Regression contract for the custom date-range feature (user-reported
  // "range not working / not visible"). The picker emits date-only strings and
  // this mapping is what every consumer (dashboard, summary, CSV export)
  // relies on — pin it so a future refactor cannot silently change the wire
  // shape.
  describe('custom-range regression contract', () => {
    it('passes date-only strings through unchanged, including month/DST boundaries', () => {
      // DST-change weekend in America/Santiago (2026-09-06): the frontend does
      // NO timezone math on these strings, the backend owns the window.
      expect(buildReportRange('custom', '2026-09-05', '2026-09-07')).toEqual({
        start_date: '2026-09-05',
        end_date: '2026-09-07',
      });
      expect(buildReportRange('custom', '2026-01-31', '2026-02-01')).toEqual({
        start_date: '2026-01-31',
        end_date: '2026-02-01',
      });
    });

    it('rejects reversed ranges across a month boundary', () => {
      expect(() => buildReportRange('custom', '2026-02-01', '2026-01-31')).toThrow();
    });

    it('emits exactly start_date/end_date and nothing else for custom', () => {
      const params = buildReportRange('custom', '2026-01-10', '2026-01-20');
      expect(Object.keys(params).sort()).toEqual(['end_date', 'start_date']);
    });
  });
});
