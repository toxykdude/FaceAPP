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
import { settingsApi, BackupConfigInput, BackupTestResult } from '@/api/settings';
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

export const SettingsBackupTab: React.FC = () => {
    const { t } = useLanguage();
    const [form, setForm] = useState<BackupConfigInput>(emptyForm());
    const [hasPassword, setHasPassword] = useState(false);
    const [testResult, setTestResult] = useState<BackupTestResult | null>(null);
    const [savedMessage, setSavedMessage] = useState(false);

    const { data, isLoading } = useQuery({
        queryKey: ['backup-config'],
        queryFn: settingsApi.getBackupConfig,
    });

    useEffect(() => {
        if (data) {
            setForm({
                type: data.type,
                host: data.host ?? '',
                port: data.port ?? null,
                share: data.share ?? '',
                path: data.path ?? '',
                username: data.username ?? '',
                // Write-only: never prefill the password. The keep-current
                // sentinel ("") preserves the stored secret on save.
                password: '',
            });
            setHasPassword(!!data.has_password);
            setTestResult(null);
        }
    }, [data]);

    const saveMutation = useMutation({
        mutationFn: (payload: BackupConfigInput) => settingsApi.putBackupConfig(payload),
        onSuccess: (cfg) => {
            setHasPassword(!!cfg.has_password);
            setForm((f) => ({ ...f, password: '' }));
            setSavedMessage(true);
        },
    });

    const testMutation = useMutation({
        mutationFn: () => settingsApi.testBackupConfig(),
        onSuccess: (result) => setTestResult(result),
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
    };

    const setField = (key: keyof BackupConfigInput, value: string | number | null) => {
        setForm((f) => ({ ...f, [key]: value }));
    };

    const transport = form.type as Transport;
    const visible = VISIBLE[transport];
    const ts = t.settings;

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
                    disabled={testMutation.isPending}
                    onClick={() => testMutation.mutate()}
                >
                    {testMutation.isPending ? ts.backupTesting : ts.backupTest}
                </Button>
            </Box>

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
