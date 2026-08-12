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
    // Whole days left on the membership. Only populated on a grant; null when
    // the CV service couldn't determine it.
    days_remaining: number | null;
    // Outstanding balance on the membership. Only populated on a grant, and
    // null whenever nothing is owed — a balance NEVER denies entry, it only
    // turns the welcome amber and names the amount.
    amount_due?: number | null;
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
    days_remaining?: number | null;
    amount_due?: number | null;
}

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';
type RecognitionState =
    | 'idle'
    | 'verifying'
    | 'granted'
    | 'granted_expiring'
    | 'granted_payment_due'
    | 'membership_denied'
    | 'unknown_denied';
type DenialCategory = 'membership' | 'unknown';
// States that take over the whole screen to announce an outcome.
type SplashState = Exclude<RecognitionState, 'idle' | 'verifying'>;

// How long the transient "Verifying identity..." beat is shown before revealing
// the final granted/denied result. There is no backend "detecting" event —
// this is purely a client-side pacing device so the kiosk never feels frozen.
const VERIFYING_DURATION_MS = 500;
const RESULT_RESET_DELAY_MS = 3000;

// A granted member with this many days or fewer left still gets in, but the
// splash turns amber and names the day count so they can renew at reception
// before it actually lapses.
const EXPIRY_WARNING_DAYS = 5;

// Formats a balance for the splash. Read from across a lobby, so cents are
// dropped when there are none — "$29" beats "$29.00" at that distance.
function formatAmountDue(amount: number): string {
    return `$${amount.toLocaleString('es-CO', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
    })}`;
}

// An unattended kiosk has nobody to pick a camera for it, so it remembers the
// last one it used and re-claims it after a reload or power cycle.
const CAMERA_STORAGE_KEY = 'kiosk.cameraId';

function readStoredCameraId(): string {
    try {
        return localStorage.getItem(CAMERA_STORAGE_KEY) || '';
    } catch {
        // Storage can be unavailable (private mode, locked-down kiosk
        // browser). Falling back to the camera list is fine.
        return '';
    }
}

function rememberCameraId(cameraId: string): void {
    try {
        localStorage.setItem(CAMERA_STORAGE_KEY, cameraId);
    } catch {
        // Non-fatal: the kiosk still works, it just won't remember.
    }
}

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
    unpaid_membership: 'reasonUnpaidMembership',
    suspended_membership: 'reasonSuspendedMembership',
    membership_not_started: 'reasonMembershipNotStarted',
    access_day_restriction: 'reasonAccessDayRestriction',
    access_time_restriction: 'reasonAccessTimeRestriction',
    access_location_restriction: 'reasonAccessLocationRestriction',
};

// A granted-but-expiring member is still welcomed — the amber styling and the
// day count carry the "renew soon" message, not a scarier headline. The same
// holds for an unpaid balance: the door opened, so the title stays a welcome.
const SPLASH_TITLE_KEY: Record<SplashState, keyof KioskTranslations['kiosk']> = {
    granted: 'welcomeBack',
    granted_expiring: 'welcomeBack',
    granted_payment_due: 'welcomeBack',
    membership_denied: 'membershipIssue',
    unknown_denied: 'unknownTitle',
};

function isSplashState(state: RecognitionState): state is SplashState {
    return state !== 'idle' && state !== 'verifying';
}

// Membership dates arrive as date-only strings. Anchoring at midday avoids the
// UTC-shift that makes a date render as the previous day in western timezones.
function formatExpiryDate(endDate: string): string {
    return new Date(endDate + 'T12:00:00').toLocaleDateString('es-CO', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
    });
}

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

const splashIn = keyframes`
  from { opacity: 0; transform: scale(1.04); }
  to { opacity: 1; transform: scale(1); }
`;

const iconPop = keyframes`
  0% { transform: scale(0); opacity: 0; }
  60% { transform: scale(1.15); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
`;

const resetCountdown = keyframes`
  from { transform: scaleX(1); }
  to { transform: scaleX(0); }
`;

// ---------------------------------------------------------------------------
// Styled Components
// ---------------------------------------------------------------------------

const STATE_BORDER_COLOR: Record<RecognitionState, string> = {
    idle: alpha(COLORS.text, 0.12),
    verifying: COLORS.accent,
    granted: COLORS.success,
    granted_expiring: COLORS.warning,
    granted_payment_due: COLORS.warning,
    membership_denied: COLORS.warning,
    unknown_denied: COLORS.danger,
};

