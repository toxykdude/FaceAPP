import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Paper,
    Tabs,
    Tab,
    TextField,
    Button,
    Grid,
    Switch,
    FormControlLabel,
    Slider,
    CircularProgress,
    Avatar,
    Alert,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    useMediaQuery,
    useTheme,
} from '@mui/material';
import {
    Save as SaveIcon,
    Security as SecurityIcon,
    Business as BusinessIcon,
    CardMembership as MembershipIcon,
    Storage as StorageIcon,
    People as PeopleIcon,
    Image as ImageIcon,
    Download as DownloadIcon,
} from '@mui/icons-material';
import { settingsApi } from '@/api/settings';
import { UserManagement } from '@/components/UserManagement';
import { useLanguage } from '@/i18n/LanguageContext';
import { useThemeMode } from '@/contexts/ThemeContext';
import { useAuth } from '@/contexts/AuthContext';

interface SettingsProps { }

const DEFAULT_SETTINGS = [
    { key: 'business_name', value: 'PowerHouse Gym', category: 'general', description: 'Name of the business' },
    { key: 'business_address', value: '', category: 'general', description: 'Physical address' },
    { key: 'contact_email', value: '', category: 'general', description: 'Contact email' },
    { key: 'min_confidence', value: 0.75, category: 'access', description: 'Minimum face recognition confidence (0.0 - 1.0)' },
    { key: 'door_open_duration', value: 5, category: 'access', description: 'Seconds to keep door open' },
    { key: 'passback_cooldown', value: 60, category: 'access', description: 'Anti-passback cooldown in seconds' },
    { key: 'deny_unknown', value: true, category: 'access', description: 'Deny access to unknown faces automatically' },
    { key: 'currency', value: 'USD', category: 'membership', description: 'Currency symbol or code' },
    { key: 'payment_grace_period', value: 3, category: 'membership', description: 'Days before suspending overdue members' },
    { key: 'data_retention_days', value: 90, category: 'system', description: 'Days to keep access logs' },
    { key: 'timezone', value: 'America/Bogota', category: 'system', description: 'System timezone (affects reports and schedules)' },
    { key: 'debug_mode', value: false, category: 'system', description: 'Enable debug logging' },
];

