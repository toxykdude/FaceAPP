import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { MemberForm } from '@/pages/Members/MemberForm';

// vi.hoisted runs before vi.mock factories are evaluated, so the mock fn and
// the swappable auth user are defined in time for both the factory and the
// tests below.
const { membershipsMock } = vi.hoisted(() => ({ membershipsMock: vi.fn() }));
const { authState } = vi.hoisted(() => ({
  authState: { current: { id: 'u-admin', role: 'admin', username: 'admin' } as any },
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: 'member-1' }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: authState.current }),
}));

vi.mock('@/api/members', () => ({
  membersApi: {
    getMember: vi.fn().mockResolvedValue({
      id: 'member-1',
      first_name: 'Test',
      last_name: 'Member',
      email: '',
      phone: '',
      id_number: '',
      date_of_birth: '',
      address: '',
      consent_given: true,
      status: 'active',
    }),
    enrollBiometric: vi.fn(),
  },
}));

vi.mock('@/api/memberships', () => ({
  membershipsApi: { getMemberships: membershipsMock },
}));

vi.mock('@/api/membershipPlans', () => ({
  membershipPlansApi: { getPlans: vi.fn().mockResolvedValue({ plans: [] }) },
}));

vi.mock('@/api/sales', () => ({ salesApi: { createTransaction: vi.fn() } }));

// Build N memberships where Plan-0 has the latest end_date and Plan-(N-1) the
// earliest. Sorting by end_date DESC therefore keeps Plan-0 and Plan-1 on top,
// so the two visible rows are deterministic and the remainder land in the
// older-history accordion.
function makeMemberships(count: number) {
  const base = new Date('2026-12-15T12:00:00Z').getTime();
  return Array.from({ length: count }, (_, i) => ({
    id: `m-${i}`,
    member_id: 'member-1',
    plan_id: 'p-1',
    type: 'Monthly',
    start_date: '2026-01-01',
    end_date: new Date(base - i * 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
    price: 100,
    status: 'active' as const,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    plan_name: `Plan-${i}`,
  }));
}

function renderMemberForm() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <MemberForm />
      </LanguageProvider>
    </QueryClientProvider>,
  );
}

describe('Membership accordion', () => {
  beforeEach(() => {
    localStorage.setItem('lang', 'en');
    authState.current = { id: 'u-admin', role: 'admin', username: 'admin' };
  });

  it('shows no accordion when the member has exactly two memberships', async () => {
    membershipsMock.mockResolvedValue(makeMemberships(2));
    renderMemberForm();
    await waitFor(() => expect(screen.getByText('Plan-0')).toBeInTheDocument());
    expect(screen.getByText('Plan-1')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /older memberships/i })).not.toBeInTheDocument();
  });

  it('keeps the two most recent records visible and places the third in the accordion', async () => {
    membershipsMock.mockResolvedValue(makeMemberships(3));
    renderMemberForm();
    await waitFor(() => expect(screen.getByText('Plan-0')).toBeInTheDocument());
    expect(screen.getByText('Plan-1')).toBeInTheDocument();
    // The accordion summary must advertise exactly one hidden record.
    const summary = screen.getByRole('button', { name: /older memberships \(1\)/i });
    expect(summary).toBeInTheDocument();
    // The third record becomes consultable once the accordion is expanded.
    const user = userEvent.setup();
    await user.click(summary);
    await waitFor(() => expect(screen.getByText('Plan-2')).toBeInTheDocument());
  });

  it('collapses records three through fifty inside a single accordion', async () => {
    membershipsMock.mockResolvedValue(makeMemberships(50));
    renderMemberForm();
    await waitFor(() => expect(screen.getByText('Plan-0')).toBeInTheDocument());
    expect(screen.getByText('Plan-1')).toBeInTheDocument();
    const summary = screen.getByRole('button', { name: /older memberships \(48\)/i });
    expect(summary).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(summary);
    await waitFor(() => expect(screen.getByText('Plan-49')).toBeInTheDocument());
    // Every row keeps its Renew action (2 visible + 48 inside the accordion).
    expect(screen.getAllByRole('button', { name: /^renew$/i })).toHaveLength(50);
  });

  it('renders admin edit/delete actions inside the expanded accordion', async () => {
    membershipsMock.mockResolvedValue(makeMemberships(3));
    renderMemberForm();
    await waitFor(() => expect(screen.getByText('Plan-0')).toBeInTheDocument());
    const summary = screen.getByRole('button', { name: /older memberships \(1\)/i });
    const user = userEvent.setup();
    await user.click(summary);
    // Scope to the accordion region so we prove the action renders *inside* it.
    const accordion = summary.closest('.MuiAccordion-root') as HTMLElement;
    await waitFor(() =>
      expect(within(accordion).getByRole('button', { name: /^edit$/i })).toBeInTheDocument(),
    );
    expect(within(accordion).getByRole('button', { name: /^delete$/i })).toBeInTheDocument();
    expect(within(accordion).getByRole('button', { name: /^renew$/i })).toBeInTheDocument();
  });

  it('keeps admin-only actions unavailable for a non-admin viewer', async () => {
    authState.current = { id: 'u-staff', role: 'staff', username: 'staff' };
    membershipsMock.mockResolvedValue(makeMemberships(3));
    renderMemberForm();
    await waitFor(() => expect(screen.getByText('Plan-0')).toBeInTheDocument());
    // Edit and delete are admin-only; none render for staff, anywhere — even
    // before the accordion is expanded.
    expect(screen.queryAllByRole('button', { name: /^edit$/i })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: /^delete$/i })).toHaveLength(0);
    // Spec scenario: non-admin expands the older-history accordion. Renew
    // remains available to everyone on every row; admin-only actions stay gated.
    const summary = screen.getByRole('button', { name: /older memberships \(1\)/i });
    const user = userEvent.setup();
    await user.click(summary);
    await waitFor(() => expect(screen.getByText('Plan-2')).toBeInTheDocument());
    expect(screen.queryAllByRole('button', { name: /^edit$/i })).toHaveLength(0);
    expect(screen.queryAllByRole('button', { name: /^delete$/i })).toHaveLength(0);
    expect(screen.getAllByRole('button', { name: /^renew$/i })).toHaveLength(3);
  });
});
