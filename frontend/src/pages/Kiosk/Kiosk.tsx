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
    Button,
    Chip,
    CircularProgress,
    useMediaQuery,
    useTheme,
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
    HelpOutline as HelpOutlineIcon,
} from '@mui/icons-material';
import { format } from 'date-fns';

import { camerasApi } from '@/api/cameras';
import { eventsApi } from '@/api/events';
import { cvServiceApi } from '@/api/cvService';
import { useLanguage } from '@/i18n/LanguageContext';

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
    membership_end_date: string | null;
}

interface WsStatusMessage {
    type: 'status' | 'ping';
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
type RecognitionState = 'idle' | 'verifying' | 'granted' | 'membership_denied' | 'unknown_denied';
type DenialCategory = 'membership' | 'unknown';

// How long the transient "Verifying identity..." beat is shown before revealing
// the final granted/denied result. There is no backend "detecting" event —
// this is purely a client-side pacing device so the kiosk never feels frozen.
const VERIFYING_DURATION_MS = 500;
const RESULT_RESET_DELAY_MS = 3000;

// ---------------------------------------------------------------------------
// Denial reason classification
// ---------------------------------------------------------------------------

// denial_reason values that mean "we don't know who this is" — never show a
// name for these, and never imply a membership problem exists.
const UNKNOWN_DENIAL_REASONS = new Set(['unknown_face', 'low_confidence', 'member_not_found']);

function classifyDenial(reason: string | null | undefined): DenialCategory {
    if (reason && UNKNOWN_DENIAL_REASONS.has(reason)) return 'unknown';
    return 'membership';
}

type KioskTranslations = ReturnType<typeof useLanguage>['t'];

const MEMBERSHIP_REASON_KEY: Record<string, keyof KioskTranslations['kiosk']> = {
    no_active_membership: 'reasonNoActiveMembership',
    expired_membership: 'reasonExpiredMembership',
    suspended_membership: 'reasonSuspendedMembership',
    membership_not_started: 'reasonMembershipNotStarted',
    access_day_restriction: 'reasonAccessDayRestriction',
    access_time_restriction: 'reasonAccessTimeRestriction',
    access_location_restriction: 'reasonAccessLocationRestriction',
};

function humanizeDenialReason(reason: string | null, t: KioskTranslations): string {
    if (!reason) return t.kiosk.reasonGeneric;
    const key = MEMBERSHIP_REASON_KEY[reason];
    if (key) return t.kiosk[key];
    const suffixMatch = reason.match(/^member(?:ship)?_(.+)$/);
    if (suffixMatch) {
        return `${t.kiosk.reasonGenericPrefix} ${suffixMatch[1].replace(/_/g, ' ')}`;
    }
    return t.kiosk.reasonGeneric;
}

// ---------------------------------------------------------------------------
// Color tokens
// ---------------------------------------------------------------------------

const COLORS = {
    background: '#090A0B',
    surface: '#14161A',
    primary: '#1D6EFF',
    accent: '#00D4FF',
    success: '#29CC6A',
    warning: '#FFB648',
    danger: '#FF5B5B',
    text: '#FFFFFF',
    secondaryText: '#9AA3AF',
};

// ---------------------------------------------------------------------------
// Keyframe Animations
// ---------------------------------------------------------------------------

const pulseGlow = (color: string) => keyframes`
  0% { box-shadow: 0 0 18px 4px ${alpha(color, 0.3)}; }
  50% { box-shadow: 0 0 48px 14px ${alpha(color, 0.55)}; }
  100% { box-shadow: 0 0 18px 4px ${alpha(color, 0.3)}; }
`;

const pulseGreen = pulseGlow(COLORS.success);
const pulseWarning = pulseGlow(COLORS.warning);
const pulseDanger = pulseGlow(COLORS.danger);
const pulseAccent = pulseGlow(COLORS.accent);

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

const scanSweep = keyframes`
  0% { top: 8%; opacity: 0; }
  15% { opacity: 1; }
  85% { opacity: 1; }
  100% { top: 88%; opacity: 0; }
`;

// ---------------------------------------------------------------------------
// Styled Components
// ---------------------------------------------------------------------------

const STATE_BORDER_COLOR: Record<RecognitionState, string> = {
    idle: alpha(COLORS.text, 0.12),
    verifying: COLORS.accent,
    granted: COLORS.success,
    membership_denied: COLORS.warning,
    unknown_denied: COLORS.danger,
};

const STATE_ANIMATION: Record<RecognitionState, string> = {
    idle: 'none',
    verifying: `${pulseAccent} 1.1s ease-in-out infinite`,
    granted: `${pulseGreen} 1.4s ease-in-out 2`,
    membership_denied: `${pulseWarning} 1.8s ease-in-out 1`,
    unknown_denied: `${pulseDanger} 1.8s ease-in-out 1`,
};

const CameraContainer = styled('div')<{
    $state: RecognitionState;
}>(({ $state }) => ({
    position: 'relative',
    width: '100%',
    maxWidth: 460,
    aspectRatio: '4 / 5',
    borderRadius: 28,
    overflow: 'hidden',
    backgroundColor: '#000',
    border: '2px solid',
    borderColor: STATE_BORDER_COLOR[$state],
    transition: 'border-color 0.4s ease, box-shadow 0.4s ease',
    animation: STATE_ANIMATION[$state],
}));

// Purely decorative face-guide overlay. Not tied to real face coordinates —
// the bbox canvas (USB mode) already draws the true detection box.
const GuideFrame = styled('div')<{ $verifying: boolean }>(({ $verifying }) => ({
    position: 'absolute',
    top: '9%',
    left: '13%',
    right: '13%',
    bottom: '15%',
    borderRadius: '50%',
    pointerEvents: 'none',
    border: `1.5px solid ${alpha(COLORS.accent, $verifying ? 0.55 : 0.22)}`,
    transition: 'border-color 0.4s ease',
    animation: $verifying ? 'none' : `${breathe} 2.6s ease-in-out infinite`,
}));

const GuideCorner = styled('span')<{ $pos: 'tl' | 'tr' | 'bl' | 'br' }>(({ $pos }) => {
    const base = {
        position: 'absolute' as const,
        width: 22,
        height: 22,
        borderColor: COLORS.accent,
        pointerEvents: 'none' as const,
        opacity: 0.7,
    };
    switch ($pos) {
        case 'tl':
            return { ...base, top: '6%', left: '9%', borderTop: '2px solid', borderLeft: '2px solid', borderTopLeftRadius: 8 };
        case 'tr':
            return { ...base, top: '6%', right: '9%', borderTop: '2px solid', borderRight: '2px solid', borderTopRightRadius: 8 };
        case 'bl':
            return { ...base, bottom: '12%', left: '9%', borderBottom: '2px solid', borderLeft: '2px solid', borderBottomLeftRadius: 8 };
        case 'br':
            return { ...base, bottom: '12%', right: '9%', borderBottom: '2px solid', borderRight: '2px solid', borderBottomRightRadius: 8 };
        default:
            return base;
    }
});

const ScanSweepLine = styled('div')({
    position: 'absolute',
    left: '11%',
    right: '11%',
    height: 2,
    borderRadius: 2,
    background: `linear-gradient(90deg, transparent, ${alpha(COLORS.accent, 0.9)}, transparent)`,
    boxShadow: `0 0 12px 2px ${alpha(COLORS.accent, 0.6)}`,
    animation: `${scanSweep} 1.2s ease-in-out infinite`,
    pointerEvents: 'none',
});

const StatusDotSmall = styled('span')<{ $color: 'green' | 'red' | 'yellow' | 'accent' }>(({ $color }) => ({
    display: 'inline-block',
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor:
        $color === 'green' ? COLORS.success
            : $color === 'red' ? COLORS.danger
                : $color === 'accent' ? COLORS.accent
                    : COLORS.warning,
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
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const [searchParams, setSearchParams] = useSearchParams();
    const urlCameraId = searchParams.get('cameraId');
    const [selectedCameraId, setSelectedCameraId] = useState<string>(urlCameraId || '');

    const [usbMode, setUsbMode] = useState(false);

    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
    const [localEvents, setLocalEvents] = useState<LocalEvent[]>([]);
    const [latestRecognition, setLatestRecognition] = useState<WsRecognitionResult | null>(null);

    const [recognitionState, setRecognitionState] = useState<RecognitionState>('idle');
    const [streamError, setStreamError] = useState(false);
    const [recognizedName, setRecognizedName] = useState<string>('');
    const [denialReason, setDenialReason] = useState<string | null>(null);
    const [membershipExpiry, setMembershipExpiry] = useState<string | null>(null);
    const [currentTime, setCurrentTime] = useState(new Date());

    const [settingsOpen, setSettingsOpen] = useState(false);

    const verifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Identifies the recognition event currently being displayed (verifying
    // or revealed), so repeated per-frame WS messages for the same person
    // (the CV service re-sends "recognition" on every processed frame, up to
    // 5/s, for as long as they stand in front of the camera) refresh the
    // auto-dismiss timer instead of restarting the verifying animation.
    const activeResultKeyRef = useRef<string | null>(null);

    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    useEffect(() => {
        const interval = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(interval);
    }, []);

    const { data: camerasData, isLoading: loadingCameras } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras(),
    });

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
        activeResultKeyRef.current = null;
        setRecognitionState('idle');
        setRecognizedName('');
        setDenialReason(null);
        setMembershipExpiry(null);
    }, []);

