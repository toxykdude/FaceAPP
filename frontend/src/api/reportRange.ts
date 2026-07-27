/**
 * Pure helpers converting the Reports page time-range selection into the
 * query params for `/sales/dashboard` and `/sales/report/summary`. Extracted
 * so the mapping logic is testable without rendering React/MUI.
 */

export const PRESET_DAYS: Record<string, number> = {
    today: 1,
    '7days': 7,
    '30days': 30,
    '90days': 90,
    year: 365,
};

export type ReportRangeParams =
    | { days: number }
    | { start_date: string; end_date: string };

class ReportRangeError extends Error {
    constructor(message: string) {
        super(message);
        this.name = 'ReportRangeError';
    }
}

/**
 * Build the API range params for a Reports selection. Presets return
 * `{ days }`; `timeRange === 'custom'` returns `{ start_date, end_date }`.
 * Throws on a reversed or incomplete custom range.
 */
export function buildReportRange(
    timeRange: string,
    customStart?: string,
    customEnd?: string,
): ReportRangeParams {
    if (timeRange === 'custom') {
        if (!customStart || !customEnd) {
            throw new ReportRangeError('Custom range requires both start and end dates');
        }
        if (customStart > customEnd) {
            throw new ReportRangeError('Custom range start must not be after end');
        }
        return { start_date: customStart, end_date: customEnd };
    }

    return { days: PRESET_DAYS[timeRange] ?? 30 };
}
