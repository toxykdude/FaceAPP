import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { MemberForm } from '@/pages/Members/MemberForm';

// The member the form loads. Tests mutate this before rendering so one mock
// serves both the "enrolled" and "never enrolled" cases.
const { memberState, updateMemberMock } = vi.hoisted(() => ({
  memberState: {
    current: {
      id: 'member-1',
      first_name: 'Test',
      last_name: 'Member',
      email: '',
      phone: '',
      id_number: '',
      date_of_birth: '',
      address: '',
      consent_given: true,
      facial_data_enrolled: true,
      status: 'active',
    } as any,
  },
  updateMemberMock: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: 'member-1' }),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u-admin', role: 'admin', username: 'admin' } }),
}));

vi.mock('@/api/members', () => ({
  membersApi: {
    getMember: vi.fn(() => Promise.resolve(memberState.current)),
    updateMember: updateMemberMock,
    enrollBiometric: vi.fn(),
    getBiometricStatus: vi.fn().mockResolvedValue({ enrolled: true, template_count: 1 }),
  },
}));

vi.mock('@/api/memberships', () => ({
  membershipsApi: { getMemberships: vi.fn().mockResolvedValue([]) },
}));

vi.mock('@/api/membershipPlans', () => ({
  membershipPlansApi: { getPlans: vi.fn().mockResolvedValue({ plans: [] }) },
}));

vi.mock('@/api/sales', () => ({
  salesApi: { createTransaction: vi.fn() },
}));

const renderForm = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <MemberForm />
      </LanguageProvider>
    </QueryClientProvider>,
  );
};

const consentCheckbox = () => screen.getByRole('checkbox');
const submit = () => screen.getByRole('button', { name: /actualizar|update/i });

describe('MemberForm biometric consent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMemberMock.mockResolvedValue({});
    memberState.current = { ...memberState.current, consent_given: true, facial_data_enrolled: true };
  });

  it('renders the checkbox from the server consent_given flag', async () => {
    renderForm();
    await waitFor(() => expect(consentCheckbox()).toBeChecked());
  });

  it('sends consent_given when granting consent to an existing member', async () => {
    memberState.current = { ...memberState.current, consent_given: false, facial_data_enrolled: false };
    const user = userEvent.setup();
    renderForm();

    await waitFor(() => expect(consentCheckbox()).not.toBeChecked());
    await user.click(consentCheckbox());
    await user.click(submit());

    await waitFor(() =>
      expect(updateMemberMock).toHaveBeenCalledWith(
        'member-1',
        expect.objectContaining({ consent_given: true }),
      ),
    );
  });

  it('asks for confirmation before revoking consent on an enrolled member', async () => {
    const user = userEvent.setup();
    renderForm();

    await waitFor(() => expect(consentCheckbox()).toBeChecked());
    await user.click(consentCheckbox());
    await user.click(submit());

    // Destructive: the update must NOT fire until the admin confirms.
    expect(updateMemberMock).not.toHaveBeenCalled();
    const confirm = await screen.findByTestId('confirm-revoke-consent');

    await user.click(confirm);
    await waitFor(() =>
      expect(updateMemberMock).toHaveBeenCalledWith(
        'member-1',
        expect.objectContaining({ consent_given: false }),
      ),
    );
  });

  it('cancelling the confirmation leaves the enrollment alone', async () => {
    const user = userEvent.setup();
    renderForm();

    await waitFor(() => expect(consentCheckbox()).toBeChecked());
    await user.click(consentCheckbox());
    await user.click(submit());

    await user.click(await screen.findByRole('button', { name: /cancelar|cancel/i }));

    await waitFor(() => expect(screen.queryByTestId('confirm-revoke-consent')).toBeNull());
    expect(updateMemberMock).not.toHaveBeenCalled();
  });

  it('revoking for a never-enrolled member needs no confirmation', async () => {
    memberState.current = { ...memberState.current, consent_given: true, facial_data_enrolled: false };
    const user = userEvent.setup();
    renderForm();

    await waitFor(() => expect(consentCheckbox()).toBeChecked());
    await user.click(consentCheckbox());
    await user.click(submit());

    await waitFor(() =>
      expect(updateMemberMock).toHaveBeenCalledWith(
        'member-1',
        expect.objectContaining({ consent_given: false }),
      ),
    );
    expect(screen.queryByTestId('confirm-revoke-consent')).toBeNull();
  });
});