    useEffect(() => {
        if (!latestRecognition || !latestRecognition.member_name) return;

        const { access_granted, denial_reason, member_name, membership_end_date, member_id } = latestRecognition;
        const resultKey = `${member_id ?? 'unknown'}:${access_granted}`;

        // Same person/outcome as the frame we're already showing — just keep
        // it on screen instead of restarting the verifying beat. Without this,
        // a face held steady in frame re-triggers this effect every ~200ms
        // (5fps capture) and the 500ms verifying timer below would never win
        // the race to actually fire.
        if (activeResultKeyRef.current === resultKey) {
            if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
            resetTimerRef.current = setTimeout(resetRecognition, RESULT_RESET_DELAY_MS);
            return;
        }
        activeResultKeyRef.current = resultKey;

        if (verifyTimerRef.current) clearTimeout(verifyTimerRef.current);
        if (resetTimerRef.current) clearTimeout(resetTimerRef.current);

        // The CV service only ever emits the final recognition result — there is
        // no separate "face detected, still verifying" backend event. We
        // simulate that beat here so the kiosk doesn't jump-cut straight to the
        // result, which would read as jarring rather than confident.
        setRecognitionState('verifying');

        verifyTimerRef.current = setTimeout(() => {
            setRecognizedName(member_name);
            setMembershipExpiry(membership_end_date || null);

            if (access_granted) {
                setRecognitionState('granted');
            } else {
                setDenialReason(denial_reason || null);
                setRecognitionState(classifyDenial(denial_reason) === 'unknown' ? 'unknown_denied' : 'membership_denied');
            }

            resetTimerRef.current = setTimeout(() => {
                resetRecognition();
            }, RESULT_RESET_DELAY_MS);
        }, VERIFYING_DURATION_MS);

        return () => {
            if (verifyTimerRef.current) clearTimeout(verifyTimerRef.current);
            if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
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
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
            });
            streamRef.current = stream;

            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
            }

