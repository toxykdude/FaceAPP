import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { Reports } from '@/pages/Reports/Reports';
import { salesApi } from '@/api/sales';

vi.mock('react-chartjs-2', () => ({ Line: () => null, Bar: () => null, Doughnut: () => null }));

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
    </QueryClientProvider>
  );
}

describe('Reports custom range wiring', () => {
  it('reveals pickers, blocks the reversed custom range, then clears/fetches once valid', async () => {
    const user = userEvent.setup();
    renderReports();
    await waitFor(() => expect(salesApi.getReportSummary).toHaveBeenCalledTimes(1));

    // Select the "custom" preset -> both date pickers appear.
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByRole('option', { name: /rango personalizado/i }));
    const start = screen.getByLabelText(/inicio/i);
    const end = screen.getByLabelText(/^fin$/i);
    expect(start).toBeInTheDocument();
    expect(end).toBeInTheDocument();

    // Reversed range: inline error shown, summary NOT refetched.
    const callsBeforeTyping = vi.mocked(salesApi.getReportSummary).mock.calls.length;
    await user.type(start, '2026-01-20');
    await user.type(end, '2026-01-10');
    expect(await screen.findByText(/el inicio no puede ser posterior al fin/i)).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(vi.mocked(salesApi.getReportSummary).mock.calls.length).toBe(callsBeforeTyping);

    // Fix the range: error clears, summary fetched with the correct window.
    await user.clear(end);
    await user.type(end, '2026-02-20');
    await waitFor(() =>
      expect(vi.mocked(salesApi.getReportSummary).mock.calls.length).toBeGreaterThan(callsBeforeTyping)
    );
    const lastCall = vi.mocked(salesApi.getReportSummary).mock.calls.slice(-1)[0][0];
    expect(lastCall).toEqual({ start_date: '2026-01-20', end_date: '2026-02-20' });
    expect(screen.queryByText(/el inicio no puede ser posterior al fin/i)).not.toBeInTheDocument();
  });
});