export const SettingsPage: React.FC<SettingsProps> = () => {
    const queryClient = useQueryClient();
    const { lang, setLang, t } = useLanguage();
    const { mode, toggleTheme } = useThemeMode();
    const { user } = useAuth();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const [activeTab, setActiveTab] = useState(0);
    const [localValues, setLocalValues] = useState<Record<string, any>>({});
    const [hasChanges, setHasChanges] = useState(false);
    const [uploadingLogo, setUploadingLogo] = useState(false);
    const [logoMessage, setLogoMessage] = useState('');
    const [exportingDb, setExportingDb] = useState(false);

    const { data: serverSettings, isLoading } = useQuery({
        queryKey: ['settings'],
        queryFn: settingsApi.getAll,
    });

    const mergedSettings = React.useMemo(() => {
        const merged = [...DEFAULT_SETTINGS];
        if (serverSettings) {
            serverSettings.forEach(s => {
                const index = merged.findIndex(d => d.key === s.key);
                if (index >= 0) { merged[index] = { ...merged[index], ...s }; }
                else { merged.push(s as any); }
            });
        }
        return merged;
    }, [serverSettings]);

    useEffect(() => {
        const values: Record<string, any> = {};
        mergedSettings.forEach(s => { values[s.key] = s.value; });
        setLocalValues(values);
        setHasChanges(false);
    }, [mergedSettings]);

    const saveMutation = useMutation({
        mutationFn: async (values: Record<string, any>) => {
            const updates = Object.entries(values).map(([key, value]) => {
                const def = DEFAULT_SETTINGS.find(d => d.key === key);
                return { key, value, category: def?.category || 'general', description: def?.description };
            });
            await settingsApi.bulkUpdate(updates);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['settings'] });
            queryClient.invalidateQueries({ queryKey: ['public-settings'] });
            setHasChanges(false);
            alert(t.settings.saved);
        },
        onError: (err) => {
            alert(t.settings.saveFailed.replace('{error}', String(err)));
        }
    });

    const handleChange = (key: string, value: any) => {
        setLocalValues(prev => ({ ...prev, [key]: value }));
        setHasChanges(true);
    };

    const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setUploadingLogo(true);
        setLogoMessage('');
        try {
            const result = await settingsApi.uploadLogo(file);
            setLocalValues(prev => ({ ...prev, business_logo: result.url }));
            setLogoMessage('Logo uploaded successfully');
            queryClient.invalidateQueries({ queryKey: ['settings'] });
            queryClient.invalidateQueries({ queryKey: ['public-settings'] });
            setTimeout(() => setLogoMessage(''), 3000);
        } catch (error: any) {
            setLogoMessage('Error uploading logo: ' + (error?.response?.data?.detail || error.message));
            setTimeout(() => setLogoMessage(''), 5000);
        } finally {
            setUploadingLogo(false);
        }
    };

    // Export a fresh database dump (admin-only). The server enforces
    // require_admin independently; this UI is convenience, not a security gate.
    const handleExportDb = async () => {
        setExportingDb(true);
        try {
            const blob = await settingsApi.exportDatabase();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `powerhouse_db_${Math.floor(Date.now() / 1000)}.dump`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (error: any) {
            alert(error?.response?.data?.detail || error?.message || 'Export failed');
        } finally {
            setExportingDb(false);
        }
    };

    const renderField = (setting: any) => {
        const value = localValues[setting.key] ?? setting.value;
        if (typeof setting.value === 'boolean') {
            return (
                <FormControlLabel
                    control={<Switch checked={!!value} onChange={(e) => handleChange(setting.key, e.target.checked)} />}
                    label={setting.key.replace(/_/g, ' ').toUpperCase()}
                />
            );
        }
        if (setting.key === 'min_confidence') {
            return (
                <Box>
                    <Typography gutterBottom>Minimum Confidence: {(value * 100).toFixed(0)}%</Typography>
                    <Slider value={value} min={0.5} max={1.0} step={0.01} onChange={(_, val) => handleChange(setting.key, val)} valueLabelDisplay="auto" />
                </Box>
            );
        }
        if (setting.key === 'timezone') {
            const tzOptions = [
                { value: 'America/Bogota', label: 'Colombia (UTC-5)' },
                { value: 'America/New_York', label: 'Eastern (UTC-5/-4)' },
                { value: 'America/Chicago', label: 'Central (UTC-6/-5)' },
                { value: 'America/Denver', label: 'Mountain (UTC-7/-6)' },
                { value: 'America/Los_Angeles', label: 'Pacific (UTC-8/-7)' },
                { value: 'America/Mexico_City', label: 'Mexico (UTC-6)' },
                { value: 'America/Lima', label: 'Peru (UTC-5)' },
                { value: 'America/Santiago', label: 'Chile (UTC-4/-3)' },
                { value: 'America/Buenos_Aires', label: 'Argentina (UTC-3)' },
                { value: 'Europe/Madrid', label: 'España (UTC+1/+2)' },
                { value: 'UTC', label: 'UTC' },
            ];
            return (
                <FormControl fullWidth>
                    <InputLabel>{setting.key.replace(/_/g, ' ')}</InputLabel>
                    <Select value={value || 'America/Bogota'} label={setting.key.replace(/_/g, ' ')} onChange={(e) => handleChange(setting.key, e.target.value)}>
                        {tzOptions.map((tz) => (
                            <MenuItem key={tz.value} value={tz.value}>{tz.label}</MenuItem>
                        ))}
                    </Select>
                </FormControl>
            );
        }
        return (
            <TextField
                fullWidth
                label={setting.key.replace(/_/g, ' ')}
                value={value}
                onChange={(e) => handleChange(setting.key, e.target.value)}
                helperText={setting.description}
                type={typeof setting.value === 'number' ? 'number' : 'text'}
            />
        );
    };

    const renderCategory = (category: string) => {
        const categorySettings = mergedSettings.filter(s => s.category === category);
        return (
            <Grid container spacing={3}>
                {categorySettings.map(s => (
                    <Grid item xs={12} md={6} key={s.key}>
                        {renderField(s)}
                    </Grid>
                ))}
            </Grid>
        );
    };

    if (isLoading) return <CircularProgress />;

    return (
        <Box sx={{ maxWidth: 1200, mx: 'auto', p: { xs: 2, sm: 4 } }}>
            <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, justifyContent: 'space-between', mb: 4, gap: 2 }}>
                <Typography variant={isMobile ? "h5" : "h4"} fontWeight="bold">{t.settings.title}</Typography>
                <Button
                    variant="contained"
                    startIcon={<SaveIcon />}
                    disabled={!hasChanges || saveMutation.isPending}
                    onClick={() => saveMutation.mutate(localValues)}
                >
                    {saveMutation.isPending ? t.settings.saving : t.settings.saveChanges}
                </Button>
            </Box>

            <Paper sx={{ width: '100%', mb: 2 }}>
                <Tabs
                    value={activeTab}
                    variant="scrollable"
                    scrollButtons="auto"
                    onChange={(_, val) => setActiveTab(val)}
                    indicatorColor="primary"
                    textColor="primary"
                    sx={{ borderBottom: 1, borderColor: 'divider' }}
                >
                    <Tab icon={<BusinessIcon />} label={t.settings.general} />
                    <Tab icon={<SecurityIcon />} label={t.settings.accessControl} />
                    <Tab icon={<MembershipIcon />} label={t.settings.membership} />
                    <Tab icon={<StorageIcon />} label={t.settings.system} />
                    <Tab icon={<PeopleIcon />} label={t.settings.users} />
                </Tabs>

                <Box sx={{ p: { xs: 2, sm: 4 } }}>
                    {activeTab === 0 && (
                        <Box>
                            {/* Branding Section */}
                            <Paper sx={{ p: 3, mb: 3 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                                    <ImageIcon color="primary" />
                                    <Typography variant="h6">Branding</Typography>
                                </Box>
                                <Grid container spacing={3}>
                                    <Grid item xs={12} md={6}>
                                        <TextField
                                            fullWidth
                                            label="Organization Name"
                                            value={localValues['business_name'] || ''}
                                            onChange={(e) => handleChange('business_name', e.target.value)}
                                            helperText="This name appears in the sidebar, login page, and reports"
                                        />
                                    </Grid>
                                    <Grid item xs={12} md={6}>
                                        <Box display="flex" alignItems="center" gap={2}>
                                            <Avatar
                                                src={localValues['business_logo'] || '/logo.png'}
                                                sx={{ width: 64, height: 64, borderRadius: 2 }}
                                                variant="rounded"
                                            >
                                                Logo
                                            </Avatar>
                                            <Box>
                                                <input
                                                    type="file"
                                                    accept="image/*"
                                                    style={{ display: 'none' }}
                                                    id="logo-upload"
                                                    onChange={handleLogoUpload}
                                                />
                                                <label htmlFor="logo-upload">
                                                    <Button variant="outlined" component="span">
                                                        Upload Logo
                                                    </Button>
                                                </label>
                                                {uploadingLogo && <CircularProgress size={20} sx={{ ml: 1, mt: 1 }} />}
                                            </Box>
                                        </Box>
                                        {logoMessage && (
                                            <Alert severity={logoMessage.startsWith('Error') ? 'error' : 'success'} sx={{ mt: 1 }}>
                                                {logoMessage}
                                            </Alert>
                                        )}
                                    </Grid>
                                </Grid>
                            </Paper>

                            {/* Language Section */}
                            <Paper sx={{ p: 3, mb: 3 }}>
                                <Typography variant="h6">{t.settings.language}</Typography>
                                <Box display="flex" gap={2} mt={2}>
                                    <Button
                                        variant={lang === 'es' ? 'contained' : 'outlined'}
                                        onClick={() => setLang('es')}
                                    >
                                        🇪🇸 {t.settings.spanish}
                                    </Button>
                                    <Button
                                        variant={lang === 'en' ? 'contained' : 'outlined'}
                                        onClick={() => setLang('en')}
                                    >
                                        🇺🇸 {t.settings.english}
                                    </Button>
                                </Box>
                            </Paper>

                            {/* Theme Section */}
                            <Paper sx={{ p: 3, mb: 3 }}>
                                <Typography variant="h6">{t.settings.theme}</Typography>
                                <Box display="flex" alignItems="center" gap={2} mt={2}>
                                    <Typography>{mode === 'dark' ? t.settings.darkMode : t.settings.lightMode}</Typography>
                                    <Switch checked={mode === 'dark'} onChange={toggleTheme} />
                                </Box>
                            </Paper>

                            {renderCategory('general')}
                        </Box>
                    )}
                    {activeTab === 1 && renderCategory('access')}
                    {activeTab === 2 && renderCategory('membership')}
                    {activeTab === 3 && (
                        <Box>
                            {user?.role === 'admin' && (
                                <Paper sx={{ p: 3, mb: 3 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                                        <StorageIcon color="primary" />
                                        <Typography variant="h6">{t.settings.exportDb}</Typography>
                                    </Box>
                                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                                        {t.settings.exportDbHelp}
                                    </Typography>
                                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
                                        {t.settings.backupRemoteStatus}: systemd timer (30 min)
                                    </Typography>
                                    <Button
                                        variant="outlined"
                                        startIcon={<DownloadIcon />}
                                        disabled={exportingDb}
                                        onClick={handleExportDb}
                                    >
                                        {t.settings.exportDb}
                                    </Button>
                                </Paper>
                            )}
                            {renderCategory('system')}
                        </Box>
                    )}
                    {activeTab === 4 && <UserManagement />}
                </Box>
            </Paper>
        </Box>
    );
};
