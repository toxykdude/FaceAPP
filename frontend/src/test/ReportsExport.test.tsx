import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { Reports } from '@/pages/Reports/Reports';
import { salesApi } from '@/api/sales';

vi.mock('react-chartjs-2', () => ({ Line: () => null, Bar: () => null, Doughnut: () => null }));

// vi.hoisted runs before vi.mock factories are evaluated, so the mock fn is
// defined in time to be both returned by the factory and asserted against here.
const { exportReportMock } = vi.hoisted(() => ({ exportReportMock: vi.fn() }));
exportReportMock.mockResolvedValue(new Blob(['csv'], { type: 'text/csv' }));

vi.mock('@/api/sales', () => ({
  salesApi: {
    getDashboardReport: vi.fn().mockResolvedValue({
      revenue_trend: [], member_growth: [], membership_distribution: [], peak_hours: [],
      checkin_trend: [], new_signups: { this_month: 0, last_month: 0, change_pct: 0 },
      active_vs_expired: { active: 0, expired: 0 }, checkins_today: 0, checkins_week: 0,
      revenue_change_pct: 0,
    }),
    getReportSummary: vi.fn().mockResolvedValue({
      total_revenue: 0, total_transactions: 0, transactions_by_method: {}, revenue_by_method: {},
    }),
    getTransactions: vi.fn().mockResolvedValue({ total: 0, transactions: [] }),
    exportReport: exportReportMock,
  },
}));

vi.mock('@/api/settings', () => ({
  settingsApi: {
    getPublic: vi.fn().mockResolvedValue({ timezone: 'America/Bogota' }),
  },
}));

function renderReports() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider><Reports /></LanguageProvider>
    </QueryClientProvider>,
  );
}

describe('Reports export wiring', () => {
  beforeEach(() => {
    exportReportMock.mockClear();
    // jsdom does not implement URL.createObjectURL / anchor.click natively.
    URL.createObjectURL = vi.fn(() => 'blob:mock');
    URL.revokeObjectURL = vi.fn();
    // Capture anchor clicks instead of navigating.
    HTMLAnchorElement.prototype.click = vi.fn();
  });

  it('clicking Export calls salesApi.exportReport with the current preset range', async () => {
    const user = userEvent.setup();
    renderReports();
    await waitFor(() => expect(salesApi.getReportSummary).toHaveBeenCalled());

    // Default preset is 30days -> export must receive the resolved { days: 30 }.
    await user.click(screen.getByRole('button', { name: /exportar reporte/i }));

    await waitFor(() => expect(exportReportMock).toHaveBeenCalledTimes(1));
    const params = exportReportMock.mock.calls[0][0];
    expect(params).toEqual({ days: 30 });
  });

  it('triggers a blob download (object URL + anchor click)', async () => {
    const user = userEvent.setup();
    renderReports();
    await waitFor(() => expect(salesApi.getReportSummary).toHaveBeenCalled());

    await user.click(screen.getByRole('button', { name: /exportar reporte/i }));
    await waitFor(() => expect(exportReportMock).toHaveBeenCalled());

    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
  });

  it('passes a custom start_date/end_date range to exportReport', async () => {
    const user = userEvent.setup();
    renderReports();
    await waitFor(() => expect(salesApi.getReportSummary).toHaveBeenCalled());

    // Select custom and fill a valid range.
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: /rango personalizado/i }));
    await user.type(screen.getByLabelText(/inicio/i), '2026-01-10');
    await user.type(screen.getByLabelText(/^fin$/i), '2026-01-20');

    await user.click(screen.getByRole('button', { name: /exportar reporte/i }));
    await waitFor(() => expect(exportReportMock).toHaveBeenCalled());
    expect(exportReportMock.mock.calls.at(-1)[0]).toEqual({
      start_date: '2026-01-10',
      end_date: '2026-01-20',
    });
  });
});
