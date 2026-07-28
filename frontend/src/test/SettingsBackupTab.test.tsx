import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { SettingsPage } from '@/pages/Settings/Settings';

// Auth state is mutable so the non-admin gating test can flip the role.
const { authState, mocks } = vi.hoisted(() => ({
    authState: { user: { role: 'admin' as string | null } },
    mocks: {
        getConfig: vi.fn(),
        putConfig: vi.fn(),
        testConfig: vi.fn(),
        exportDb: vi.fn(),
    },
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

const NONE_CONFIG = {
    type: 'none', host: '', port: null, share: '', path: '', username: '', has_password: false,
};

mocks.getConfig.mockResolvedValue(NONE_CONFIG);
mocks.putConfig.mockResolvedValue(NONE_CONFIG);
mocks.testConfig.mockResolvedValue({ ok: false, message: '' });
mocks.exportDb.mockResolvedValue(new Blob(['x'], { type: 'application/octet-stream' }));

vi.mock('@/api/settings', () => ({
    settingsApi: {
        getAll: vi.fn().mockResolvedValue([]),
        getPublic: vi.fn().mockResolvedValue({ timezone: 'America/Bogota' }),
        uploadLogo: vi.fn(),
        exportDatabase: mocks.exportDb,
        getBackupConfig: mocks.getConfig,
        putBackupConfig: mocks.putConfig,
        testBackupConfig: mocks.testConfig,
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
const TRANSPORT = /transporte|transport/i;
const HOST = /^host$/i;
const PATH = /ruta|path/i;
const USERNAME = /usuario|username/i;
const PASSWORD = /contraseña|password/i;
const PORT = /puerto|port/i;
const SHARE = /recurso compartido|share/i;
const FTP_WARN = /texto plano|cleartext/i;
const KEEP = /mantener la actual|keep current/i;
const SAVE_BTN = /guardar respaldo|save backup/i;
const TEST_BTN = /probar conexi(?:ó|o)n|test connection/i;

async function openBackupTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole('tab', { name: BACKUP_TAB }));
}

async function selectTransport(user: ReturnType<typeof userEvent.setup>, value: string) {
    await user.click(screen.getByRole('combobox', { name: TRANSPORT }));
    const listbox = await screen.findByRole('listbox');
    const optName = value === 'none' ? /ninguno|none/i : new RegExp(`^${value}$`, 'i');
    await user.click(within(listbox).getByRole('option', { name: optName }));
}

describe('Settings — Backup tab (remote backup config)', () => {
    beforeEach(() => {
        authState.user = { role: 'admin' };
        mocks.getConfig.mockResolvedValue(NONE_CONFIG);
        mocks.putConfig.mockResolvedValue(NONE_CONFIG);
        mocks.testConfig.mockResolvedValue({ ok: false, message: '' });
        mocks.getConfig.mockClear();
        mocks.putConfig.mockClear();
        mocks.testConfig.mockClear();
    });

    it('admin: transport Select renders the 6 options none/rsync/sftp/ftp/smb/nfs', async () => {
        const user = userEvent.setup();
        renderSettings();
        await openBackupTab(user);

        await user.click(await screen.findByRole('combobox', { name: TRANSPORT }));
        const listbox = await screen.findByRole('listbox');
        const options = within(listbox).getAllByRole('option');
        expect(options).toHaveLength(6);
        expect(options.map((o) => o.getAttribute('data-value'))).toEqual([
            'none', 'rsync', 'sftp', 'ftp', 'smb', 'nfs',
        ]);
    });

    it('admin: conditional fields appear/clear per transport', async () => {
        const user = userEvent.setup();
        renderSettings();
        await openBackupTab(user);

        // none: no transport-specific fields
        await screen.findByRole('combobox', { name: TRANSPORT });
        expect(screen.queryByRole('textbox', { name: HOST })).toBeNull();
        expect(screen.queryByRole('spinbutton', { name: PORT })).toBeNull();
        // type="password" inputs expose no implicit role in this jsdom build,
        // so the password field is matched by its label instead.
        expect(screen.queryByLabelText(PASSWORD)).toBeNull();
        expect(screen.queryByText(KEEP)).toBeNull();

        // rsync: host + path only
        await selectTransport(user, 'rsync');
        expect(await screen.findByRole('textbox', { name: HOST })).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: PATH })).toBeInTheDocument();
        expect(screen.queryByRole('textbox', { name: USERNAME })).toBeNull();
        expect(screen.queryByRole('spinbutton', { name: PORT })).toBeNull();

        // sftp: host + username + password + port(22)
        await selectTransport(user, 'sftp');
        expect(await screen.findByRole('textbox', { name: HOST })).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: USERNAME })).toBeInTheDocument();
        expect(screen.getByLabelText(PASSWORD)).toBeInTheDocument();
        expect(screen.getByRole('spinbutton', { name: PORT })).toBeInTheDocument();
        expect((screen.getByRole('spinbutton', { name: PORT }) as HTMLInputElement).value).toBe('22');

        // smb: share + username + password (no port)
        await selectTransport(user, 'smb');
        expect(await screen.findByRole('textbox', { name: SHARE })).toBeInTheDocument();
        expect(screen.getByRole('textbox', { name: USERNAME })).toBeInTheDocument();
        expect(screen.getByLabelText(PASSWORD)).toBeInTheDocument();
        expect(screen.queryByRole('spinbutton', { name: PORT })).toBeNull();

        // nfs: path only
        await selectTransport(user, 'nfs');
        expect(await screen.findByRole('textbox', { name: PATH })).toBeInTheDocument();
        expect(screen.queryByRole('textbox', { name: HOST })).toBeNull();
    });

    it('admin: FTP cleartext warning is shown only when ftp is selected', async () => {
        const user = userEvent.setup();
        renderSettings();
        await openBackupTab(user);

        await selectTransport(user, 'sftp');
        expect(screen.queryByText(FTP_WARN)).toBeNull();

        await selectTransport(user, 'ftp');
        expect(await screen.findByText(FTP_WARN)).toBeInTheDocument();

        await selectTransport(user, 'smb');
        expect(screen.queryByText(FTP_WARN)).toBeNull();
    });

    it('admin: keep-current helper appears on the password field only when has_password is true', async () => {
        mocks.getConfig.mockResolvedValue({
            type: 'sftp', host: 'h.example', port: 22, share: '', path: '/b', username: 'u', has_password: true,
        });
        const user = userEvent.setup();
        renderSettings();
        await openBackupTab(user);

        expect(await screen.findByText(KEEP)).toBeInTheDocument();
    });

    it('non-admin: Backup tab is not rendered (server-side 403 gate is authoritative)', async () => {
        authState.user = { role: 'staff' };
        const user = userEvent.setup();
        renderSettings();

        await waitFor(() => {
            expect(screen.queryByRole('tab', { name: BACKUP_TAB })).toBeNull();
        });
        expect(mocks.getConfig).not.toHaveBeenCalled();
    });

    it('admin: Save sends putBackupConfig with an empty password (keep-current sentinel) when untouched', async () => {
        mocks.getConfig.mockResolvedValue({
            type: 'sftp', host: 'h.example', port: 22, share: '', path: '/back', username: 'u', has_password: true,
        });
        const user = userEvent.setup();
        renderSettings();
        await openBackupTab(user);

        await user.click(await screen.findByRole('button', { name: SAVE_BTN }));

        await waitFor(() => expect(mocks.putConfig).toHaveBeenCalledTimes(1));
        const payload = mocks.putConfig.mock.calls[0][0] as Record<string, unknown>;
        expect(payload.type).toBe('sftp');
        expect(payload.host).toBe('h.example');
        // Untouched password MUST be the keep-current sentinel (omitted OR "").
        expect(payload.password === undefined || payload.password === '').toBe(true);
    });

    it('admin: Test button calls testBackupConfig and renders the sanitized {ok,message} result', async () => {
        mocks.testConfig.mockResolvedValueOnce({ ok: false, message: 'connection refused' });
        const user = userEvent.setup();
        renderSettings();
        await openBackupTab(user);

        await user.click(await screen.findByRole('button', { name: TEST_BTN }));

        await waitFor(() => expect(mocks.testConfig).toHaveBeenCalledTimes(1));
        expect(await screen.findByText(/connection refused/i)).toBeInTheDocument();
    });
});