const STATE_ANIMATION: Record<RecognitionState, string> = {
    idle: 'none',
    verifying: `${pulseAccent} 1.1s ease-in-out infinite`,
    granted: `${pulseGreen} 1.4s ease-in-out 2`,
    granted_expiring: `${pulseWarning} 1.4s ease-in-out 2`,
    granted_payment_due: `${pulseWarning} 1.4s ease-in-out 2`,
    membership_denied: `${pulseWarning} 1.8s ease-in-out 1`,
    unknown_denied: `${pulseDanger} 1.8s ease-in-out 1`,
};

// The result splash owns the whole screen, so its palette is what a member
// reads from across the lobby. It answers one question first — did the door
// open? Green and amber mean come in, red means see reception. Icon and
// title then separate the two amber cases and the two red ones.
const SPLASH_ACCENT: Record<SplashState, string> = {
    granted: COLORS.success,
    granted_expiring: COLORS.warning,
    granted_payment_due: COLORS.warning,
    membership_denied: COLORS.danger,
    unknown_denied: COLORS.danger,
};

const SplashOverlay = styled('div')<{ $state: SplashState }>(({ $state }) => {
    const accent = SPLASH_ACCENT[$state];
    return {
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
        padding: 24,
        background: `radial-gradient(ellipse at center, ${alpha(accent, 0.24)} 0%, ${alpha(COLORS.background, 0.88)} 72%)`,
        backdropFilter: 'blur(7px)',
        animation: `${splashIn} 0.35s ease-out`,
        '@media (prefers-reduced-motion: reduce)': { animation: 'none' },
    };
});

