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
});
