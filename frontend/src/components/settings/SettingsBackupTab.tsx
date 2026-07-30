import React, { useEffect, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import {
    Paper,
    Box,
    Typography,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    TextField,
    Button,
    Alert,
    CircularProgress,
    Grid,
    Snackbar,
} from '@mui/material';
import {
    Save as SaveIcon,
    NetworkCheck as NetworkCheckIcon,
} from '@mui/icons-material';
import { settingsApi, BackupConfig, BackupConfigInput, BackupTestResult } from '@/api/settings';
import { useLanguage } from '@/i18n/LanguageContext';

const TRANSPORTS = ['none', 'rsync', 'sftp', 'ftp', 'smb', 'nfs'] as const;
type Transport = (typeof TRANSPORTS)[number];

/**
 * Fields surfaced in the UI per transport. Mirrors the backend contract:
 * none=∅, rsync=host,path, sftp=host,username,password,port(22),path,
 * ftp=host,username,password,port(21),path, smb=share,username,password,path,
 * nfs=path. Irrelevant fields are cleared on transport change.
 */
const VISIBLE: Record<Transport, {
    host?: boolean; path?: boolean; username?: boolean; password?: boolean; port?: boolean; share?: boolean;
}> = {
    none: {},
    rsync: { host: true, path: true },
    sftp: { host: true, path: true, username: true, password: true, port: true },
    ftp: { host: true, path: true, username: true, password: true, port: true },
    smb: { share: true, path: true, username: true, password: true },
    nfs: { path: true },
};

const DEFAULT_PORT: Partial<Record<Transport, number>> = { sftp: 22, ftp: 21 };

const emptyForm = (): BackupConfigInput => ({
    type: 'none',
    host: '',
    port: null,
    share: '',
    path: '',
    username: '',
    password: '',
});

/** Transports the backend probe can actually exercise (PROBEABLE_TYPES). */
const PROBEABLE: ReadonlySet<string> = new Set(['rsync', 'sftp', 'ftp', 'smb', 'nfs']);

/**
 * Project the masked server config onto the form shape. The password is always
 * blank: it is write-only, and "" is the keep-current sentinel.
 */
const formFromConfig = (cfg: BackupConfig): BackupConfigInput => ({
    type: cfg.type,
    host: cfg.host ?? '',
    port: cfg.port ?? null,
    share: cfg.share ?? '',
    path: cfg.path ?? '',
    username: cfg.username ?? '',
    password: '',
});

/**
 * True when the form no longer matches the last known saved config. A non-empty
 * password always counts as a change, since a typed secret is not yet stored.
 */
const isDirtyAgainst = (form: BackupConfigInput, saved: BackupConfigInput | null): boolean => {
    if (!saved) return false;
    return (
        form.type !== saved.type ||
        (form.host ?? '') !== (saved.host ?? '') ||
        (form.port ?? null) !== (saved.port ?? null) ||
        (form.share ?? '') !== (saved.share ?? '') ||
        (form.path ?? '') !== (saved.path ?? '') ||
        (form.username ?? '') !== (saved.username ?? '') ||
        !!form.password
    );
};

const detailOf = (err: any, fallback: string): string =>
    err?.response?.data?.detail || err?.message || fallback;

export const SettingsBackupTab: React.FC = () => {
    const { t } = useLanguage();
    const ts = t.settings;
    const [form, setForm] = useState<BackupConfigInput>(emptyForm());
    // Last config known to be persisted server-side. The probe targets THIS,
    // never the form, so it also drives whether Test is reachable.
    const [saved, setSaved] = useState<BackupConfigInput | null>(null);
    const [hasPassword, setHasPassword] = useState(false);
    const [testResult, setTestResult] = useState<BackupTestResult | null>(null);
    const [testError, setTestError] = useState<string | null>(null);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [savedMessage, setSavedMessage] = useState(false);

    const { data, isLoading } = useQuery({
        queryKey: ['backup-config'],
        queryFn: settingsApi.getBackupConfig,
    });

    /** Adopt a server response as both the form contents and the saved baseline. */
    const adoptConfig = (cfg: BackupConfig) => {
        setForm(formFromConfig(cfg));
        setSaved(formFromConfig(cfg));
        setHasPassword(!!cfg.has_password);
        setTestResult(null);
        setTestError(null);
        setSaveError(null);
    };

    useEffect(() => {
        if (data) {
            adoptConfig(data);
        }
    }, [data]);

    const saveMutation = useMutation({
        mutationFn: (payload: BackupConfigInput) => settingsApi.putBackupConfig(payload),
        // The response carries the backend's normalized values (e.g. an smb
        // share rewritten to //server/share, a defaulted port). Adopting it as
        // the new baseline is what keeps the form from reading as dirty forever.
        onSuccess: (cfg) => {
            adoptConfig(cfg);
            setSavedMessage(true);
        },
        onError: (err: any) => setSaveError(detailOf(err, ts.backupSaveError)),
    });

    const testMutation = useMutation({
        mutationFn: () => settingsApi.testBackupConfig(),
        onSuccess: (result) => {
            setTestResult(result);
            setTestError(null);
        },
        // A rejected probe (400 for an unprobeable or malformed stored config,
        // 500, network failure) must be visible; swallowing it made the button
        // look dead.
        onError: (err: any) => {
            setTestResult(null);
            setTestError(detailOf(err, ts.backupTestError));
        },
    });

    const onTransportChange = (next: Transport) => {
        const v = VISIBLE[next];
        setForm((f) => ({
            type: next,
            // Reset the port to the transport default and clear fields that are
            // no longer relevant so stale values are never persisted.
            port: v.port ? (DEFAULT_PORT[next] ?? f.port ?? null) : null,
            host: v.host ? f.host : '',
            path: v.path ? f.path : '',
            username: v.username ? f.username : '',
            share: v.share ? f.share : '',
            password: v.password ? f.password : '',
        }));
        setTestResult(null);
        setTestError(null);
    };

    const setField = (key: keyof BackupConfigInput, value: string | number | null) => {
        setForm((f) => ({ ...f, [key]: value }));
    };

    const transport = form.type as Transport;
    const visible = VISIBLE[transport];

    // Test probes the SAVED config, so it stays out of reach while the form has
    // unsaved edits or the stored transport has nothing to probe. The hint says
    // which of the two it is.
    const isDirty = isDirtyAgainst(form, saved);
    const savedIsProbeable = PROBEABLE.has(saved?.type ?? 'none');
    const testBlockedReason = !savedIsProbeable
        ? ts.backupTestNoTransport
        : isDirty
            ? ts.backupTestSaveFirst
            : null;

    if (isLoading) {
        return (
            <Paper sx={{ p: 3, mb: 3 }}>
                <CircularProgress size={24} />
            </Paper>
        );
    }

    return (
        <Paper sx={{ p: 3, mb: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <NetworkCheckIcon color="primary" />
                <Typography variant="h6">{ts.backupTitle}</Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {ts.backupRemoteStatus}
            </Typography>

            <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                    <FormControl fullWidth>
                        <InputLabel id="backup-transport-label">{ts.backupTransport}</InputLabel>
                        <Select
                            labelId="backup-transport-label"
                            label={ts.backupTransport}
                            value={transport}
                            onChange={(e) => onTransportChange(e.target.value as Transport)}
                        >
                            <MenuItem value="none">{ts.backupTransportNone}</MenuItem>
                            <MenuItem value="rsync">rsync</MenuItem>
                            <MenuItem value="sftp">sftp</MenuItem>
                            <MenuItem value="ftp">ftp</MenuItem>
                            <MenuItem value="smb">smb</MenuItem>
                            <MenuItem value="nfs">nfs</MenuItem>
                        </Select>
                    </FormControl>
                </Grid>

                {visible.host && (
                    <Grid item xs={12} md={6}>
                        <TextField
                            fullWidth
                            label={ts.backupHost}
                            value={form.host ?? ''}
                            onChange={(e) => setField('host', e.target.value)}
                        />
                    </Grid>
                )}

                {visible.share && (
                    <Grid item xs={12} md={6}>
                        <TextField
                            fullWidth
                            label={ts.backupShare}
                            value={form.share ?? ''}
                            onChange={(e) => setField('share', e.target.value)}
                        />
                    </Grid>
                )}

                {visible.username && (
                    <Grid item xs={12} md={6}>
                        <TextField
                            fullWidth
                            label={ts.backupUsername}
                            value={form.username ?? ''}
                            onChange={(e) => setField('username', e.target.value)}
                        />
                    </Grid>
                )}

                {visible.password && (
                    <Grid item xs={12} md={6}>
                        <TextField
                            fullWidth
                            type="password"
                            label={ts.backupPassword}
                            value={form.password ?? ''}
                            placeholder={hasPassword ? ts.backupPasswordKeep : ''}
                            onChange={(e) => setField('password', e.target.value)}
                            helperText={hasPassword ? ts.backupPasswordKeep : ''}
                        />
                    </Grid>
                )}

                {visible.port && (
                    <Grid item xs={12} md={6}>
                        <TextField
                            fullWidth
                            type="number"
                            label={ts.backupPort}
                            value={form.port ?? ''}
                            onChange={(e) => setField('port', e.target.value === '' ? null : Number(e.target.value))}
                        />
                    </Grid>
                )}

                {visible.path && (
                    <Grid item xs={12} md={6}>
                        <TextField
                            fullWidth
                            label={ts.backupPath}
                            value={form.path ?? ''}
                            onChange={(e) => setField('path', e.target.value)}
                        />
                    </Grid>
                )}
            </Grid>

            {transport === 'ftp' && (
                <Alert severity="warning" sx={{ mt: 2 }}>
                    {ts.backupFtpWarning}
                </Alert>
            )}

            {hasPassword && visible.password && (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                    {ts.backupHasPassword}
                </Typography>
            )}

            <Box sx={{ display: 'flex', gap: 2, mt: 3, flexWrap: 'wrap' }}>
                <Button
                    variant="contained"
                    color="primary"
                    startIcon={<SaveIcon />}
                    disabled={saveMutation.isPending}
                    onClick={() => saveMutation.mutate(form)}
                >
                    {saveMutation.isPending ? ts.saving : ts.backupSave}
                </Button>
                <Button
                    variant="outlined"
                    startIcon={<NetworkCheckIcon />}
                    disabled={testMutation.isPending || testBlockedReason !== null}
                    onClick={() => testMutation.mutate()}
                >
                    {testMutation.isPending ? ts.backupTesting : ts.backupTest}
                </Button>
            </Box>

            {testBlockedReason && (
                <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: 'block', mt: 1 }}
                    data-testid="backup-test-blocked"
                >
                    {testBlockedReason}
                </Typography>
            )}

            {saveError && (
                <Alert severity="error" sx={{ mt: 2 }} data-testid="backup-save-error">
                    {ts.backupSaveError}: {saveError}
                </Alert>
            )}

            {testError && (
                <Alert severity="error" sx={{ mt: 2 }} data-testid="backup-test-error">
                    {ts.backupTestError}: {testError}
                </Alert>
            )}

            {testResult && (
                <Alert severity={testResult.ok ? 'success' : 'error'} sx={{ mt: 2 }} data-testid="backup-test-result">
                    {testResult.ok ? ts.backupTestOk : ts.backupTestFail}: {testResult.message}
                </Alert>
            )}

            <Snackbar
                open={savedMessage}
                autoHideDuration={3000}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
                onClose={() => setSavedMessage(false)}
            >
                <Alert severity="success" onClose={() => setSavedMessage(false)}>
                    {ts.backupSaved}
                </Alert>
            </Snackbar>
        </Paper>
    );
};