const CameraContainer = styled('div')<{
    $state: RecognitionState;
}>(({ $state }) => ({
    position: 'relative',
    width: '100%',
    maxWidth: 1180,
    height: 'min(66dvh, calc(100vw * 0.5625))',
    minHeight: 320,
    aspectRatio: '16 / 9',
    borderRadius: 32,
    overflow: 'hidden',
    backgroundColor: '#000',
    border: '1px solid',
    borderColor: STATE_BORDER_COLOR[$state],
    transition: 'border-color 0.4s ease, box-shadow 0.4s ease',
    animation: STATE_ANIMATION[$state],
    boxShadow: `0 28px 80px ${alpha('#000', 0.58)}, inset 0 0 0 1px ${alpha(COLORS.text, 0.05)}`,
    '@media (orientation: portrait)': {
        width: 'min(92vw, 820px)',
        height: 'min(66dvh, calc(92vw * 1.2))',
        minHeight: 0,
        aspectRatio: '5 / 6',
    },
    '@media (max-height: 800px) and (orientation: landscape)': {
        height: 'min(64dvh, calc(100vw * 0.5625))',
        maxWidth: 'min(1180px, 78vw)',
        minHeight: 300,
    },
    '@media (prefers-reduced-motion: reduce)': { animation: 'none', transition: 'none' },
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
    const [selectedCameraId, setSelectedCameraId] = useState<string>(
        () => urlCameraId || readStoredCameraId()
    );

    // The kiosk drives the camera attached to the machine it runs on, so local
    // camera mode is the default — staff shouldn't have to enable it by hand at
    // every start. ?mode=remote opts back into a server-side RTSP stream.
    const [usbMode, setUsbMode] = useState(() => searchParams.get('mode') !== 'remote');

    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
    const [localEvents, setLocalEvents] = useState<LocalEvent[]>([]);
    const [latestRecognition, setLatestRecognition] = useState<WsRecognitionResult | null>(null);

    const [recognitionState, setRecognitionState] = useState<RecognitionState>('idle');
    const [streamError, setStreamError] = useState(false);
    const [recognizedName, setRecognizedName] = useState<string>('');
    const [denialReason, setDenialReason] = useState<string | null>(null);
    const [membershipExpiry, setMembershipExpiry] = useState<string | null>(null);
    const [daysRemaining, setDaysRemaining] = useState<number | null>(null);
    const [amountDue, setAmountDue] = useState<number | null>(null);
    const [currentTime, setCurrentTime] = useState(new Date());

    const [settingsOpen, setSettingsOpen] = useState(false);

    const verifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const resetTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    // Identifies the recognition event currently being displayed (verifying
    // or revealed), so repeated per-frame WS messages for the same person
    // (the CV service re-sends "recognition" on every processed frame, up to
    // 5/s, for as long as they stand in front of the camera) cannot restart
    // either the reveal or fixed auto-dismiss deadline.
    const activeResultKeyRef = useRef<string | null>(null);

    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
    // In-flight guard: startUsbCamera does its real setup (MediaStream/WebSocket/
    // interval assignment into the refs above) only after the async
    // getUserMedia() resolves. If the function is invoked again (Retry click,
    // rapid camera switch, etc.) while a previous call's getUserMedia is still
    // pending, stopUsbCamera() finds nothing to clean up yet, and both calls'
    // async work can later stomp each other's ref assignments — leaking an open
    // WebSocket + running capture interval + live camera stream. Make a second
    // concurrent call a no-op instead.
    const startingUsbCameraRef = useRef(false);
    // Nobody is standing at an unattended kiosk to click "Reconnect", so a
    // dropped WebSocket used to leave the terminal dead until staff noticed
    // and reloaded the page. These drive an automatic, backed-off recovery.
    const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const reconnectAttemptsRef = useRef(0);
    // startUsbCamera and scheduleReconnect call each other; the ref breaks the
    // cycle without making either callback depend on the other's identity.
    const startUsbCameraRef = useRef<((cameraId: string) => void) | null>(null);

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
        setDaysRemaining(null);
        setAmountDue(null);
    }, []);

    useEffect(() => {
        if (!latestRecognition || !latestRecognition.member_name) {
            // No active recognition (e.g. the USB camera was just stopped —
            // stopUsbCamera() sets latestRecognition to null). Cancel any
            // pending reveal/dismiss timers and make sure the UI doesn't stay
            // frozen on whatever state was last shown.
            if (verifyTimerRef.current) {
                clearTimeout(verifyTimerRef.current);
                verifyTimerRef.current = null;
            }
            if (resetTimerRef.current) {
                clearTimeout(resetTimerRef.current);
                resetTimerRef.current = null;
            }
            if (activeResultKeyRef.current !== null) {
                resetRecognition();
            }
            return;
        }

        const {
            access_granted,
            denial_reason,
            member_name,
            membership_end_date,
            member_id,
            days_remaining,
            amount_due,
        } = latestRecognition;
        const resultKey = `${member_id ?? 'unknown'}:${access_granted}`;

        // Same person/outcome as the frame we're already showing — just keep
        // it on screen instead of restarting the verifying beat. Without this,
        // a face held steady in frame re-triggers this effect every ~200ms
        // (5fps capture) and the 500ms verifying timer below would never win
        // the race to actually fire.
        if (activeResultKeyRef.current === resultKey) {
            // Still verifying (verifyTimerRef is still pending): let it keep
            // counting down uninterrupted. Once revealed, the fixed reset
            // deadline also remains untouched so a person standing still can
            // never block the queue. This effect intentionally does NOT
            // return a cleanup function that clears verifyTimerRef, because
            // that cleanup would otherwise re-run (and cancel the pending
            // reveal) on every duplicate frame — which is exactly what used
            // to leave the kiosk stuck showing "verifying" forever.
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
            verifyTimerRef.current = null;
            setRecognizedName(member_name);
            setMembershipExpiry(membership_end_date || null);
            setDaysRemaining(days_remaining ?? null);
            setAmountDue(amount_due ?? null);

            if (access_granted) {
                // Still a grant — the door opens either way. The amber variants
                // only add a nudge to settle up or renew. `0` is a real warning
                // value for days (the final valid day), so test the null-ness
                // separately.
                const expiringSoon =
                    days_remaining !== null &&
                    days_remaining !== undefined &&
                    days_remaining <= EXPIRY_WARNING_DAYS;
                // A balance on a GRANT can only be a partial payment — a member
                // who paid nothing is denied upstream by the CV payment gate and
                // never reaches this branch. The balance outranks the renewal
                // nudge (money owed is what reception acts on today) and the
                // payment splash still shows the day count when both apply.
                const owesMoney = amount_due !== null && amount_due !== undefined && amount_due > 0;
                if (owesMoney) {
                    setRecognitionState('granted_payment_due');
                } else {
                    setRecognitionState(expiringSoon ? 'granted_expiring' : 'granted');
                }
            } else {
                setDenialReason(denial_reason || null);
                setRecognitionState(classifyDenial(denial_reason) === 'unknown' ? 'unknown_denied' : 'membership_denied');
            }

            if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
            resetTimerRef.current = setTimeout(() => {
                resetRecognition();
            }, RESULT_RESET_DELAY_MS);
        }, VERIFYING_DURATION_MS);
    }, [latestRecognition, resetRecognition]);

    // Unmount-only teardown for the recognition timers. The effect above
    // manages verifyTimerRef/resetTimerRef explicitly across repeated
    // same-person frames instead of clearing them on every re-render (see
    // comment above) — this dedicated effect is the only place they get
    // cancelled on unmount.
    useEffect(() => {
        return () => {
            if (verifyTimerRef.current) clearTimeout(verifyTimerRef.current);
            if (resetTimerRef.current) clearTimeout(resetTimerRef.current);
        };
    }, []);

    // -----------------------------------------------------------------------
    // USB Camera Lifecycle
    // -----------------------------------------------------------------------

    const cancelReconnect = useCallback(() => {
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
    }, []);

    const scheduleReconnect = useCallback((cameraId: string) => {
        // One pending attempt at a time: onclose and the getUserMedia catch
        // can both fire for the same failure.
        if (reconnectTimerRef.current) return;
        reconnectAttemptsRef.current += 1;
        // Exponential backoff capped at 10s. The kiosk must keep trying
        // indefinitely — a drop it cannot recover from is an outage nobody
        // is watching — without hammering a service that is down.
        const delay = Math.min(1000 * 2 ** (reconnectAttemptsRef.current - 1), 10000);
        reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null;
            startUsbCameraRef.current?.(cameraId);
        }, delay);
    }, []);

    const stopUsbCamera = useCallback(() => {
        cancelReconnect();
        if (captureIntervalRef.current) {
            clearInterval(captureIntervalRef.current);
            captureIntervalRef.current = null;
        }
        if (wsRef.current) {
            // Clear the ref BEFORE close(): onclose fires synchronously, and
            // it treats "still the live socket" as the signal to reconnect.
            // Closing first would make every deliberate teardown look like a
            // drop and immediately resurrect the camera.
            const closing = wsRef.current;
            wsRef.current = null;
            closing.close();
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
    }, [cancelReconnect]);

    const startUsbCamera = useCallback(async (cameraId: string) => {
        // A previous call is still awaiting getUserMedia — do nothing rather
        // than racing it (see startingUsbCameraRef declaration for why).
        if (startingUsbCameraRef.current) return;
        startingUsbCameraRef.current = true;

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

            ws.onopen = () => {
                setConnectionStatus('connected');
                reconnectAttemptsRef.current = 0;
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
                                    days_remaining: msg.days_remaining,
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
            ws.onclose = () => {
                setConnectionStatus('disconnected');
                // Recover only if this is still the live socket. stopUsbCamera
                // nulls wsRef and a restart assigns a new one, so an
                // intentional teardown or a superseded socket stays silent
                // instead of resurrecting a camera the user turned off.
                if (wsRef.current !== ws) return;
                scheduleReconnect(cameraId);
            };

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
            // The camera is often still busy for a moment after a drop, so a
            // failed restart must queue another attempt rather than give up.
            scheduleReconnect(cameraId);
        } finally {
            startingUsbCameraRef.current = false;
        }
    }, [stopUsbCamera, scheduleReconnect]);

    // Published for scheduleReconnect (declared above startUsbCamera).
    useEffect(() => {
        startUsbCameraRef.current = startUsbCamera;
    }, [startUsbCamera]);

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
        // Unknown-classified denials (e.g. member_not_found, which can surface
        // a stale cached name from the CV service until its template cache
        // expires) must never disclose identity — mirror the same gating
        // already applied to the border color above.
        const label = granted
            ? `${t.kiosk.accessGrantedLabel} - ${latestRecognition.member_name} (${Math.round(latestRecognition.confidence * 100)}%)`
            : classifyDenial(latestRecognition.denial_reason) === 'unknown'
                ? `${t.kiosk.accessDeniedLabel} - ${t.kiosk.unknownPerson} (${Math.round(latestRecognition.confidence * 100)}%)`
                : `${t.kiosk.accessDeniedLabel} - ${latestRecognition.member_name || t.kiosk.unknownPerson} (${Math.round(latestRecognition.confidence * 100)}%)`;

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
    }, [latestRecognition, t, usbMode]);

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

    // Nobody is standing at an unattended kiosk to choose a camera, so adopt
    // the first configured one as soon as the list arrives. An explicit URL
    // selection may intentionally be outside this list, but a remembered ID
    // must still exist because cameras can be deleted between restarts.
    useEffect(() => {
        if (urlCameraId) return;
        const firstCamera = camerasData?.[0];
        if (!firstCamera) return;
        if (selectedCameraId && camerasData.some((camera) => camera.id === selectedCameraId)) return;
        setSelectedCameraId(firstCamera.id);
    }, [camerasData, selectedCameraId, urlCameraId]);

    useEffect(() => {
        if (!selectedCameraId) return;
        rememberCameraId(selectedCameraId);
    }, [selectedCameraId]);

    const handleCameraChange = (e: any) => {
        const id = e.target.value;
        setSelectedCameraId(id);
        setSearchParams({ cameraId: id });
    };

    const displayEvents = usbMode ? localEvents : remoteEvents;
    const recentCheckins = displayEvents.slice(0, 3);
    const showGuide = recognitionState === 'idle' || recognitionState === 'verifying';
    const cameraUnavailable = !!selectedCameraId && (streamError || (usbMode && (connectionStatus === 'error' || connectionStatus === 'disconnected')));
    const cameraReady = selectedCameraId && (!usbMode || connectionStatus === 'connected') && !streamError;
    const statusTitle = recognitionState === 'verifying'
        ? t.kiosk.verifyingTitle
        : cameraReady
            ? t.kiosk.readyTitle
            : connectionStatus === 'connecting'
                ? t.kiosk.preparingCamera
                : t.kiosk.cameraReconnecting;
    const statusDetail = recognitionState === 'verifying'
        ? t.kiosk.verifyingDetail
        : cameraReady
            ? t.kiosk.faceCamera
            : t.kiosk.cameraReconnectingDetail;

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
                background: `radial-gradient(circle at 50% 35%, ${alpha(COLORS.primary, 0.11)} 0%, transparent 42%), radial-gradient(circle at 85% 80%, ${alpha(COLORS.accent, 0.05)} 0%, transparent 32%), ${COLORS.background}`,
                color: COLORS.text,
                position: 'relative',
                overflow: 'hidden',
                '@media (prefers-reduced-motion: reduce)': {
                    '&, & *': { animation: 'none !important', transition: 'none !important' },
                },
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
                    px: { xs: 2, md: 4 },
                    py: { xs: 1.5, md: 2.5 },
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

                <Box sx={{ display: 'flex', alignItems: 'center', gap: { xs: 1.5, md: 3 } }}>
                    <Box data-testid="system-status" sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 0.75, borderRadius: 99, bgcolor: alpha(COLORS.surface, 0.78), border: `1px solid ${alpha(cameraUnavailable ? COLORS.danger : cameraReady ? COLORS.success : COLORS.warning, 0.45)}`, backdropFilter: 'blur(12px)' }}>
                        <StatusDotSmall $color={cameraUnavailable ? 'red' : cameraReady ? 'green' : 'yellow'} />
                        <Typography fontWeight={800} sx={{ color: cameraUnavailable ? COLORS.danger : COLORS.text, fontSize: { xs: '0.78rem', sm: '0.88rem', lg: '0.95rem' }, letterSpacing: '0.04em' }}>
                            {cameraUnavailable ? t.kiosk.systemUnavailable : cameraReady ? t.kiosk.systemReady : t.kiosk.systemPreparing}
                        </Typography>
                    </Box>
                    <Typography fontWeight={500} sx={{ display: { xs: 'none', sm: 'block' }, color: alpha(COLORS.text, 0.74), fontSize: { sm: '1.55rem', lg: '1.75rem' }, fontVariantNumeric: 'tabular-nums' }}>
                        {format(currentTime, 'h:mm a')}
                    </Typography>
                </Box>
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
                    px: { xs: 1.5, md: 3 },
                    pt: { xs: 8, md: 9 },
                    pb: { xs: 2, md: 3 },
                }}
            >
                {/* Camera Feed */}
                <CameraContainer $state={recognitionState} data-testid="camera-hero">
                    {selectedCameraId ? (
                        usbMode ? (
                            <>
                                <video ref={videoRef} autoPlay playsInline muted style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
                                <canvas ref={overlayCanvasRef} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', objectFit: 'contain', pointerEvents: 'none' }} />
                                <canvas ref={canvasRef} style={{ display: 'none' }} />
                                {(connectionStatus === 'error' || connectionStatus === 'disconnected') && (
                                    <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', bgcolor: alpha(COLORS.background, 0.92), gap: 0.5, px: 3 }}>
                                        <WifiOffIcon sx={{ fontSize: 44, color: COLORS.secondaryText, mb: 1, animation: `${breathe} 2s ease-in-out infinite` }} />
                                        <Typography sx={{ color: COLORS.text, fontWeight: 600, textAlign: 'center' }}>{t.kiosk.cameraReconnecting}</Typography>
                                        <Typography variant="body2" sx={{ color: COLORS.secondaryText, textAlign: 'center' }}>{t.kiosk.cameraReconnectingDetail}</Typography>
                                        <Button
                                            variant="outlined"
                                            size="small"
                                            sx={{ mt: 2, color: COLORS.accent, borderColor: alpha(COLORS.accent, 0.5), '&:hover': { borderColor: COLORS.accent, bgcolor: alpha(COLORS.accent, 0.08) } }}
                                            onClick={() => startUsbCamera(selectedCameraId)}
                                        >
                                            {t.kiosk.retry}
                                        </Button>
                                    </Box>
                                )}
                            </>
                        ) : (
                            <>
                            <img
                                src={cvServiceApi.getStreamUrl(selectedCameraId)}
                                alt={t.kiosk.liveCameraAlt}
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
                    {!!selectedCameraId && !streamError && (!usbMode || (connectionStatus !== 'error' && connectionStatus !== 'disconnected')) && (
                        <Fade in={showGuide} timeout={300}>
                            <Box data-testid="scan-guide" sx={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
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

                {!cameraUnavailable && !isSplashState(recognitionState) && <Box
                    data-testid="status-dock"
                    role="status"
                    aria-live="polite"
                    aria-atomic="true"
                    sx={{
                        width: { xs: 'calc(100% - 32px)', sm: 'min(760px, 76vw)' },
                        minHeight: { xs: 92, sm: 108 },
                        mt: { xs: -2.5, sm: -3.5 },
                        zIndex: 4,
                        px: { xs: 2.5, sm: 4 },
                        py: { xs: 1.5, sm: 2 },
                        borderRadius: { xs: 3, sm: 4 },
                        textAlign: 'center',
                        bgcolor: alpha(COLORS.surface, 0.9),
                        border: `1px solid ${alpha(recognitionState === 'verifying' ? COLORS.accent : COLORS.text, 0.16)}`,
                        boxShadow: `0 18px 50px ${alpha('#000', 0.48)}`,
                        backdropFilter: 'blur(18px)',
                    }}
                >
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1.5 }}>
                        {recognitionState === 'verifying' ? (
                            <CircularProgress size={24} thickness={4} sx={{ color: COLORS.accent }} />
                        ) : (
                            <Box sx={{ width: 11, height: 11, borderRadius: '50%', bgcolor: cameraReady ? COLORS.success : COLORS.warning, boxShadow: `0 0 18px ${alpha(cameraReady ? COLORS.success : COLORS.warning, 0.7)}` }} />
                        )}
                        <Typography component="h1" sx={{ color: recognitionState === 'verifying' ? COLORS.accent : COLORS.text, fontWeight: 800, fontSize: { xs: '1.35rem', sm: '1.8rem', lg: '2.1rem' }, lineHeight: 1.1 }}>
                            {statusTitle}
                        </Typography>
                    </Box>
                    <Typography sx={{ mt: 0.75, color: COLORS.secondaryText, fontSize: { xs: '0.9rem', sm: '1.05rem' } }}>
                        {statusDetail}
                    </Typography>
                </Box>}
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
                    // Unknown-classified denials (e.g. member_not_found, which can carry a
                    // stale cached real name) must never disclose identity here either —
                    // mirror the same gating already applied to the bbox overlay label
                    // (which also masks with the literal "Unknown", not a translated string).
                    const displayName = denied && classifyDenial(event.denial_reason) === 'unknown'
                        ? t.kiosk.unknownPerson
                        : event.member_name;
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
                            label={`${displayName} · ${format(new Date(event.timestamp), 'h:mm a')}`}
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
                    aria-label={t.kiosk.settings}
                    onClick={() => setSettingsOpen((prev) => !prev)}
                    sx={{ bgcolor: alpha(COLORS.text, 0.05), border: '1px solid', borderColor: alpha(COLORS.text, 0.12), color: COLORS.secondaryText, minWidth: 44, minHeight: 44, '&:hover': { bgcolor: alpha(COLORS.text, 0.1), color: COLORS.text } }}
                >
                    <SettingsIcon />
                </IconButton>
            </Box>

            {/* ---- FULL-SCREEN RESULT SPLASH ----
                The outcome is the one thing a member needs to read from across
                the lobby, so it takes the whole screen rather than sitting in a
                panel above the camera frame. */}
            {isSplashState(recognitionState) && (
                <SplashOverlay
                    $state={recognitionState}
                    data-testid="result-splash"
                    data-state={recognitionState}
                    role="status"
                    aria-live="assertive"
                    aria-atomic="true"
                >
                    <Box sx={{ animation: `${iconPop} 0.5s ease-out`, mb: { xs: 2, sm: 3 } }}>
                        {recognitionState === 'granted' && (
                            <CheckCircleIcon
                                sx={{
                                    fontSize: { xs: 80, sm: 120 },
                                    color: COLORS.success,
                                    filter: `drop-shadow(0 0 30px ${alpha(COLORS.success, 0.6)})`,
                                }}
                            />
                        )}
                        {(recognitionState === 'granted_expiring' ||
                            recognitionState === 'granted_payment_due') && (
                            <WarningAmberIcon
                                sx={{
                                    fontSize: { xs: 80, sm: 120 },
                                    color: COLORS.warning,
                                    filter: `drop-shadow(0 0 30px ${alpha(COLORS.warning, 0.6)})`,
                                }}
                            />
                        )}
                        {recognitionState === 'membership_denied' && (
                            <WarningAmberIcon
                                sx={{
                                    fontSize: { xs: 80, sm: 120 },
                                    color: COLORS.danger,
                                    filter: `drop-shadow(0 0 30px ${alpha(COLORS.danger, 0.6)})`,
                                }}
                            />
                        )}
                        {recognitionState === 'unknown_denied' && (
                            <HelpOutlineIcon
                                sx={{
                                    fontSize: { xs: 80, sm: 120 },
                                    color: COLORS.danger,
                                    filter: `drop-shadow(0 0 30px ${alpha(COLORS.danger, 0.6)})`,
                                }}
                            />
                        )}
                    </Box>

                    <Typography
                        variant={isMobile ? 'h4' : 'h2'}
                        fontWeight={900}
                        sx={{
                            letterSpacing: '0.04em',
                            color: SPLASH_ACCENT[recognitionState],
                            textShadow: `0 0 40px ${alpha(SPLASH_ACCENT[recognitionState], 0.5)}`,
                            mb: 1,
                        }}
                    >
                        {t.kiosk[SPLASH_TITLE_KEY[recognitionState]]}
                    </Typography>

                    {/* An unrecognized face has no name to show — and any name
                        attached to that result may be a stale cache hit, so it
                        must never be displayed. */}
                    {recognitionState !== 'unknown_denied' && !!recognizedName && (
                        <Typography
                            variant={isMobile ? 'h5' : 'h3'}
                            fontWeight={700}
                            sx={{
                                animation: `${slideDown} 0.4s ease-out`,
                                color: alpha(COLORS.text, 0.95),
                                mb: 2,
                                maxWidth: '80vw',
                                lineHeight: 1.2,
                            }}
                        >
                            {recognizedName}
                        </Typography>
                    )}

                    {recognitionState === 'granted' && (
                        <>
                            {membershipExpiry && (
                                <Typography
                                    variant={isMobile ? 'body1' : 'h6'}
                                    sx={{ color: alpha(COLORS.success, 0.9), fontWeight: 400 }}
                                >
                                    {t.kiosk.membershipValidUntil}: {formatExpiryDate(membershipExpiry)}
                                </Typography>
                            )}
                            <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 1 }}>
                                {t.kiosk.doorOpening}
                            </Typography>
                        </>
                    )}

                    {recognitionState === 'granted_expiring' && (
                        <>
                            <Typography
                                variant={isMobile ? 'body1' : 'h6'}
                                sx={{ color: COLORS.warning, fontWeight: 600, mb: 0.5 }}
                            >
                                {t.kiosk.membershipExpiringSoon}: {daysRemaining}{' '}
                                {daysRemaining === 1 ? t.kiosk.dayUnit : t.kiosk.daysUnit}
                            </Typography>
                            {membershipExpiry && (
                                <Typography
                                    variant={isMobile ? 'body2' : 'body1'}
                                    sx={{ color: alpha(COLORS.warning, 0.75), fontWeight: 400 }}
                                >
                                    {t.kiosk.expiresOn}: {formatExpiryDate(membershipExpiry)}
                                </Typography>
                            )}
                            <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 1 }}>
                                {t.kiosk.pleaseVisitReception}
                            </Typography>
                        </>
                    )}

                    {/* The door already opened — this block exists purely so the
                        member learns at the door what they still owe, instead of
                        finding out weeks later. */}
                    {recognitionState === 'granted_payment_due' && (
                        <>
                            <Typography
                                variant={isMobile ? 'body1' : 'h6'}
                                sx={{ color: COLORS.warning, fontWeight: 600, mb: 0.5 }}
                                data-testid="payment-due-notice"
                            >
                                {t.kiosk.paymentPending}
                            </Typography>
                            {amountDue !== null && (
                                <Typography
                                    variant={isMobile ? 'h6' : 'h5'}
                                    fontWeight={800}
                                    sx={{ color: COLORS.warning, mb: 0.5 }}
                                    data-testid="payment-due-amount"
                                >
                                    {t.kiosk.amountDue}: {formatAmountDue(amountDue)}
                                </Typography>
                            )}
                            {/* Both warnings can apply at once. The balance leads,
                                but an expiry that is also imminent still gets said
                                rather than being swallowed by it. */}
                            {daysRemaining !== null && daysRemaining <= EXPIRY_WARNING_DAYS && (
                                <Typography
                                    variant={isMobile ? 'body2' : 'body1'}
                                    sx={{ color: alpha(COLORS.warning, 0.75), fontWeight: 400 }}
                                >
                                    {t.kiosk.membershipExpiringSoon}: {daysRemaining}{' '}
                                    {daysRemaining === 1 ? t.kiosk.dayUnit : t.kiosk.daysUnit}
                                </Typography>
                            )}
                            <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 1 }}>
                                {t.kiosk.pleaseVisitReception}
                            </Typography>
                        </>
                    )}

                    {recognitionState === 'membership_denied' && (
                        <>
                            <Typography
                                variant={isMobile ? 'body1' : 'h6'}
                                sx={{ color: alpha(COLORS.text, 0.75), fontWeight: 400 }}
                            >
                                {humanizeDenialReason(denialReason, t)}
                            </Typography>
                            {/* Only the non-payment denial carries a balance, and
                                naming it turns "come see reception" into an
                                errand the member can actually complete. */}
                            {amountDue !== null && (
                                <Typography
                                    variant={isMobile ? 'h6' : 'h5'}
                                    fontWeight={800}
                                    sx={{ color: COLORS.danger, mt: 0.5 }}
                                    data-testid="denied-amount-due"
                                >
                                    {t.kiosk.amountDue}: {formatAmountDue(amountDue)}
                                </Typography>
                            )}
                            <Typography variant="body2" sx={{ color: COLORS.secondaryText, mt: 1 }}>
                                {t.kiosk.pleaseVisitReception}
                            </Typography>
                        </>
                    )}

                    {recognitionState === 'unknown_denied' && (
                        <Typography
                            variant={isMobile ? 'body1' : 'h6'}
                            sx={{ color: alpha(COLORS.text, 0.7), fontWeight: 400, maxWidth: 420 }}
                        >
                            {t.kiosk.unknownSubtitle}
                        </Typography>
                    )}

                    <Box sx={{ width: { xs: 220, sm: 320 }, mt: { xs: 3, sm: 4 } }}>
                        <Typography variant="caption" sx={{ color: alpha(COLORS.text, 0.68), letterSpacing: '0.04em' }}>
                            {t.kiosk.returningToReady}
                        </Typography>
                        <Box sx={{ height: 3, mt: 1, overflow: 'hidden', borderRadius: 99, bgcolor: alpha(COLORS.text, 0.14) }}>
                            <Box sx={{ width: '100%', height: '100%', transformOrigin: 'left', bgcolor: SPLASH_ACCENT[recognitionState], animation: `${resetCountdown} ${RESULT_RESET_DELAY_MS}ms linear forwards` }} />
                        </Box>
                    </Box>

                    <Box sx={{ position: 'absolute', bottom: { xs: 24, sm: 40 }, opacity: 0.3 }}>
                        <Typography
                            variant="body2"
                            fontWeight={700}
                            sx={{ color: alpha(COLORS.text, 0.5), letterSpacing: '0.1em' }}
                        >
                            POWERHOUSE GYM
                        </Typography>
                    </Box>
                </SplashOverlay>
            )}
        </Box>
    );
};
