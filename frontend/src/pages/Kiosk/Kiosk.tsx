import React, { useState, useEffect, useRef, useCallback } from 'react';
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
    IconButton,
    Tooltip,
    alpha,
    keyframes,
    styled,
} from '@mui/material';
import {
    CheckCircle as CheckCircleIcon,
    Cancel as CancelIcon,
    VideocamOff as VideocamOffIcon,
    Usb as UsbIcon,
    Videocam as VideocamIcon,
    WifiOff as WifiOffIcon,
    LinkOff as LinkOffIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';

import { camerasApi } from '@/api/cameras';
import { eventsApi } from '@/api/events';
import { cvServiceApi } from '@/api/cvService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface WsRecognitionResult {
    type: 'recognition';
    member_id: string | null;
    member_name: string | null;
    confidence: number;
    access_granted: boolean;
    denial_reason: string | null;
    face_bbox: number[] | null;
}

interface WsStatusMessage {
    type: 'status';
    fps?: number;
    frames_processed?: number;
    faces?: number;
}

type WsMessage = WsRecognitionResult | WsStatusMessage;

interface LocalEvent {
    id: string;
    member_name: string;
    access_granted: boolean;
    confidence: number;
    timestamp: Date;
    denial_reason?: string | null;
}

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

// ---------------------------------------------------------------------------
// Styled Components
// ---------------------------------------------------------------------------

const pulseGreen = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.7); }
  70% { box-shadow: 0 0 0 10px rgba(76, 175, 80, 0); }
  100% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0); }
`;

const pulseRed = keyframes`
  0% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0.7); }
  70% { box-shadow: 0 0 0 10px rgba(244, 67, 54, 0); }
  100% { box-shadow: 0 0 0 0 rgba(244, 67, 54, 0); }
