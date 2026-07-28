import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { SettingsPage } from '@/pages/Settings/Settings';
import { settingsApi } from '@/api/settings';

// Auth state is mutable so the non-admin gating test can flip the role.
const { authState } = vi.hoisted(() => ({
    authState: { user: { role: 'admin' as string } },
}));

vi.mock('@/contexts/AuthContext', () => ({
    useAuth: () => authState,
}));

vi.mock('@/contexts/ThemeContext', () => ({
    useThemeMode: () => ({ mode: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@/components/UserManagement', () => ({
    UserManagement: () => <div data-testid="user-mgmt" />,
}));

const { exportDbMock } = vi.hoisted(() => ({ exportDbMock: vi.fn() }));
exportDbMock.mockResolvedValue(
    new Blob(['PGDMPmock'], { type: 'application/octet-stream' }),
);

vi.mock('@/api/settings', () => ({
    settingsApi: {
        getAll: vi.fn().mockResolvedValue([]),
        getPublic: vi.fn().mockResolvedValue({ timezone: 'America/Bogota' }),
        uploadLogo: vi.fn(),
        exportDatabase: exportDbMock,
        // The Export Database block now lives in the Backup tab alongside
        // SettingsBackupTab; provide no-op backup-config methods so mounting
        // the Backup tab does not crash this Export-DB-focused test.
        getBackupConfig: vi.fn().mockResolvedValue({
            type: 'none', host: '', port: null, share: '', path: '', username: '', has_password: false,
        }),
        putBackupConfig: vi.fn().mockResolvedValue({
            type: 'none', host: '', port: null, share: '', path: '', username: '', has_password: false,
        }),
        testBackupConfig: vi.fn().mockResolvedValue({ ok: false, message: '' }),
    },
}));

function renderSettings() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
        <QueryClientProvider client={qc}>
            <LanguageProvider>
                <SettingsPage />
            </LanguageProvider>
        </QueryClientProvider>,
    );
}

const BACKUP_TAB = /respaldo|backup/i;
const EXPORT_BTN = /exportar base de datos|export database/i;

describe('Settings — Export Database', () => {
    beforeEach(() => {
        authState.user = { role: 'admin' };
        exportDbMock.mockClear();
        URL.createObjectURL = vi.fn(() => 'blob:mock');
        URL.revokeObjectURL = vi.fn();
        HTMLAnchorElement.prototype.click = vi.fn();
    });

    it('admin: Export DB button calls settingsApi.exportDatabase and triggers a blob download', async () => {
        const user = userEvent.setup();
        renderSettings();

        // The Export Database block was moved into the Backup tab.
        await user.click(await screen.findByRole('tab', { name: BACKUP_TAB }));
        // RED target: the Export Database button must appear (admin-gated).
        await user.click(await screen.findByRole('button', { name: EXPORT_BTN }));

        await waitFor(() => expect(exportDbMock).toHaveBeenCalledTimes(1));
        expect(URL.createObjectURL).toHaveBeenCalled();
        expect(HTMLAnchorElement.prototype.click).toHaveBeenCalled();
    });

    it('non-admin: Export DB button is not rendered (server-side gate is authoritative)', async () => {
        authState.user = { role: 'staff' };
        renderSettings();

        // The Backup tab itself is admin-only, so it must not be rendered for
        // non-admins — which also means the Export DB button cannot appear.
        await waitFor(() =>
            expect(screen.queryByRole('tab', { name: BACKUP_TAB })).toBeNull(),
        );
        expect(screen.queryByRole('button', { name: EXPORT_BTN })).toBeNull();
        expect(exportDbMock).not.toHaveBeenCalled();
    });
});
