import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Button,
    Paper,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Chip,
    CircularProgress,
    IconButton,
    Tooltip,
    useMediaQuery,
    useTheme,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    FormControlLabel,
    Switch,
    Alert,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
} from '@mui/material';
import {
    Add as AddIcon,
    Refresh as RefreshIcon,
    SettingsRemote as TestIcon,
    Delete as DeleteIcon,
    Edit as EditIcon,
} from '@mui/icons-material';
import { camerasApi, CameraCreate, VideoDevice } from '@/api/cameras';
import { useLanguage } from '@/i18n/LanguageContext';

export const CamerasList: React.FC = () => {
    const queryClient = useQueryClient();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const { t } = useLanguage();
    const [openAddDialog, setOpenAddDialog] = useState(false);
    const [newCamera, setNewCamera] = useState<CameraCreate>({
        name: '',
        location: '',
        rtsp_url: '',
        enabled: true,
        description: '',
    });
    const [isUsbMode, setIsUsbMode] = useState(false);
    const [detectedDevices, setDetectedDevices] = useState<VideoDevice[]>([]);
    const [isDetecting, setIsDetecting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);

    const { data: cameras, isLoading, refetch } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras(),
    });

    const createMutation = useMutation({
        mutationFn: (data: CameraCreate) => camerasApi.createCamera(data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['cameras'] });
            setOpenAddDialog(false);
            setNewCamera({ name: '', location: '', rtsp_url: '', enabled: true, description: '' });
            setIsUsbMode(false);
            setError(null);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || t.cameras.errorCreating);
        },
    });

    const updateMutation = useMutation({
        mutationFn: (data: any) => camerasApi.updateCamera(editingId!, data),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['cameras'] });
            setOpenAddDialog(false);
            resetForm();
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || t.cameras.errorUpdating);
        },
    });

    const resetForm = () => {
        setNewCamera({ name: '', location: '', rtsp_url: '', enabled: true, description: '' });
        setEditingId(null);
        setIsUsbMode(false);
        setError(null);
    };

    const testMutation = useMutation({
        mutationFn: (id: string) => camerasApi.testCamera(id),
        onSuccess: (data) => {
            alert(`Camera test ${data.status}: ${data.message}`);
        },
    });

    const deleteMutation = useMutation({
        mutationFn: (id: string) => camerasApi.deleteCamera(id),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['cameras'] });
        },
    });

    const detectDevices = async () => {
        setIsDetecting(true);
        const allDevices: VideoDevice[] = [];
        try {
            if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                try { await navigator.mediaDevices.getUserMedia({ video: true }); } catch (e) { console.warn('Permission denied'); }
                const clientDevs = await navigator.mediaDevices.enumerateDevices();
                const videoInputs = clientDevs.filter(d => d.kind === 'videoinput');
                videoInputs.forEach((d, i) => {
                    allDevices.push({ path: `client:${d.deviceId}`, name: `Local: ${d.label || `Camera ${i + 1}`}` });
                });
            }
        } catch (err) { console.warn('Local device detection failed:', err); }
        try {
            const serverDevices = await camerasApi.detectDevices();
            allDevices.push(...serverDevices.map(d => ({ ...d, name: `Server: ${d.name}` })));
        } catch (err: any) { console.error('Failed to detect server devices', err); }
        setDetectedDevices(allDevices);
        setIsDetecting(false);
    };

    const handleAddSubmit = () => {
        if (!newCamera.name || (!newCamera.rtsp_url && !editingId)) {
            setError(t.cameras.nameRequired);
            return;
        }
        if (editingId) { updateMutation.mutate(newCamera); } else { createMutation.mutate(newCamera); }
    };

    const handleEditClick = async (camera: any) => {
        try {
            const { rtsp_url } = await camerasApi.getRtspUrl(camera.id);
            setNewCamera({ name: camera.name, location: camera.location, rtsp_url, enabled: camera.enabled, description: camera.description });
            setEditingId(camera.id);
            setIsUsbMode(rtsp_url.startsWith('/') || /^\d+$/.test(rtsp_url));
            setOpenAddDialog(true);
        } catch (e) { alert('Failed to fetch RTSP URL'); }
    };

    const handleOpenAdd = () => { resetForm(); setOpenAddDialog(true); };

    if (isLoading) {
        return <Box display="flex" justifyContent="center" p={5}><CircularProgress /></Box>;
    }

    return (
        <Box>
            <Box display="flex" flexDirection={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} mb={3} gap={2}>
                <Typography variant={isMobile ? "h5" : "h4"}>{t.cameras.title}</Typography>
                <Box display="flex" gap={1} width={isMobile ? '100%' : 'auto'}>
                    <IconButton onClick={() => refetch()} sx={{ mr: 1 }}><RefreshIcon /></IconButton>
                    <Button variant="contained" startIcon={<AddIcon />} onClick={handleOpenAdd}>
                        {t.cameras.addCamera}
                    </Button>
                </Box>
            </Box>

            <TableContainer component={Paper} sx={{ overflowX: 'auto' }}>
                <Table>
                    <TableHead>
                        <TableRow>
                            <TableCell>{t.cameras.name}</TableCell>
                            <TableCell>{t.cameras.location}</TableCell>
                            {!isMobile && <TableCell>{t.cameras.rtspUrl}</TableCell>}
                            <TableCell>{t.cameras.status}</TableCell>
                            <TableCell align="right">{t.common.actions}</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {cameras?.map((camera) => (
                            <TableRow key={camera.id}>
                                <TableCell>{camera.name}</TableCell>
                                <TableCell>{camera.location}</TableCell>
                                <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {camera.rtsp_url ? (
                                        (camera.rtsp_url.startsWith('/') || /^\d+$/.test(camera.rtsp_url)) ?
                                            <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                                <Typography variant="caption" sx={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{t.cameras.usb}</Typography>
                                                {camera.rtsp_url}
                                            </Box>
                                            : camera.rtsp_url
                                    ) : (
                                        <Typography variant="caption" sx={{ color: 'text.disabled', fontStyle: 'italic' }}>{t.cameras.hidden}</Typography>
                                    )}
                                </TableCell>
                                <TableCell>
                                    <Chip label={camera.enabled ? t.cameras.active : t.members.inactive} color={camera.enabled ? 'success' : 'default'} size="small" />
                                </TableCell>
                                <TableCell align="right">
                                    <Tooltip title={t.cameras.testConnection}><IconButton size="small" sx={{ minWidth: 44, minHeight: 44 }} onClick={() => testMutation.mutate(camera.id)}><TestIcon /></IconButton></Tooltip>
                                    <IconButton size="small" sx={{ minWidth: 44, minHeight: 44 }} onClick={() => handleEditClick(camera)}><EditIcon /></IconButton>
                                    <IconButton size="small" sx={{ minWidth: 44, minHeight: 44 }} color="error" onClick={() => { if (window.confirm(t.cameras.deleteConfirm)) { deleteMutation.mutate(camera.id); } }}><DeleteIcon /></IconButton>
                                </TableCell>
                            </TableRow>
                        ))}
                        {(!cameras || cameras.length === 0) && (
                            <TableRow><TableCell colSpan={isMobile ? 4 : 5} align="center">{t.cameras.noCameras}</TableCell></TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            <Dialog open={openAddDialog} fullScreen={isMobile} onClose={() => setOpenAddDialog(false)} maxWidth="sm" fullWidth>
                <DialogTitle>{editingId ? t.cameras.editCamera : t.cameras.addNewCamera}</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {error && <Alert severity="error">{error}</Alert>}
                        <TextField label={t.cameras.name} fullWidth required value={newCamera.name} onChange={(e) => setNewCamera({ ...newCamera, name: e.target.value })} autoFocus />
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                            <Typography variant="body2" sx={{ mr: 2, fontWeight: 500 }}>{t.cameras.sourceType}</Typography>
                            <FormControlLabel
                                control={<Switch checked={isUsbMode} onChange={(e) => { setIsUsbMode(e.target.checked); setNewCamera({ ...newCamera, rtsp_url: '' }); if (e.target.checked) { detectDevices(); } }} color="secondary" />}
                                label={isUsbMode ? t.cameras.usbWebcam : t.cameras.rtspStream}
                            />
                            {isUsbMode && (
                                <Button size="small" onClick={detectDevices} disabled={isDetecting} sx={{ ml: 1 }}>
                                    {isDetecting ? t.cameras.detecting : t.common.search}
                                </Button>
                            )}
                        </Box>
                        {isUsbMode && (
                            <>
                                {detectedDevices.length > 0 && (
                                    <FormControl fullWidth>
                                        <InputLabel>{t.cameras.videoDevice}</InputLabel>
                                        <Select 
                                            value={detectedDevices.some(d => d.path === newCamera.rtsp_url) ? newCamera.rtsp_url : ''} 
                                            label={t.cameras.videoDevice} 
                                            onChange={(e) => setNewCamera({ ...newCamera, rtsp_url: e.target.value })}
                                        >
                                            <MenuItem value=""><em>{t.cameras.enterManualPath}</em></MenuItem>
                                            {detectedDevices.map((dev) => (
                                                <MenuItem key={dev.path} value={dev.path} sx={{ flexDirection: 'column', alignItems: 'flex-start' }}>
                                                    <Typography variant="body2">{dev.name}</Typography>
                                                    {dev.info && (
                                                        <Typography variant="caption" sx={{ color: 'warning.main' }}>
                                                            ⚠ {dev.info}
                                                        </Typography>
                                                    )}
                                                </MenuItem>
                                            ))}
                                        </Select>
                                    </FormControl>
                                )}
                                {detectedDevices.some(d => d.status === 'needs_passthrough') && (
                                    <Alert severity="warning" sx={{ mt: 1 }}>
                                        USB device detected but /dev/video* nodes missing. Run on Proxmox host:
                                        <br />
                                        <code style={{ fontSize: '0.8em', background: 'rgba(0,0,0,0.1)', padding: '2px 6px', borderRadius: 4 }}>
                                            pct set CONTAINER_ID -devices 0 -lxc.cgroup2.devices.allow: c 81:0 rwm -lxc.mount.entry: /dev/video0 dev/video0 none bind,create=file
                                        </code>
                                    </Alert>
                                )}
                                <TextField
                                    label={t.cameras.devicePath || 'Device Path'}
                                    placeholder="/dev/video0"
                                    fullWidth 
                                    value={newCamera.rtsp_url} 
                                    onChange={(e) => setNewCamera({ ...newCamera, rtsp_url: e.target.value })}
                                    helperText={detectedDevices.length === 0 ? 'No USB devices auto-detected. Enter device path manually (e.g., /dev/video0 or 0)' : 'Or enter a custom device path'}
                                />
                            </>
                        )}
                        {!isUsbMode && (
                            <TextField
                                label={t.cameras.rtspUrl}
                                fullWidth required value={newCamera.rtsp_url} onChange={(e) => setNewCamera({ ...newCamera, rtsp_url: e.target.value })}
                                helperText={t.cameras.rtspHelper}
                            />
                        )}
                        <TextField label={t.cameras.location} fullWidth value={newCamera.location || ''} onChange={(e) => setNewCamera({ ...newCamera, location: e.target.value })} />
                        <TextField label={t.cameras.description} fullWidth multiline rows={2} value={newCamera.description || ''} onChange={(e) => setNewCamera({ ...newCamera, description: e.target.value })} />
                        <FormControlLabel
                            control={<Switch checked={newCamera.enabled ?? true} onChange={(e) => setNewCamera({ ...newCamera, enabled: e.target.checked })} color="primary" />}
                            label={t.cameras.active}
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenAddDialog(false)}>{t.common.cancel}</Button>
                    <Button onClick={handleAddSubmit} variant="contained" disabled={createMutation.isPending || updateMutation.isPending}>
                        {createMutation.isPending || updateMutation.isPending ? t.cameras.saving : (editingId ? t.cameras.update : t.cameras.addCamera)}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