`;

const StatusDot = styled('span')<{ $color: 'green' | 'red' | 'yellow' }>(({ $color }) => ({
    display: 'inline-block',
    width: 10,
    height: 10,
    borderRadius: '50%',
    backgroundColor:
        $color === 'green' ? '#4caf50' : $color === 'red' ? '#f44336' : '#ff9800',
    marginRight: 6,
    animation: $color !== 'yellow' ? `${$color === 'green' ? pulseGreen : pulseRed} 2s infinite` : 'none',
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_DOT: Record<ConnectionStatus, 'green' | 'red' | 'yellow'> = {
    connected: 'green',
    connecting: 'yellow',
    disconnected: 'red',
    error: 'red',
};

const STATUS_LABEL: Record<ConnectionStatus, string> = {
    connected: 'Live',
    connecting: 'Connecting...',
    disconnected: 'Disconnected',
    error: 'Error',
};

// ---------------------------------------------------------------------------
// Kiosk Component
// ---------------------------------------------------------------------------

export const Kiosk: React.FC = () => {
    const [searchParams, setSearchParams] = useSearchParams();
    const urlCameraId = searchParams.get('cameraId');
    const [selectedCameraId, setSelectedCameraId] = useState<string>(urlCameraId || '');

    // USB camera mode toggle
    const [usbMode, setUsbMode] = useState(false);

    // USB camera state
    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
    const [localEvents, setLocalEvents] = useState<LocalEvent[]>([]);
    const [latestRecognition, setLatestRecognition] = useState<WsRecognitionResult | null>(null);

    // Refs
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Fetch Cameras
    const { data: camerasData, isLoading: loadingCameras } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras(),
    });

    // Poll for Events (Remote mode only)
    const { data: eventsData } = useQuery({
        queryKey: ['kiosk-events', selectedCameraId],
        queryFn: () =>
            eventsApi.getEvents(0, 10, undefined, selectedCameraId || undefined),
        refetchInterval: 2000,
        enabled: !!selectedCameraId && !usbMode,
    });

    const remoteEvents = eventsData?.events || [];

    // -----------------------------------------------------------------------
    // USB Camera Lifecycle
    // -----------------------------------------------------------------------

    const stopUsbCamera = useCallback(() => {
        if (captureIntervalRef.current) {
            clearInterval(captureIntervalRef.current);
            captureIntervalRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
        }
        if (videoRef.current) {
            videoRef.current.srcObject = null;
        }
        if (overlayCanvasRef.current) {
            const ctx = overlayCanvasRef.current.getContext('2d');
            if (ctx) ctx.clearRect(0, 0, overlayCanvasRef.current.width, overlayCanvasRef.current.height);
        }
        setConnectionStatus('disconnected');
        setLatestRecognition(null);
    }, []);

    const startUsbCamera = useCallback(async (cameraId: string) => {
        stopUsbCamera();
        setConnectionStatus('connecting');

        try {
            // 1. Get camera stream
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
            });
            streamRef.current = stream;

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
            }

            // 2. Connect WebSocket
            const wsUrl = cvServiceApi.getWebSocketUrl(cameraId);
            const ws = new WebSocket(wsUrl);
            ws.binaryType = 'arraybuffer';
            wsRef.current = ws;

            ws.onopen = () => {
                setConnectionStatus('connected');
            };

            ws.onmessage = (event) => {
                if (typeof event.data === 'string') {
                    try {
                        const msg: WsMessage = JSON.parse(event.data);
                        if (msg.type === 'recognition') {
                            setLatestRecognition(msg);
                            setLocalEvents((prev) => {
                                const newEvent: LocalEvent = {
                                    id: crypto.randomUUID(),
                                    member_name: msg.member_name || 'Unknown',
                                    access_granted: msg.access_granted,
                                    confidence: msg.confidence,
                                    timestamp: new Date(),
                                    denial_reason: msg.denial_reason,
                                };
                                return [newEvent, ...prev].slice(0, 50);
                            });
                        }
                    } catch {
                        // ignore parse errors
                    }
                }
            };

            ws.onerror = () => {
                setConnectionStatus('error');
            };

            ws.onclose = () => {
                setConnectionStatus('disconnected');
            };

            // 3. Start frame capture loop - every 200ms send a JPEG frame
            captureIntervalRef.current = setInterval(() => {
                if (ws.readyState !== WebSocket.OPEN) return;
                if (!videoRef.current || !canvasRef.current) return;

                const video = videoRef.current;
                const canvas = canvasRef.current;
                if (video.readyState < 2) return; // HAVE_CURRENT_DATA

                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext('2d');
                if (!ctx) return;

                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
                const base64 = dataUrl.split(',')[1];
                const binary = atob(base64);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) {
                    bytes[i] = binary.charCodeAt(i);
                }
                ws.send(bytes);
            }, 200);

        } catch (err) {
            console.error('USB camera error:', err);
            setConnectionStatus('error');
        }
    }, [stopUsbCamera]);

    // Draw bounding box overlay when recognition result arrives
    useEffect(() => {
        const canvas = overlayCanvasRef.current;
        const video = videoRef.current;
        if (!canvas || !video || !usbMode) return;

        canvas.width = video.videoWidth || 1280;
        canvas.height = video.videoHeight || 720;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        if (!latestRecognition || !latestRecognition.face_bbox) return;

        const [x, y, w, h] = latestRecognition.face_bbox;
        const granted = latestRecognition.access_granted;
        const color = granted ? '#4caf50' : '#f44336';
        const label = granted
            ? `ACCESS GRANTED - ${latestRecognition.member_name} (${Math.round(latestRecognition.confidence * 100)}%)`
            : `ACCESS DENIED - ${latestRecognition.member_name || 'Unknown'} (${Math.round(latestRecognition.confidence * 100)}%)`;

        // Bounding box
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(x, y, w, h);

        // Label background
        ctx.font = 'bold 16px monospace';
        const textWidth = ctx.measureText(label).width;
        const labelY = y > 30 ? y - 8 : y + h + 24;
        ctx.fillStyle = color;
        ctx.fillRect(x, labelY - 18, textWidth + 16, 24);

        // Label text
        ctx.fillStyle = '#ffffff';
        ctx.fillText(label, x + 8, labelY);
    }, [latestRecognition, usbMode]);

    // Handle USB mode toggle
    const handleUsbToggle = useCallback(() => {
        if (usbMode) {
            stopUsbCamera();
            setUsbMode(false);
        } else {
            if (!selectedCameraId) return;
            setUsbMode(true);
            setLocalEvents([]);
            startUsbCamera(selectedCameraId);
        }
    }, [usbMode, selectedCameraId, stopUsbCamera, startUsbCamera]);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            stopUsbCamera();
        };
    }, [stopUsbCamera]);

    // Restart USB camera when camera selection changes in USB mode
    useEffect(() => {
        if (usbMode && selectedCameraId) {
            setLocalEvents([]);
            startUsbCamera(selectedCameraId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedCameraId]);

    const handleCameraChange = (e: any) => {
        const id = e.target.value;
        setSelectedCameraId(id);
        setSearchParams({ cameraId: id });
    };

    const displayEvents = usbMode ? localEvents : remoteEvents;

    return (
        <Box
            sx={{
                height: '100vh',
                display: 'flex',
                flexDirection: 'column',
                bgcolor: '#0a0a0a',
                color: 'white',
            }}
        >
            {/* Header / Controls */}
            <Box
                sx={{
                    p: 2,
                    bgcolor: '#141414',
                    borderBottom: '1px solid #2a2a2a',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 2,
                    flexWrap: 'wrap',
                }}
            >
                <FormControl size="small" sx={{ minWidth: 220 }}>
                    <InputLabel id="cam-select-label" sx={{ color: '#aaa' }}>
                        Select Camera
                    </InputLabel>
                    <Select
                        labelId="cam-select-label"
                        value={selectedCameraId}
                        label="Select Camera"
                        onChange={handleCameraChange}
                        sx={{
                            bgcolor: '#1e1e1e',
                            color: 'white',
                            '.MuiOutlinedInput-notchedOutline': { borderColor: '#444' },
                            '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#666' },
                        }}
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

                <Tooltip title={usbMode ? 'Switch to Remote Camera (RTSP)' : 'Switch to Local USB Camera'}>
                    <IconButton
                        onClick={handleUsbToggle}
                        disabled={!selectedCameraId}
                        sx={{
                            bgcolor: usbMode ? alpha('#4caf50', 0.15) : 'transparent',
                            border: '1px solid',
                            borderColor: usbMode ? '#4caf50' : '#444',
                            color: usbMode ? '#4caf50' : '#aaa',
                            '&:hover': {
                                bgcolor: usbMode ? alpha('#4caf50', 0.25) : alpha('#fff', 0.05),
                            },
                            '&.Mui-disabled': {
                                bgcolor: 'transparent',
                                borderColor: '#333',
                                color: '#555',
                            },
                        }}
                    >
                        {usbMode ? <UsbIcon /> : <VideocamIcon />}
                    </IconButton>
                </Tooltip>

                {usbMode && (
                    <Box sx={{ display: 'flex', alignItems: 'center', ml: 1 }}>
                        <StatusDot $color={STATUS_DOT[connectionStatus]} />
                        <Typography variant="body2" sx={{ color: '#aaa' }}>
                            USB Camera - {STATUS_LABEL[connectionStatus]}
                        </Typography>
                    </Box>
                )}
            </Box>

            {/* Main Content */}
            <Grid container sx={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
                {/* Video Feed */}
                <Grid
                    item
                    xs={12}
                    md={8}
                    sx={{
                        bgcolor: '#000',
                        position: 'relative',
                        overflow: 'hidden',
                        minHeight: 0,
                    }}
                >
                    <Box sx={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        overflow: 'hidden',
                    }}>
                    {selectedCameraId ? (
                        usbMode ? (
                            <>
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    style={{
                                        display: 'block',
                                        maxWidth: '100%',
                                        maxHeight: '100%',
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'contain',
                                    }}
                                />
                                <canvas
                                    ref={overlayCanvasRef}
                                    style={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'contain',
                                        pointerEvents: 'none',
                                    }}
                                />
                                <canvas ref={canvasRef} style={{ display: 'none' }} />
                                {connectionStatus === 'error' && (
                                    <Box
                                        sx={{
                                            position: 'absolute',
                                            inset: 0,
                                            display: 'flex',
                                            flexDirection: 'column',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            bgcolor: alpha('#000', 0.7),
                                        }}
                                    >
                                        <WifiOffIcon sx={{ fontSize: 48, color: '#f44336', mb: 1 }} />
                                        <Typography color="error">Connection Error</Typography>
                                        <Typography variant="body2" color="grey.500">
                                            Check that the CV service is running
                                        </Typography>
                                    </Box>
                                )}
                            </>
                        ) : (
                            <img
                                src={cvServiceApi.getStreamUrl(selectedCameraId)}
                                alt="Live Camera Feed"
                                style={{
                                    display: 'block',
                                    maxWidth: '100%',
                                    maxHeight: '100%',
                                    width: '100%',
                                    height: '100%',
                                    objectFit: 'contain',
                                }}
                            />
                        )
                    ) : (
                        <Box textAlign="center" color="grey.500">
                            <VideocamOffIcon sx={{ fontSize: 60 }} />
                            <Typography mt={1}>Select a camera to start monitoring</Typography>
                        </Box>
                    )}
                    </Box>
                </Grid>

                {/* Events Panel */}
                <Grid
                    item
                    xs={12}
                    md={4}
                    sx={{
                        borderLeft: '1px solid #2a2a2a',
                        display: 'flex',
                        flexDirection: 'column',
                        bgcolor: '#111',
                    }}
                >
                    <Box sx={{ p: 2, bgcolor: '#141414', borderBottom: '1px solid #2a2a2a' }}>
                        <Typography variant="h6" fontWeight="bold">
                            Recent Access
                        </Typography>
                        <Typography variant="caption" color="grey.500">
                            {usbMode ? 'Live via USB camera' : 'Polling from server'}
                        </Typography>
                    </Box>

                    <Box sx={{ flex: 1, overflow: 'auto', p: 1 }}>
                        <List disablePadding>
                            {displayEvents.map((event: any) => (
                                <Card
                                    key={event.id}
                                    sx={{
                                        mb: 1,
                                        bgcolor: '#1a1a1a',
                                        color: 'white',
                                        border: '1px solid',
                                        borderColor: event.access_granted
                                            ? alpha('#4caf50', 0.3)
                                            : alpha('#f44336', 0.3),
                                        transition: 'all 0.3s ease',
                                    }}
                                >
                                    <ListItem alignItems="flex-start" sx={{ py: 1, px: 1.5 }}>
                                        <ListItemAvatar sx={{ minWidth: 42 }}>
                                            <Avatar
                                                sx={{
                                                    width: 32,
                                                    height: 32,
                                                    bgcolor: event.access_granted
                                                        ? 'success.main'
                                                        : 'error.main',
                                                }}
                                            >
                                                {event.access_granted ? (
                                                    <CheckCircleIcon sx={{ fontSize: 18 }} />
                                                ) : (
                                                    <CancelIcon sx={{ fontSize: 18 }} />
                                                )}
                                            </Avatar>
                                        </ListItemAvatar>
                                        <ListItemText
                                            primary={
                                                <Typography variant="subtitle2" fontWeight="bold">
                                                    {event.member_name || 'Unknown Person'}
                                                </Typography>
                                            }
                                            secondary={
                                                <Box
                                                    component="span"
                                                    sx={{
                                                        display: 'flex',
                                                        flexDirection: 'column',
                                                        gap: 0.3,
                                                    }}
                                                >
                                                    <Typography variant="caption" color="grey.400">
                                                        {format(
                                                            new Date(event.timestamp),
                                                            'h:mm:ss a'
                                                        )}
                                                    </Typography>
                                                    <Box display="flex" gap={1} alignItems="center">
                                                        <Chip
                                                            label={
                                                                event.access_granted
                                                                    ? 'Granted'
                                                                    : 'Denied'
                                                            }
                                                            color={
                                                                event.access_granted
                                                                    ? 'success'
                                                                    : 'error'
                                                            }
                                                            size="small"
                                                            sx={{ height: 22, fontSize: '0.7rem' }}
                                                        />
                                                        <Typography
                                                            variant="caption"
                                                            color="grey.500"
                                                        >
                                                            {(
                                                                (event.confidence_score ||
                                                                    event.confidence ||
                                                                    0) * 100
                                                            ).toFixed(0)}
                                                            % match
                                                        </Typography>
                                                    </Box>
                                                    {!event.access_granted &&
                                                        event.denial_reason && (
                                                            <Typography
                                                                variant="caption"
                                                                color="error.light"
                                                            >
                                                                {event.denial_reason}
                                                            </Typography>
                                                        )}
                                                </Box>
                                            }
                                        />
                                    </ListItem>
                                </Card>
                            ))}

                            {displayEvents.length === 0 && (
                                <Box textAlign="center" color="grey.600" mt={6} px={2}>
                                    {usbMode ? (
                                        <>
                                            <LinkOffIcon sx={{ fontSize: 40, mb: 1 }} />
                                            <Typography variant="body2">
                                                Waiting for camera feed...
                                            </Typography>
                                            <Typography variant="caption">
                                                Point your face at the camera
                                            </Typography>
                                        </>
                                    ) : (
                                        <>
                                            <VideocamOffIcon sx={{ fontSize: 40, mb: 1 }} />
                                            <Typography variant="body2">
                                                Waiting for events...
                                            </Typography>
                                        </>
                                    )}
                                </Box>
                            )}
                        </List>
                    </Box>
                </Grid>
            </Grid>
        </Box>
    );
};