            const wsUrl = cvServiceApi.getWebSocketUrl(cameraId);
            const ws = new WebSocket(wsUrl);
            ws.binaryType = 'arraybuffer';
            wsRef.current = ws;

            ws.onopen = () => { setConnectionStatus('connected'); };

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

            ws.onerror = () => { setConnectionStatus('error'); };
            ws.onclose = () => { setConnectionStatus('disconnected'); };

            captureIntervalRef.current = setInterval(() => {
                if (ws.readyState !== WebSocket.OPEN) return;
                if (!videoRef.current || !canvasRef.current) return;

                const video = videoRef.current;
                const canvas = canvasRef.current;
                if (video.readyState < 2) return;

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
        const color = granted
            ? COLORS.success
            : classifyDenial(latestRecognition.denial_reason) === 'unknown'
                ? COLORS.danger
                : COLORS.warning;
        const label = granted
            ? `ACCESS GRANTED - ${latestRecognition.member_name} (${Math.round(latestRecognition.confidence * 100)}%)`
            : `ACCESS DENIED - ${latestRecognition.member_name || 'Unknown'} (${Math.round(latestRecognition.confidence * 100)}%)`;

        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);

        ctx.font = window.innerWidth < 600 ? 'bold 12px monospace' : 'bold 16px monospace';
        const textWidth = ctx.measureText(label).width;
        const labelY = y > 30 ? y - 8 : y + h + 24;
        ctx.fillStyle = alpha(color, 0.85);
        ctx.fillRect(x, labelY - 18, textWidth + 16, 24);

        ctx.fillStyle = '#ffffff';
        ctx.fillText(label, x + 8, labelY);
    }, [latestRecognition, usbMode]);

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
        setStreamError(false);
    }, [usbMode, selectedCameraId, stopUsbCamera, startUsbCamera]);

    useEffect(() => {
        return () => { stopUsbCamera(); };
    }, [stopUsbCamera]);

    useEffect(() => {
        if (usbMode && selectedCameraId) {
            setLocalEvents([]);
            startUsbCamera(selectedCameraId);
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
        setStreamError(false);
    }, [selectedCameraId]);

    const handleCameraChange = (e: any) => {
        const id = e.target.value;
        setSelectedCameraId(id);
        setSearchParams({ cameraId: id });
    };

    const displayEvents = usbMode ? localEvents : remoteEvents;
    const recentCheckins = displayEvents.slice(0, 3);
    const showGuide = recognitionState === 'idle' || recognitionState === 'verifying';

    // -----------------------------------------------------------------------
    // Render
    // -----------------------------------------------------------------------

    return (
        <Box
            sx={{
                height: '100dvh',
                width: '100vw',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                background: `linear-gradient(180deg, ${COLORS.background} 0%, ${COLORS.surface} 100%)`,
                color: COLORS.text,
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* ---- TOP BAR ---- */}
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
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <img
                        src="/logo.png"
                        alt="PowerHouse Gym"
                        style={{ height: isMobile ? 28 : 36, width: 'auto' }}
                        onError={(e) => {
                            (e.target as HTMLImageElement).style.display = 'none';
                        }}
                    />
                    <Typography
                        variant="h5"
                        fontWeight={900}
                        sx={{
                            letterSpacing: '0.05em',
                            background: `linear-gradient(135deg, ${COLORS.text} 0%, ${COLORS.secondaryText} 100%)`,
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            fontSize: { xs: '1.1rem', md: '1.5rem' },
                        }}
                    >
                        POWERHOUSE GYM
                    </Typography>
                </Box>

                <Typography
                    variant="h4"
                    fontWeight={300}
                    sx={{
                        color: alpha(COLORS.text, 0.6),
                        fontVariantNumeric: 'tabular-nums',
                        letterSpacing: '0.02em',
                    }}
                >
                    {format(currentTime, 'h:mm a')}
                </Typography>
            </Box>

            {/* ---- MAIN CONTENT ---- */}
            <Box
                sx={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '100%',
                    px: 3,
                    pt: 8,
                    pb: 6,
                }}
            >
                {/* Recognition Overlay */}
                <Fade in={recognitionState !== 'idle'} timeout={400}>
                    <Box
                        sx={{
                            textAlign: 'center',
                            mb: 2.5,
                            minHeight: { xs: 50, sm: 70 },
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                        }}
                    >
                        {recognitionState === 'verifying' && (
                            <Box sx={{ animation: `${fadeIn} 0.25s ease-out`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                                <CircularProgress size={isMobile ? 26 : 32} thickness={4} sx={{ color: COLORS.accent }} />
                                <Typography variant={isMobile ? "h6" : "h5"} fontWeight={700} sx={{ color: COLORS.accent, letterSpacing: '0.02em' }}>
                                    {t.kiosk.verifying}
                                </Typography>
                            </Box>
                        )}
                        {recognitionState === 'granted' && (
                            <Box sx={{ animation: `${slideDown} 0.4s ease-out`, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                <CheckCircleIcon sx={{ fontSize: { xs: 36, sm: 48 }, color: COLORS.success, mb: 0.5 }} />
                                <Typography variant={isMobile ? "h5" : "h4"} fontWeight={800} sx={{ color: COLORS.success, letterSpacing: '0.02em', textShadow: `0 0 20px ${alpha(COLORS.success, 0.4)}` }}>
                                    {t.kiosk.welcomeBack}
                                </Typography>
                                <Typography variant={isMobile ? "h6" : "h5"} fontWeight={600} sx={{ color: alpha(COLORS.text, 0.9), mt: 0.5 }}>
                                    {recognizedName}
                                </Typography>
                                {membershipExpiry && (
                                    <Typography variant="body2" sx={{ color: alpha(COLORS.success, 0.8), mt: 0.5, fontSize: { xs: '0.8rem', sm: '0.9rem' }, fontWeight: 400 }}>
                                        {t.kiosk.membershipValidUntil}: {new Date(membershipExpiry + 'T12:00:00').toLocaleDateString('es-CO', { day: 'numeric', month: 'long', year: 'numeric' })}
                                    </Typography>
                                )}
                                <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 0.75 }}>
                                    {t.kiosk.doorOpening}
                                </Typography>
                            </Box>
                        )}
                        {recognitionState === 'membership_denied' && (
                            <Box sx={{ animation: `${slideDown} 0.4s ease-out`, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                <WarningAmberIcon sx={{ fontSize: { xs: 36, sm: 48 }, color: COLORS.warning, mb: 0.5 }} />
                                <Typography variant={isMobile ? "h5" : "h4"} fontWeight={800} sx={{ color: COLORS.warning, letterSpacing: '0.02em', textShadow: `0 0 20px ${alpha(COLORS.warning, 0.35)}` }}>
                                    {t.kiosk.membershipIssue}
                                </Typography>
                                <Typography variant={isMobile ? "h6" : "h5"} fontWeight={600} sx={{ color: alpha(COLORS.text, 0.9), mt: 0.5 }}>
                                    {recognizedName}
                                </Typography>
                                <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 0.5 }}>
                                    {humanizeDenialReason(denialReason, t)}
                                </Typography>
                                <Typography variant="body2" sx={{ color: alpha(COLORS.text, 0.4), mt: 0.25 }}>
                                    {t.kiosk.pleaseVisitReception}
                                </Typography>
                            </Box>
                        )}
                        {recognitionState === 'unknown_denied' && (
                            <Box sx={{ animation: `${slideDown} 0.4s ease-out`, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                                <HelpOutlineIcon sx={{ fontSize: { xs: 36, sm: 48 }, color: COLORS.danger, mb: 0.5 }} />
                                <Typography variant={isMobile ? "h5" : "h4"} fontWeight={800} sx={{ color: COLORS.danger, letterSpacing: '0.02em', textShadow: `0 0 20px ${alpha(COLORS.danger, 0.3)}` }}>
                                    {t.kiosk.unknownTitle}
                                </Typography>
                                <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 0.75, maxWidth: 320 }}>
                                    {t.kiosk.unknownSubtitle}
                                </Typography>
                            </Box>
                        )}
                    </Box>
                </Fade>

                {/* Camera Feed */}
                <CameraContainer $state={recognitionState}>
                    {selectedCameraId ? (
                        usbMode ? (
                            <>
                                <video ref={videoRef} autoPlay playsInline muted style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
                                <canvas ref={overlayCanvasRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }} />
                                <canvas ref={canvasRef} style={{ display: 'none' }} />
                                {connectionStatus === 'error' && (
                                    <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', bgcolor: alpha(COLORS.background, 0.92), gap: 0.5, px: 3 }}>
                                        <WifiOffIcon sx={{ fontSize: 44, color: COLORS.secondaryText, mb: 1, animation: `${breathe} 2s ease-in-out infinite` }} />
                                        <Typography sx={{ color: COLORS.text, fontWeight: 600, textAlign: 'center' }}>{t.kiosk.cameraReconnecting}</Typography>
                                        <Typography variant="body2" sx={{ color: COLORS.secondaryText, textAlign: 'center' }}>{t.kiosk.cameraReconnectingDetail}</Typography>
                                    </Box>
                                )}
                            </>
                        ) : (
                            <>
                            <img
                                src={cvServiceApi.getStreamUrl(selectedCameraId)}
                                alt="Live Camera Feed"
                                style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' }}
                                onError={() => setStreamError(true)}
                            />
                            {streamError && (
                                <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', bgcolor: alpha(COLORS.background, 0.95), px: 3 }}>
                                    <VideocamOffIcon sx={{ fontSize: 44, color: COLORS.secondaryText, mb: 1, animation: `${breathe} 2s ease-in-out infinite` }} />
                                    <Typography sx={{ color: COLORS.text, fontWeight: 600, fontSize: '1.05rem', textAlign: 'center' }}>
                                        {t.kiosk.cameraReconnecting}
                                    </Typography>
                                    <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 1, maxWidth: 340, textAlign: 'center' }}>
                                        {t.kiosk.cameraReconnectingDetail}
                                    </Typography>
                                    <Button
                                        variant="outlined"
                                        size="small"
                                        sx={{ mt: 2, color: COLORS.accent, borderColor: alpha(COLORS.accent, 0.5), '&:hover': { borderColor: COLORS.accent, bgcolor: alpha(COLORS.accent, 0.08) } }}
                                        onClick={() => setStreamError(false)}
                                    >
                                        {t.kiosk.retry}
                                    </Button>
                                </Box>
                            )}
                            </>
                        )
                    ) : (
                        <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', bgcolor: COLORS.surface }}>
                            <VideocamOffIcon sx={{ fontSize: 56, color: alpha(COLORS.text, 0.15), mb: 1 }} />
                            <Typography sx={{ color: COLORS.secondaryText, fontWeight: 500 }}>{t.cameras.selectCameraStart}</Typography>
                            <Typography variant="caption" sx={{ color: alpha(COLORS.secondaryText, 0.6), mt: 0.5 }}>{t.cameras.openSettings}</Typography>
                        </Box>
                    )}

                    {/* Decorative face-guide overlay: idle breathing ring / verifying scan sweep */}
                    {!!selectedCameraId && !streamError && connectionStatus !== 'error' && (
                        <Fade in={showGuide} timeout={300}>
                            <Box sx={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
                                <GuideFrame $verifying={recognitionState === 'verifying'} />
                                <GuideCorner $pos="tl" />
                                <GuideCorner $pos="tr" />
                                <GuideCorner $pos="bl" />
                                <GuideCorner $pos="br" />
                                {recognitionState === 'verifying' && <ScanSweepLine />}
                            </Box>
                        </Fade>
                    )}

                    {usbMode && connectionStatus === 'connected' && recognitionState === 'idle' && (
                        <Box sx={{ position: 'absolute', bottom: 12, left: '50%', transform: 'translateX(-50%)', display: 'flex', alignItems: 'center', gap: 1, bgcolor: alpha('#000', 0.6), px: 2, py: 0.75, borderRadius: 3, backdropFilter: 'blur(8px)' }}>
                            <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: COLORS.accent, animation: `${breathe} 1.5s ease-in-out infinite` }} />
                            <Typography variant="caption" sx={{ color: alpha(COLORS.text, 0.7) }}>{t.kiosk.scanning}</Typography>
                        </Box>
                    )}
                </CameraContainer>

                <Fade in={recognitionState === 'idle' && !!selectedCameraId}>
                    <Box sx={{ mt: 2.5, textAlign: 'center', animation: `${fadeIn} 0.6s ease-out` }}>
                        <Typography variant="body1" sx={{ color: alpha(COLORS.text, 0.35), fontWeight: 400 }}>
                            {t.kiosk.faceCamera}
                        </Typography>
                    </Box>
                </Fade>
            </Box>

            {/* ---- BOTTOM BAR ---- */}
            <Box sx={{ position: 'absolute', bottom: 0, left: 0, right: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: { xs: 1, sm: 3 }, px: { xs: 2, sm: 4 }, py: { xs: 1, sm: 2 }, flexWrap: 'wrap', zIndex: 10 }}>
                {recentCheckins.map((event: any) => {
                    const denied = !event.access_granted;
                    const dotColor = !denied ? 'green' : classifyDenial(event.denial_reason) === 'unknown' ? 'red' : 'yellow';
                    const borderColor = !denied
                        ? alpha(COLORS.success, 0.2)
                        : classifyDenial(event.denial_reason) === 'unknown'
                            ? alpha(COLORS.danger, 0.2)
                            : alpha(COLORS.warning, 0.2);
                    const iconColor = !denied
                        ? COLORS.success
                        : classifyDenial(event.denial_reason) === 'unknown'
                            ? COLORS.danger
                            : COLORS.warning;
                    return (
                        <Chip
                            key={event.id}
                            size="small"
                            sx={{
                                bgcolor: alpha(COLORS.text, 0.05),
                                border: '1px solid',
                                borderColor,
                                color: alpha(COLORS.text, 0.5),
                                fontSize: '0.75rem',
                                '& .MuiChip-icon': { color: iconColor },
                                '& .MuiChip-label': { display: 'flex', alignItems: 'center', gap: 0.5 },
                            }}
                            icon={<StatusDotSmall $color={dotColor} />}
                            label={`${event.member_name} · ${format(new Date(event.timestamp), 'h:mm a')}`}
                        />
                    );
                })}
            </Box>

            {/* ---- SETTINGS PANEL ---- */}
            <Box sx={{ position: 'absolute', bottom: 16, right: 16, zIndex: 20 }}>
                <Fade in={settingsOpen} timeout={200}>
                    <Box sx={{ display: settingsOpen ? 'block' : 'none', bgcolor: alpha(COLORS.surface, 0.95), backdropFilter: 'blur(12px)', border: '1px solid', borderColor: alpha(COLORS.text, 0.1), borderRadius: 2, p: 2.5, mb: 1, minWidth: { xs: 220, sm: 260 }, animation: settingsOpen ? `${fadeIn} 0.2s ease-out` : 'none' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: -1 }}>
                            <IconButton size="small" onClick={() => setSettingsOpen(false)}>
                                <CloseIcon sx={{ fontSize: 18, color: COLORS.secondaryText }} />
                            </IconButton>
                        </Box>

                        <Typography variant="caption" sx={{ color: COLORS.secondaryText, mb: 1, display: 'block' }}>
                            {t.kiosk.kioskSettings}
                        </Typography>

                        <FormControl size="small" fullWidth sx={{ mt: 1 }}>
                            <InputLabel id="cam-select-label" sx={{ color: COLORS.secondaryText, fontSize: '0.8rem' }}>
                                {t.kiosk.camera}
                            </InputLabel>
                            <Select
                                labelId="cam-select-label"
                                value={selectedCameraId}
                                label={t.kiosk.camera}
                                onChange={handleCameraChange}
                                sx={{ bgcolor: alpha(COLORS.background, 0.6), color: COLORS.text, fontSize: '0.85rem', '.MuiOutlinedInput-notchedOutline': { borderColor: alpha(COLORS.text, 0.15) }, '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: alpha(COLORS.text, 0.3) } }}
                            >
                                {loadingCameras ? (
                                    <MenuItem disabled>{t.common.loading}</MenuItem>
                                ) : (
                                    camerasData?.map((cam: any) => (
                                        <MenuItem key={cam.id} value={cam.id}>{cam.name}</MenuItem>
                                    ))
                                )}
                                {!loadingCameras && (!camerasData || camerasData.length === 0) && (
                                    <MenuItem disabled>{t.kiosk.noCamerasFound}</MenuItem>
                                )}
                            </Select>
                        </FormControl>

                        <Tooltip title={usbMode ? t.kiosk.switchToRemote : t.kiosk.switchToUsb}>
                            <Box
                                onClick={selectedCameraId ? handleUsbToggle : undefined}
                                sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mt: 2, p: 1, borderRadius: 1, border: '1px solid', borderColor: usbMode ? COLORS.success : alpha(COLORS.text, 0.15), bgcolor: usbMode ? alpha(COLORS.success, 0.08) : 'transparent', cursor: selectedCameraId ? 'pointer' : 'not-allowed', opacity: selectedCameraId ? 1 : 0.4, transition: 'all 0.2s', '&:hover': { borderColor: usbMode ? COLORS.success : alpha(COLORS.text, 0.3), bgcolor: usbMode ? alpha(COLORS.success, 0.12) : alpha(COLORS.text, 0.03) } }}
                            >
                                {usbMode ? (
                                    <UsbIcon sx={{ fontSize: 18, color: COLORS.success }} />
                                ) : (
                                    <VideocamIcon sx={{ fontSize: 18, color: COLORS.secondaryText }} />
                                )}
                                <Box sx={{ flex: 1 }}>
                                    <Typography variant="body2" sx={{ color: alpha(COLORS.text, 0.8), fontSize: '0.8rem', fontWeight: 500 }}>
                                        {t.kiosk.usbCameraMode}
                                    </Typography>
                                    {usbMode && (
                                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                            <StatusDotSmall $color={STATUS_DOT[connectionStatus]} />
                                            <Typography variant="caption" sx={{ color: COLORS.secondaryText, fontSize: '0.7rem' }}>
                                                {connectionStatus === 'connected' ? t.kiosk.connected
                                                    : connectionStatus === 'connecting' ? t.kiosk.connecting
                                                    : connectionStatus === 'error' ? t.kiosk.error
                                                    : t.kiosk.disconnected}
                                            </Typography>
                                        </Box>
                                    )}
                                </Box>
                            </Box>
                        </Tooltip>
                    </Box>
                </Fade>

                <IconButton
                    onClick={() => setSettingsOpen((prev) => !prev)}
                    sx={{ bgcolor: alpha(COLORS.text, 0.05), border: '1px solid', borderColor: alpha(COLORS.text, 0.12), color: COLORS.secondaryText, minWidth: 44, minHeight: 44, '&:hover': { bgcolor: alpha(COLORS.text, 0.1), color: COLORS.text } }}
                >
                    <SettingsIcon />
                </IconButton>
            </Box>
        </Box>
    );
};
