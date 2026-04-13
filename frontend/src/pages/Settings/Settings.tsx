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
    CircularProgress
} from '@mui/material';
import {
    Save as SaveIcon,
    Security as SecurityIcon,
    Business as BusinessIcon,
    CardMembership as MembershipIcon,
    Storage as StorageIcon,
    People as PeopleIcon
} from '@mui/icons-material';
import { settingsApi } from '@/api/settings';
import { UserManagement } from '@/components/UserManagement';

interface SettingsProps { }

const DEFAULT_SETTINGS = [
    // General
    { key: 'business_name', value: 'PowerHouse Gym', category: 'general', description: 'Name of the business' },
    { key: 'business_address', value: '', category: 'general', description: 'Physical address' },
    { key: 'contact_email', value: '', category: 'general', description: 'Contact email' },

    // Access
    { key: 'min_confidence', value: 0.75, category: 'access', description: 'Minimum face recognition confidence (0.0 - 1.0)' },
    { key: 'door_open_duration', value: 5, category: 'access', description: 'Seconds to keep door open' },
    { key: 'passback_cooldown', value: 60, category: 'access', description: 'Anti-passback cooldown in seconds' },
    { key: 'deny_unknown', value: true, category: 'access', description: 'Deny access to unknown faces automatically' },

    // Membership
    { key: 'currency', value: 'USD', category: 'membership', description: 'Currency symbol or code' },
    { key: 'payment_grace_period', value: 3, category: 'membership', description: 'Days before suspending overdue members' },

    // System
    { key: 'data_retention_days', value: 90, category: 'system', description: 'Days to keep access logs' },
    { key: 'debug_mode', value: false, category: 'system', description: 'Enable debug logging' },
];

export const SettingsPage: React.FC<SettingsProps> = () => {
    const queryClient = useQueryClient();
    const [activeTab, setActiveTab] = useState(0);
    const [localValues, setLocalValues] = useState<Record<string, any>>({});
    const [hasChanges, setHasChanges] = useState(false);

    const { data: serverSettings, isLoading } = useQuery({
        queryKey: ['settings'],
        queryFn: settingsApi.getAll,
    });

    // Merge server settings with defaults
    const mergedSettings = React.useMemo(() => {
        const merged = [...DEFAULT_SETTINGS];
        if (serverSettings) {
            serverSettings.forEach(s => {
                const index = merged.findIndex(d => d.key === s.key);
                if (index >= 0) {
                    merged[index] = { ...merged[index], ...s };
                } else {
                    merged.push(s as any);
                }
            });
        }
        return merged;
    }, [serverSettings]);

    // Initialize local values
    useEffect(() => {
        const values: Record<string, any> = {};
        mergedSettings.forEach(s => {
            values[s.key] = s.value;
        });
        setLocalValues(values);
        setHasChanges(false);
    }, [mergedSettings]);

    const saveMutation = useMutation({
        mutationFn: async (values: Record<string, any>) => {
            const updates = Object.entries(values).map(([key, value]) => {
                const def = DEFAULT_SETTINGS.find(d => d.key === key);
                return {
                    key,
                    value,
                    category: def?.category || 'general',
                    description: def?.description
                };
            });
            await settingsApi.bulkUpdate(updates);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['settings'] });
            setHasChanges(false);
            alert('Settings saved successfully');
        },
        onError: (err) => {
            alert('Failed to save settings: ' + err);
        }
    });

    const handleChange = (key: string, value: any) => {
        setLocalValues(prev => ({ ...prev, [key]: value }));
        setHasChanges(true);
    };

    const renderField = (setting: any) => {
        const value = localValues[setting.key] ?? setting.value;

        if (typeof setting.value === 'boolean') {
            return (
                <FormControlLabel
                    control={
                        <Switch
                            checked={!!value}
                            onChange={(e) => handleChange(setting.key, e.target.checked)}
                        />
                    }
                    label={setting.key.replace(/_/g, ' ').toUpperCase()}
                />
            );
        }

        if (setting.key === 'min_confidence') {
            return (
                <Box>
                    <Typography gutterBottom>
                        Minimum Confidence: {(value * 100).toFixed(0)}%
                    </Typography>
                    <Slider
                        value={value}
                        min={0.5}
                        max={1.0}
                        step={0.01}
                        onChange={(_, val) => handleChange(setting.key, val)}
                        valueLabelDisplay="auto"
                    />
                </Box>
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
        <Box sx={{ maxWidth: 1200, mx: 'auto', p: 4 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 4 }}>
                <Typography variant="h4" fontWeight="bold">Settings</Typography>
                <Button
                    variant="contained"
                    startIcon={<SaveIcon />}
                    disabled={!hasChanges || saveMutation.isPending}
                    onClick={() => saveMutation.mutate(localValues)}
                >
                    {saveMutation.isPending ? 'Saving...' : 'Save Changes'}
                </Button>
            </Box>

            <Paper sx={{ width: '100%', mb: 2 }}>
                <Tabs
                    value={activeTab}
                    onChange={(_, val) => setActiveTab(val)}
                    indicatorColor="primary"
                    textColor="primary"
                    sx={{ borderBottom: 1, borderColor: 'divider' }}
                >
                    <Tab icon={<BusinessIcon />} label="General" />
                    <Tab icon={<SecurityIcon />} label="Access Control" />
                    <Tab icon={<MembershipIcon />} label="Membership" />
                    <Tab icon={<StorageIcon />} label="System" />
                    <Tab icon={<PeopleIcon />} label="Users" />
                </Tabs>

                <Box sx={{ p: 4 }}>
                    {activeTab === 0 && renderCategory('general')}
                    {activeTab === 1 && renderCategory('access')}
                    {activeTab === 2 && renderCategory('membership')}
                    {activeTab === 3 && renderCategory('system')}
                    {activeTab === 4 && <UserManagement />}
                </Box>
            </Paper>
        </Box>
    );
};
