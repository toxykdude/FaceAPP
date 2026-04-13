import React, { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    Box,
    Card,
    Typography,
    Grid,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    List,
    ListItem,
    ListItemAvatar,
    Avatar,
    ListItemText,
    Chip,
} from '@mui/material';
import {
    CheckCircle as CheckCircleIcon,
    Cancel as CancelIcon,
    VideocamOff as VideocamOffIcon
} from '@mui/icons-material';
import { format } from 'date-fns';

import { camerasApi } from '@/api/cameras';
import { eventsApi } from '@/api/events';
import { cvServiceApi } from '@/api/cvService';

export const Kiosk: React.FC = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const urlCameraId = searchParams.get('cameraId');
    const [selectedCameraId, setSelectedCameraId] = useState<string>(urlCameraId || '');

    // Fetch Cameras
    const { data: camerasData, isLoading: loadingCameras } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras(),
    });

    // Cameras are auto-started by CV service on startup — no need to start them here

    const handleCameraChange = (e: any) => {
        const id = e.target.value;
        setSelectedCameraId(id);
        setSearchParams({ cameraId: id });
    };

    // Poll for Events (Real-time)
    const { data: eventsData } = useQuery({
        queryKey: ['kiosk-events', selectedCameraId],
        queryFn: () => eventsApi.getEvents(0, 10, undefined, selectedCameraId || undefined),
        refetchInterval: 2000, // Poll every 2 seconds
        enabled: !!selectedCameraId
    });

    const events = eventsData?.events || [];

    return (
        <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', bgcolor: '#121212', color: 'white' }}>
            {/* Header / Controls */}
            <Box sx={{ p: 2, bgcolor: '#1e1e1e', borderBottom: '1px solid #333' }}>
                <FormControl size="small" sx={{ minWidth: 200, bgcolor: 'white', borderRadius: 1 }}>
                    <InputLabel id="cam-select-label">Select Camera</InputLabel>
                    <Select
                        labelId="cam-select-label"
                        value={selectedCameraId}
                        label="Select Camera"
                        onChange={handleCameraChange}
                    >
                        {loadingCameras ? (
                            <MenuItem disabled>Loading...</MenuItem>
                        ) : (
                            camerasData?.map((cam: any) => (
                                <MenuItem key={cam.id} value={cam.id}>
                                    {cam.name}
                                </MenuItem>
                            ))
                        )}
                        {!loadingCameras && (!camerasData || camerasData.length === 0) && (
                            <MenuItem disabled>No cameras found</MenuItem>
                        )}
                    </Select>
                </FormControl>
            </Box>

            {/* Main Content */}
            <Grid container sx={{ flex: 1, overflow: 'hidden' }}>
                {/* Video Feed */}
                <Grid item xs={12} md={8} sx={{ bgcolor: 'black', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {selectedCameraId ? (
                        <img
                            src={cvServiceApi.getStreamUrl(selectedCameraId)}
                            style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
                            onError={(e) => {
                                // Fallback logic or retry could go here
                                (e.target as HTMLImageElement).alt = "Stream disconnected or loading...";
                            }}
                            alt="Live Camera Feed"
                        />
                    ) : (
                        <Box textAlign="center" color="grey.500">
                            <VideocamOffIcon sx={{ fontSize: 60 }} />
                            <Typography>Select a camera to start monitoring</Typography>
                        </Box>
                    )}
                </Grid>

                {/* Live Feed / Events */}
                <Grid item xs={12} md={4} sx={{ borderLeft: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
                    <Box sx={{ p: 2, bgcolor: '#1e1e1e' }}>
                        <Typography variant="h6">Recent Access</Typography>
                    </Box>
                    <Box sx={{ flex: 1, overflow: 'auto', p: 1 }}>
                        <List>
                            {events.map((event: any) => (
                                <Card key={event.id} sx={{ mb: 1, bgcolor: '#252525', color: 'white' }}>
                                    <ListItem alignItems="flex-start">
                                        <ListItemAvatar>
                                            <Avatar sx={{ bgcolor: event.access_granted ? 'success.main' : 'error.main' }}>
                                                {event.access_granted ? <CheckCircleIcon /> : <CancelIcon />}
                                            </Avatar>
                                        </ListItemAvatar>
                                        <ListItemText
                                            primary={
                                                <Typography variant="subtitle1" fontWeight="bold">
                                                    {event.member_name || 'Unknown Person'}
                                                </Typography>
                                            }
                                            secondary={
                                                <Box component="span" sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                                                    <Typography variant="body2" color="grey.400">
                                                        {format(new Date(event.timestamp), 'h:mm:ss a')}
                                                    </Typography>
                                                    <Box display="flex" gap={1} alignItems="center">
                                                        <Chip
                                                            label={event.access_granted ? "Access Granted" : "Denied"}
                                                            color={event.access_granted ? "success" : "error"}
                                                            size="small"
                                                        />
                                                        {event.confidence_score > 0 && (
                                                            <Typography variant="caption" color="grey.500">
                                                                {(event.confidence_score * 100).toFixed(0)}% match
                                                            </Typography>
                                                        )}
                                                    </Box>
                                                    {!event.access_granted && event.denial_reason && (
                                                        <Typography variant="caption" color="error.light">
                                                            Reason: {event.denial_reason}
                                                        </Typography>
                                                    )}
                                                </Box>
                                            }
                                        />
                                    </ListItem>
                                </Card>
                            ))}
                            {events.length === 0 && (
                                <Typography textAlign="center" color="grey.500" mt={4}>
                                    Waiting for events...
                                </Typography>
                            )}
                        </List>
                    </Box>
                </Grid>
            </Grid>
        </Box>
    );
};
