import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { SalesList } from '@/pages/Sales/SalesList';

// Public settings drive the configured timezone the list must render in.
vi.mock('@/api/sales', () => ({
  salesApi: {
    getTransactions: vi.fn().mockResolvedValue({
      total: 1,
      transactions: [
        {
          id: 'tx-1',
          member_id: 'm-1',
          amount: 100,
          payment_method: 'cash',
          invoice_number: 'INV-1',
          notes: '',
          // 2026-01-15T12:00:00Z == 09:00 Santiago (DST, UTC-3).
          transaction_date: '2026-01-15T12:00:00Z',
          created_at: '2026-01-15T12:00:00Z',
          member_name: 'Csv Tester',
          member_id_number: '123',
        },
      ],
    }),
    createTransaction: vi.fn(),
  },
}));

vi.mock('@/api/settings', () => ({
  settingsApi: {
    getPublic: vi.fn().mockResolvedValue({
      business_name: 'Gym',
      timezone: 'America/Santiago',
    }),
  },
}));

function renderSalesList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <SalesList />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe('SalesList configured-timezone rendering', () => {
  it('renders transaction_date as date+time in the configured zone', async () => {
    renderSalesList();
    await waitFor(() =>
      expect(screen.getByText('Csv Tester')).toBeInTheDocument(),
    );

    // The cell must show the Santiago-local time (09:00), proving the configured
    // zone is applied AND the time component is shown (legacy only rendered a
    // browser-local date with no time).
    const cell = screen.getByText(/09:00/);
    expect(cell).toBeInTheDocument();
    expect(cell.textContent).toContain('2026');
  });
});
