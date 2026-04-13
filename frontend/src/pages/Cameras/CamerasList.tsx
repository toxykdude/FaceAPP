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

export const CamerasList: React.FC = () => {
    const queryClient = useQueryClient();
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
            setNewCamera({
                name: '',
                location: '',
                rtsp_url: '',

                enabled: true,
                description: '',
            });
            setIsUsbMode(false);
            setError(null);
        },
        onError: (err: any) => {
            setError(err.response?.data?.detail || 'Failed to create camera');
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
            setError(err.response?.data?.detail || 'Failed to update camera');
        },
    });

    const resetForm = () => {
        setNewCamera({
            name: '',
            location: '',
            rtsp_url: '',

            enabled: true,
            description: '',
        });
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

        // 1. Detect Browser/Client Devices
        try {
            if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                try {
                    // Request permission first to get labels
                    await navigator.mediaDevices.getUserMedia({ video: true });
                } catch (e) {
                    console.warn('Permission denied for local camera access');
                }
                const clientDevs = await navigator.mediaDevices.enumerateDevices();
                const videoInputs = clientDevs.filter(d => d.kind === 'videoinput');

                videoInputs.forEach((d, i) => {
                    allDevices.push({
                        path: `client:${d.deviceId}`,
                        name: `Local: ${d.label || `Camera ${i + 1}`}`
                    });
                });
            }
        } catch (err) {
            console.warn('Local device detection failed:', err);
        }

        // 2. Detect Server Devices
        try {
            const serverDevices = await camerasApi.detectDevices();
            // Prefix server devices to distinguish
            const serverDevsMapped = serverDevices.map(d => ({
                ...d,
                name: `Server: ${d.name}`
            }));
            allDevices.push(...serverDevsMapped);
        } catch (err: any) {
            console.error('Failed to detect server devices', err);
        }

        setDetectedDevices(allDevices);
        setIsDetecting(false);
    };

    const handleAddSubmit = () => {
        if (!newCamera.name || (!newCamera.rtsp_url && !editingId)) {
            setError('Name and RTSP URL are required');
            return;
        }

        if (editingId) {
            updateMutation.mutate(newCamera);
        } else {
            createMutation.mutate(newCamera);
        }
    };

    const handleEditClick = async (camera: any) => {
        try {
            const { rtsp_url } = await camerasApi.getRtspUrl(camera.id);
            setNewCamera({
                name: camera.name,
                location: camera.location,
                rtsp_url: rtsp_url,
                enabled: camera.enabled,
                description: camera.description
            });
            setEditingId(camera.id);
            setIsUsbMode(rtsp_url.startsWith('/') || /^\d+$/.test(rtsp_url));
            setOpenAddDialog(true);
        } catch (e) {
            alert('Failed to fetch RTSP URL for editing');
        }
    };

    const handleOpenAdd = () => {
        resetForm();
        setOpenAddDialog(true);
    };

    if (isLoading) {
        return (
            <Box display="flex" justifyContent="center" p={5}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h4">Cameras</Typography>
                <Box>
                    <IconButton onClick={() => refetch()} sx={{ mr: 1 }}>
                        <RefreshIcon />
                    </IconButton>
                    <Button
                        variant="contained"
                        startIcon={<AddIcon />}
                        onClick={handleOpenAdd}
                    >
                        Add Camera
                    </Button>
                </Box>
            </Box>

            <TableContainer component={Paper}>
                <Table>
                    <TableHead>
                        <TableRow>
                            <TableCell>Name</TableCell>
                            <TableCell>Location</TableCell>
                            <TableCell>RTSP URL</TableCell>
                            <TableCell>Status</TableCell>
                            <TableCell align="right">Actions</TableCell>
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
                                                <Typography variant="caption" sx={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>USB</Typography>
                                                {camera.rtsp_url}
                                            </Box>
                                            : camera.rtsp_url
                                    ) : (
                                        <Typography variant="caption" sx={{ color: 'text.disabled', fontStyle: 'italic' }}>
                                            Hidden (Security)
                                        </Typography>
                                    )}
                                </TableCell>
                                <TableCell>
                                    <Chip
                                        label={camera.enabled ? 'Active' : 'Inactive'}
                                        color={camera.enabled ? 'success' : 'default'}
                                        size="small"
                                    />
                                </TableCell>
                                <TableCell align="right">
                                    <Tooltip title="Test Connection">
                                        <IconButton size="small" onClick={() => testMutation.mutate(camera.id)}>
                                            <TestIcon />
                                        </IconButton>
                                    </Tooltip>
                                    <IconButton size="small" onClick={() => handleEditClick(camera)}>
                                        <EditIcon />
                                    </IconButton>
                                    <IconButton size="small" color="error" onClick={() => {
                                        if (window.confirm('Are you sure you want to delete this camera?')) {
                                            deleteMutation.mutate(camera.id);
                                        }
                                    }}>
                                        <DeleteIcon />
                                    </IconButton>
                                </TableCell>
                            </TableRow>
                        ))}
                        {(!cameras || cameras.length === 0) && (
                            <TableRow>
                                <TableCell colSpan={5} align="center">
                                    No cameras found.
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Add Camera Dialog */}
            <Dialog
                open={openAddDialog}
                onClose={() => setOpenAddDialog(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>{editingId ? 'Edit Camera' : 'Add New Camera'}</DialogTitle>
                <DialogContent>
                    <Box sx={{ pt: 1, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {error && <Alert severity="error">{error}</Alert>}

                        <TextField
                            label="Name"
                            fullWidth
                            required
                            value={newCamera.name}
                            onChange={(e) => setNewCamera({ ...newCamera, name: e.target.value })}
                            autoFocus
                        />

                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                            <Typography variant="body2" sx={{ mr: 2, fontWeight: 500 }}>
                                Source Type:
                            </Typography>
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={isUsbMode}
                                        onChange={(e) => {
                                            setIsUsbMode(e.target.checked);
                                            setNewCamera({ ...newCamera, rtsp_url: '' });
                                            if (e.target.checked) {
                                                detectDevices();
                                            }
                                        }}
                                        color="secondary"
                                    />
                                }
                                label={isUsbMode ? "USB Webcam" : "RTSP Stream"}
                            />
                            {isUsbMode && (
                                <Button size="small" onClick={detectDevices} disabled={isDetecting} sx={{ ml: 1 }}>
                                    {isDetecting ? 'Detecting...' : 'Refresh'}
                                </Button>
                            )}
                        </Box>

                        {isUsbMode && detectedDevices.length > 0 ? (
                            <FormControl fullWidth required>
                                <InputLabel>Video Device</InputLabel>
                                <Select
                                    value={newCamera.rtsp_url}
                                    label="Video Device"
                                    onChange={(e) => setNewCamera({ ...newCamera, rtsp_url: e.target.value })}
                                >
                                    {detectedDevices.map((dev) => (
                                        <MenuItem key={dev.path} value={dev.path}>
                                            {dev.name}
                                        </MenuItem>
                                    ))}
                                    <MenuItem value="manual">
                                        <em>Enter Manual Path...</em>
                                    </MenuItem>
                                </Select>
                            </FormControl>
                        ) : (
                            <TextField
                                label={isUsbMode ? "Device Path / Index" : "RTSP URL"}
                                fullWidth
                                required
                                value={newCamera.rtsp_url}
                                onChange={(e) => setNewCamera({ ...newCamera, rtsp_url: e.target.value })}
                                helperText={
                                    isUsbMode
                                        ? "e.g., /dev/video0 (Linux), 0 (Default Webcam)"
                                        : "e.g., rtsp://user:pass@IP:554/stream"
                                }
                            />
                        )}

                        <TextField
                            label="Location"
                            fullWidth
                            value={newCamera.location || ''}
                            onChange={(e) => setNewCamera({ ...newCamera, location: e.target.value })}
                        />

                        <TextField
                            label="Description"
                            fullWidth
                            multiline
                            rows={2}
                            value={newCamera.description || ''}
                            onChange={(e) => setNewCamera({ ...newCamera, description: e.target.value })}
                        />

                        <FormControlLabel
                            control={
                                <Switch
                                    checked={newCamera.enabled ?? true}
                                    onChange={(e) => setNewCamera({ ...newCamera, enabled: e.target.checked })}
                                    color="primary"
                                />
                            }
                            label="Active"
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenAddDialog(false)}>Cancel</Button>
                    <Button
                        onClick={handleAddSubmit}
                        variant="contained"
                        disabled={createMutation.isPending || updateMutation.isPending}
                    >
                        {createMutation.isPending || updateMutation.isPending ? 'Saving...' : (editingId ? 'Update' : 'Add Camera')}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};
