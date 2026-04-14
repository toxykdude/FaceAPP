import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Fade,
    alpha,
    keyframes,
    styled,
    Tooltip,
    IconButton,
    Chip,
} from '@mui/material';
import {
    CheckCircle as CheckCircleIcon,
    VideocamOff as VideocamOffIcon,
    Usb as UsbIcon,
    Videocam as VideocamIcon,
    WifiOff as WifiOffIcon,
    Settings as SettingsIcon,
    Close as CloseIcon,
    WarningAmber as WarningAmberIcon,
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
type RecognitionState = 'idle' | 'granted' | 'denied';

// ---------------------------------------------------------------------------
// Keyframe Animations
// ---------------------------------------------------------------------------

const pulseGreen = keyframes`
  0% { box-shadow: 0 0 20px 5px rgba(76, 175, 80, 0.4); }
  50% { box-shadow: 0 0 60px 15px rgba(76, 175, 80, 0.7); }
  100% { box-shadow: 0 0 20px 5px rgba(76, 175, 80, 0.4); }
`;

const pulseRed = keyframes`
  0% { box-shadow: 0 0 20px 5px rgba(244, 67, 54, 0.4); }
  50% { box-shadow: 0 0 60px 15px rgba(244, 67, 54, 0.7); }
  100% { box-shadow: 0 0 20px 5px rgba(244, 67, 54, 0.4); }
`;

const slideDown = keyframes`
  from { transform: translateY(-30px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
`;

const fadeIn = keyframes`
  from { opacity: 0; }
  to { opacity: 1; }
`;

const breathe = keyframes`
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
`;

// ---------------------------------------------------------------------------
// Styled Components
// ---------------------------------------------------------------------------

const CameraContainer = styled('div')<{
    $state: RecognitionState;
}>(({ $state }) => ({
    position: 'relative',
    width: '100%',
    maxWidth: 800,
    aspectRatio: '16 / 9',
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#000',
    border: '3px solid',
    borderColor:
        $state === 'granted'
            ? '#4caf50'
            : $state === 'denied'
              ? '#f44336'
              : '#222',
    transition: 'border-color 0.4s ease, box-shadow 0.4s ease',
    animation:
        $state === 'granted'
            ? `${pulseGreen} 1.5s ease-in-out 2`
            : $state === 'denied'
              ? `${pulseRed} 2s ease-in-out 1`
              : 'none',
}));

const StatusDotSmall = styled('span')<{ $color: 'green' | 'red' | 'yellow' }>(({ $color }) => ({
    display: 'inline-block',
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor:
        $color === 'green' ? '#4caf50' : $color === 'red' ? '#f44336' : '#ff9800',
    animation: $color !== 'yellow' ? `${breathe} 2s ease-in-out infinite` : 'none',
}));

const STATUS_DOT: Record<ConnectionStatus, 'green' | 'red' | 'yellow'> = {
    connected: 'green',
    connecting: 'yellow',
    disconnected: 'red',
    error: 'red',
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

    // Recognition display state
    const [recognitionState, setRecognitionState] = useState<RecognitionState>('idle');
    const [recognizedName, setRecognizedName] = useState<string>('');
    const [, setDenialReason] = useState<string>('');
    const [currentTime, setCurrentTime] = useState(new Date());

    // Settings panel toggle
    const [settingsOpen, setSettingsOpen] = useState(false);

    // Auto-reset timer ref
    const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Refs
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // Clock — update every second
    useEffect(() => {
        const interval = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(interval);
    }, []);

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
    // Recognition State Machine
    // -----------------------------------------------------------------------

    const resetRecognition = useCallback(() => {
        setRecognitionState('idle');
        setRecognizedName('');
        setDenialReason('');
    }, []);

    // When latestRecognition changes, drive the state machine
    useEffect(() => {
        if (!latestRecognition || !latestRecognition.member_name) return;

        // Clear any existing reset timer
        if (resetTimerRef.current) {
            clearTimeout(resetTimerRef.current);
            resetTimerRef.current = null;
        }

        if (latestRecognition.access_granted) {
            setRecognitionState('granted');
        } else {
            setRecognitionState('denied');
        }
        setRecognizedName(latestRecognition.member_name);
        setDenialReason(latestRecognition.denial_reason || '');

        // Auto-reset to idle after 3 seconds
        resetTimerRef.current = setTimeout(() => {
            resetRecognition();
        }, 3000);

        return () => {
            if (resetTimerRef.current) {
                clearTimeout(resetTimerRef.current);
            }
        };
    }, [latestRecognition, resetRecognition]);

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
    const recentCheckins = displayEvents.slice(0, 3);

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    return (
        <Box
            sx={{
                height: '100vh',
                width: '100vw',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                background: 'linear-gradient(180deg, #0a0a0a 0%, #111111 100%)',
                color: 'white',
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* ---- TOP BAR: Logo (center) + Time (right) ---- */}
            <Box
                sx={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    px: 4,
                    py: 2.5,
                    zIndex: 10,
                }}
            >
                {/* Logo / Brand */}
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <img
                        src="/logo.png"
                        alt="PowerHouse Gym"
                        style={{ height: 36, width: 'auto' }}
                        onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                        }}
                    />
                    <Typography
                        variant="h5"
                        fontWeight={900}
                        sx={{
                            letterSpacing: '0.05em',
                            background: 'linear-gradient(135deg, #fff 0%, #aaa 100%)',
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            fontSize: { xs: '1.1rem', md: '1.5rem' },
                        }}
                    >
                        POWERHOUSE GYM
                    </Typography>
                </Box>

                {/* Clock */}
                <Typography
                    variant="h4"
                    fontWeight={300}
                    sx={{
                        color: 'rgba(255,255,255,0.6)',
                        fontVariantNumeric: 'tabular-nums',
                        letterSpacing: '0.02em',
                    }}
                >
                    {format(currentTime, 'h:mm a')}
                </Typography>
            </Box>

            {/* ---- MAIN CONTENT: Camera + Recognition Overlay ---- */}
            <Box
                sx={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '100%',
                    px: 3,
                    pt: 8, // account for top bar
                    pb: 6, // account for bottom check-ins
                }}
            >
                {/* Recognition Overlay — shows ABOVE camera */}
                <Fade in={recognitionState !== 'idle'} timeout={400}>
                    <Box
                        sx={{
                            textAlign: 'center',
                            mb: 2.5,
                            minHeight: 70,
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                        }}
                    >
                        {recognitionState === 'granted' && (
                            <Box
                                sx={{
                                    animation: `${slideDown} 0.4s ease-out`,
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                }}
                            >
                                <CheckCircleIcon
                                    sx={{ fontSize: 48, color: '#4caf50', mb: 0.5 }}
                                />
                                <Typography
                                    variant="h4"
                                    fontWeight={800}
                                    sx={{
                                        color: '#4caf50',
                                        letterSpacing: '0.02em',
                                        textShadow: '0 0 20px rgba(76, 175, 80, 0.4)',
                                    }}
                                >
                                    WELCOME BACK!
                                </Typography>
                                <Typography
                                    variant="h5"
                                    fontWeight={600}
                                    sx={{ color: 'rgba(255,255,255,0.9)', mt: 0.5 }}
                                >
                                    {recognizedName}
                                </Typography>
                            </Box>
                        )}
                        {recognitionState === 'denied' && (
                            <Box
                                sx={{
                                    animation: `${slideDown} 0.4s ease-out`,
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                }}
                            >
                                <WarningAmberIcon
                                    sx={{ fontSize: 48, color: '#f44336', mb: 0.5 }}
                                />
                                <Typography
                                    variant="h4"
                                    fontWeight={800}
                                    sx={{
                                        color: '#f44336',
                                        letterSpacing: '0.02em',
                                        textShadow: '0 0 20px rgba(244, 67, 54, 0.4)',
                                    }}
                                >
                                    MEMBERSHIP EXPIRED
                                </Typography>
                                <Typography
                                    variant="h5"
                                    fontWeight={600}
                                    sx={{ color: 'rgba(255,255,255,0.9)', mt: 0.5 }}
                                >
                                    {recognizedName}
                                </Typography>
                                <Typography
                                    variant="body2"
                                    sx={{ color: 'rgba(255,255,255,0.5)', mt: 0.5 }}
                                >
                                    Please visit reception to renew
                                </Typography>
                            </Box>
                        )}
                    </Box>
                </Fade>

                {/* Camera Feed — Hero Element */}
                <CameraContainer $state={recognitionState}>
                    {selectedCameraId ? (
                        usbMode ? (
                            <>
                                <video
                                    ref={videoRef}
                                    autoPlay
                                    playsInline
                                    muted
                                    style={{
                                        position: 'absolute',
                                        top: 0,
                                        left: 0,
                                        width: '100%',
                                        height: '100%',
                                        objectFit: 'cover',
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
                                            bgcolor: alpha('#000', 0.8),
                                        }}
                                    >
                                        <WifiOffIcon sx={{ fontSize: 48, color: '#f44336', mb: 1 }} />
                                        <Typography color="error" fontWeight={600}>
                                            Camera Error
                                        </Typography>
                                        <Typography variant="body2" sx={{ color: 'grey.500' }}>
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
                                    position: 'absolute',
                                    top: 0,
                                    left: 0,
                                    width: '100%',
                                    height: '100%',
                                    objectFit: 'cover',
                                }}
                            />
                        )
                    ) : (
                        <Box
                            sx={{
                                position: 'absolute',
                                inset: 0,
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                justifyContent: 'center',
                                bgcolor: '#0d0d0d',
                            }}
                        >
                            <VideocamOffIcon sx={{ fontSize: 64, color: '#333', mb: 1 }} />
                            <Typography sx={{ color: '#555', fontWeight: 500 }}>
                                Select a camera to start
                            </Typography>
                            <Typography variant="caption" sx={{ color: '#444', mt: 0.5 }}>
                                Open settings to configure
                            </Typography>
                        </Box>
                    )}

                    {/* Scanning indicator when USB is connected and idle */}
                    {usbMode && connectionStatus === 'connected' && recognitionState === 'idle' && (
                        <Box
                            sx={{
                                position: 'absolute',
                                bottom: 12,
                                left: '50%',
                                transform: 'translateX(-50%)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 1,
                                bgcolor: 'rgba(0,0,0,0.6)',
                                px: 2,
                                py: 0.75,
                                borderRadius: 3,
                                backdropFilter: 'blur(8px)',
                            }}
                        >
                            <Box
                                sx={{
                                    width: 8,
                                    height: 8,
                                    borderRadius: '50%',
                                    bgcolor: '#4caf50',
                                    animation: `${breathe} 1.5s ease-in-out infinite`,
                                }}
                            />
                            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.7)' }}>
                                Scanning...
                            </Typography>
                        </Box>
                    )}
                </CameraContainer>

                {/* Idle message below camera */}
                <Fade in={recognitionState === 'idle' && !!selectedCameraId}>
                    <Box
                        sx={{
                            mt: 2.5,
                            textAlign: 'center',
                            animation: `${fadeIn} 0.6s ease-out`,
                        }}
                    >
                        <Typography
                            variant="body1"
                            sx={{ color: 'rgba(255,255,255,0.35)', fontWeight: 400 }}
                        >
                            Please face the camera to check in
                        </Typography>
                    </Box>
                </Fade>
            </Box>

            {/* ---- BOTTOM BAR: Recent Check-ins ---- */}
            <Box
                sx={{
                    position: 'absolute',
                    bottom: 0,
                    left: 0,
                    right: 0,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 3,
                    px: 4,
                    py: 2,
                    zIndex: 10,
                }}
            >
                {recentCheckins.map((event: any) => (
                    <Chip
                        key={event.id}
                        size="small"
                        sx={{
                            bgcolor: 'rgba(255,255,255,0.05)',
                            border: '1px solid',
                            borderColor: event.access_granted
                                ? 'rgba(76,175,80,0.2)'
                                : 'rgba(244,67,54,0.2)',
                            color: 'rgba(255,255,255,0.5)',
                            fontSize: '0.75rem',
                            '& .MuiChip-icon': {
                                color: event.access_granted ? '#4caf50' : '#f44336',
                            },
                            '& .MuiChip-label': {
                                display: 'flex',
                                alignItems: 'center',
                                gap: 0.5,
                            },
                        }}
                        icon={
                            <StatusDotSmall
                                $color={event.access_granted ? 'green' : 'red'}
                            />
                        }
                        label={`${event.member_name} · ${format(new Date(event.timestamp), 'h:mm a')}`}
                    />
                ))}
            </Box>

            {/* ---- SETTINGS PANEL (bottom-right, expandable) ---- */}
            <Box
                sx={{
                    position: 'absolute',
                    bottom: 16,
                    right: 16,
                    zIndex: 20,
                }}
            >
                <Fade in={settingsOpen} timeout={200}>
                    <Box
                        sx={{
                            display: settingsOpen ? 'block' : 'none',
                            bgcolor: 'rgba(20,20,20,0.95)',
                            backdropFilter: 'blur(12px)',
                            border: '1px solid #333',
                            borderRadius: 2,
                            p: 2.5,
                            mb: 1,
                            minWidth: 260,
                            animation: settingsOpen ? `${fadeIn} 0.2s ease-out` : 'none',
                        }}
                    >
                        {/* Close button */}
                        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: -1 }}>
                            <IconButton size="small" onClick={() => setSettingsOpen(false)}>
                                <CloseIcon sx={{ fontSize: 18, color: '#888' }} />
                            </IconButton>
                        </Box>

                        <Typography variant="caption" sx={{ color: '#666', mb: 1, display: 'block' }}>
                            Kiosk Settings
                        </Typography>

                        {/* Camera Select */}
                        <FormControl size="small" fullWidth sx={{ mt: 1 }}>
                            <InputLabel id="cam-select-label" sx={{ color: '#aaa', fontSize: '0.8rem' }}>
                                Camera
                            </InputLabel>
                            <Select
                                labelId="cam-select-label"
                                value={selectedCameraId}
                                label="Camera"
                                onChange={handleCameraChange}
                                sx={{
                                    bgcolor: '#1a1a1a',
                                    color: 'white',
                                    fontSize: '0.85rem',
                                    '.MuiOutlinedInput-notchedOutline': { borderColor: '#333' },
                                    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#555' },
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

                        {/* USB Toggle */}
                        <Tooltip
                            title={usbMode ? 'Switch to Remote Camera (RTSP)' : 'Switch to Local USB Camera'}
                        >
                            <Box
                                onClick={selectedCameraId ? handleUsbToggle : undefined}
                                sx={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 1.5,
                                    mt: 2,
                                    p: 1,
                                    borderRadius: 1,
                                    border: '1px solid',
                                    borderColor: usbMode ? '#4caf50' : '#333',
                                    bgcolor: usbMode ? 'rgba(76,175,80,0.08)' : 'transparent',
                                    cursor: selectedCameraId ? 'pointer' : 'not-allowed',
                                    opacity: selectedCameraId ? 1 : 0.4,
                                    transition: 'all 0.2s',
                                    '&:hover': {
                                        borderColor: usbMode ? '#66bb6a' : '#555',
                                        bgcolor: usbMode ? 'rgba(76,175,80,0.12)' : 'rgba(255,255,255,0.03)',
                                    },
                                }}
                            >
                                {usbMode ? (
                                    <UsbIcon sx={{ fontSize: 18, color: '#4caf50' }} />
                                ) : (
                                    <VideocamIcon sx={{ fontSize: 18, color: '#888' }} />
                                )}
                                <Box sx={{ flex: 1 }}>
                                    <Typography variant="body2" sx={{ color: '#ccc', fontSize: '0.8rem', fontWeight: 500 }}>
                                        USB Camera Mode
                                    </Typography>
                                    {usbMode && (
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                            <StatusDotSmall $color={STATUS_DOT[connectionStatus]} />
                                            <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem' }}>
                                                {connectionStatus === 'connected'
                                                    ? 'Connected'
                                                    : connectionStatus === 'connecting'
                                                      ? 'Connecting...'
                                                      : connectionStatus === 'error'
                                                        ? 'Error'
                                                        : 'Disconnected'}
                                            </Typography>
                                        </Box>
                                    )}
                                </Box>
                            </Box>
                        </Tooltip>
                    </Box>
                </Fade>

                {/* Gear icon button */}
                <IconButton
                    onClick={() => setSettingsOpen((prev) => !prev)}
                    sx={{
                        bgcolor: 'rgba(255,255,255,0.05)',
                        border: '1px solid #333',
                        color: '#666',
                        '&:hover': {
                            bgcolor: 'rgba(255,255,255,0.1)',
                            color: '#aaa',
                        },
                    }}
                >
                    <SettingsIcon />
                </IconButton>
            </Box>
        </Box>
    );
};
