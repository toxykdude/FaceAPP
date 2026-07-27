/**
 * Face enrollment page for capturing member's facial data.
 */
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Button,
    Card,
    CardContent,
    CircularProgress,
    LinearProgress,
    Alert,
    Grid,
    Tabs,
    Tab,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    useMediaQuery,
    useTheme,
    Step,
    StepLabel,
    Stepper,
} from '@mui/material';
import { CameraAlt as CameraIcon, PhotoLibrary as PhotoIcon, CheckCircle as CheckIcon, Videocam as VideoIcon, ConnectedTv as SystemIcon, CloudUpload as TabletIcon } from '@mui/icons-material';
import { membersApi } from '@/api/members';
import { camerasApi } from '@/api/cameras';
import { useLanguage } from '@/i18n/LanguageContext';

export const FaceEnrollment: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

    const [tabValue, setTabValue] = useState(0);

    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [stream, setStream] = useState<MediaStream | null>(null);
    const [isWebcamActive, setIsWebcamActive] = useState(false);

    const [selectedCameraId, setSelectedCameraId] = useState('');

    const { data: member, isLoading: memberLoading } = useQuery({
        queryKey: ['member', id],
        queryFn: () => membersApi.getMember(id!),
    });

    const { data: status, isLoading: statusLoading } = useQuery({
        queryKey: ['biometric-status', id],
        queryFn: () => membersApi.getBiometricStatus(id!),
    });

    const { data: systemCameras } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras(),
    });

    const enrollMutation = useMutation({
        mutationFn: (file: File) => membersApi.enrollBiometric(id!, file),
        onSuccess: () => {
            handleSuccess();
        },
        onError: handleError,
    });

    const enrollCameraMutation = useMutation({
        mutationFn: (cameraId: string) => membersApi.enrollBiometricFromCamera(id!, cameraId),
        onSuccess: () => {
            handleSuccess();
        },
        onError: handleError,
    });

    // --- Tablet Camera state ---
    const [tabletRequestId, setTabletRequestId] = useState<string | null>(null);
    const [tabletStatus, setTabletStatus] = useState<'idle' | 'creating' | 'pending' | 'processing' | 'complete' | 'failed' | 'cancelled'>('idle');
    const [tabletQualityScore, setTabletQualityScore] = useState<number | null>(null);
    const [tabletResultMessage, setTabletResultMessage] = useState<string | null>(null);

    const createTabletRequestMutation = useMutation({
        mutationFn: () => membersApi.createEnrollmentRequest(id!),
        onSuccess: (data) => {
            setTabletRequestId(data.id);
            setTabletStatus('pending');
        },
        onError: (error) => {
            setTabletStatus('failed');
            setTabletResultMessage((error as any)?.response?.data?.detail || error.message);
        },
    });

    const cancelTabletRequestMutation = useMutation({
        mutationFn: () => membersApi.cancelEnrollmentRequest(tabletRequestId!),
        onSuccess: () => {
            setTabletStatus('cancelled');
        },
    });

    const pollTabletRequest = useCallback(async () => {
        if (!tabletRequestId) return;
        try {
            const result = await membersApi.getEnrollmentRequest(tabletRequestId);
            setTabletStatus(result.status);
            if (result.quality_score !== null) {
                setTabletQualityScore(result.quality_score);
            }
            if (result.result_message) {
                setTabletResultMessage(result.result_message);
            }
            if (result.status === 'complete') {
                queryClient.invalidateQueries({ queryKey: ['biometric-status', id] });
            }
        } catch {
            // Silently ignore poll errors — keep polling
        }
    }, [tabletRequestId, queryClient, id]);

    useEffect(() => {
        if (tabletStatus !== 'pending' && tabletStatus !== 'processing') return;
        const interval = setInterval(pollTabletRequest, 2000);
        return () => clearInterval(interval);
    }, [tabletStatus, pollTabletRequest]);

    // Reset tablet state when switching away from tab 3
    useEffect(() => {
        if (tabValue !== 3) {
            setTabletRequestId(null);
            setTabletStatus('idle');
            setTabletQualityScore(null);
            setTabletResultMessage(null);
        }
    }, [tabValue]);

    function handleSuccess() {
        queryClient.invalidateQueries({ queryKey: ['biometric-status', id] });
        alert(t.members.enrolledSuccess);
        stopWebcam();
        navigate('/members');
    }

    function handleError(error: any) {
        alert(`${t.members.enrollmentFailed}: ${(error as any)?.response?.data?.detail || error.message}`);
    }

    React.useEffect(() => {
        return () => {
            stopWebcam();
        };
    }, []);

    const startWebcam = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true });
            setStream(mediaStream);
            setIsWebcamActive(true);
            if (videoRef.current) {
                videoRef.current.srcObject = mediaStream;
            }
        } catch (err) {
            console.error("Webcam Request Error:", err);
            alert(t.members.webcamAccessError);
        }
    };

    const stopWebcam = () => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            setStream(null);
        }
        setIsWebcamActive(false);
    };

    const captureWebcam = () => {
        if (videoRef.current && canvasRef.current) {
            const video = videoRef.current;
            const canvas = canvasRef.current;
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx?.drawImage(video, 0, 0);

            canvas.toBlob((blob) => {
                if (blob) {
                    const file = new File([blob], "webcam_capture.jpg", { type: "image/jpeg" });
                    enrollMutation.mutate(file);
                }
            }, 'image/jpeg');
        }
    };

    const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) {
            setSelectedFile(file);
            setPreviewUrl(URL.createObjectURL(file));
        }
    };

    if (memberLoading || statusLoading) {
        return (
            <Box display="flex" justifyContent="center" p={5}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box>
            <Typography variant={isMobile ? "h5" : "h4"} gutterBottom>
                {t.members.faceEnrollmentTitle.replace('{first}', member?.first_name || '').replace('{last}', member?.last_name || '')}
            </Typography>

            <Grid container spacing={3}>
                <Grid item xs={12} md={5}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" gutterBottom>{t.members.currentStatus}</Typography>
                            {status?.enrolled ? (
                                <Alert icon={<CheckIcon fontSize="inherit" />} severity="success">
                                    {t.members.enrolledTemplates.replace('{count}', String(status.template_count || 0))}
                                </Alert>
                            ) : (
                                <Alert severity="warning">{t.members.notEnrolledYet}</Alert>
                            )}

                            <Box mt={2}>
                                <Typography variant="caption" color="text.secondary">
                                    {t.members.chooseMethod}
                                </Typography>
                            </Box>
                        </CardContent>
                    </Card>
                </Grid>

                <Grid item xs={12} md={7}>
                    <Card>
                        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                            <Tabs value={tabValue} onChange={(_, v) => { setTabValue(v); if (v !== 1) stopWebcam(); }} variant="fullWidth">
                                <Tab icon={<PhotoIcon />} label={t.members.uploadPhotoTab} />
                                <Tab icon={<VideoIcon />} label={t.members.webcamTab} />
                                <Tab icon={<SystemIcon />} label={t.members.systemCameraTab} />
                                <Tab icon={<TabletIcon />} label={t.members.tabletCameraTab} />
                            </Tabs>
                        </Box>

                        <CardContent>
                            {tabValue === 0 && (
                                <Box textAlign="center">
                                    <Box
                                        sx={{
                                            height: { xs: 200, sm: 300 },
                                            border: '2px dashed #ccc',
                                            display: 'flex',
                                            justifyContent: 'center',
                                            alignItems: 'center',
                                            mb: 2,
                                            bgcolor: '#f5f5f5',
                                            overflow: 'hidden'
                                        }}
                                    >
                                        {previewUrl ? (
                                            <img src={previewUrl} alt="Preview" style={{ maxWidth: '100%', maxHeight: '100%' }} />
                                        ) : (
                                            <Typography color="text.secondary">{t.members.selectPhoto}</Typography>
                                        )}
                                    </Box>
                                    <input
                                        type="file"
                                        accept="image/*"
                                        style={{ display: 'none' }}
                                        ref={fileInputRef}
                                        onChange={handleFileChange}
                                    />
                                    <Button variant="outlined" startIcon={<PhotoIcon />} onClick={() => fileInputRef.current?.click()} sx={{ mr: 2 }}>
                                        {t.members.chooseFile}
                                    </Button>
                                    <Button
                                        variant="contained"
                                        disabled={!selectedFile || enrollMutation.isPending}
                                        onClick={() => selectedFile && enrollMutation.mutate(selectedFile)}
                                    >
                                        {enrollMutation.isPending ? t.members.enrolling : t.members.uploadEnroll}
                                    </Button>
                                    {enrollMutation.isPending && (
                                        <Box sx={{ mt: 2 }}>
                                            <LinearProgress />
                                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                                                {t.members.enrollingHint}
                                            </Typography>
                                        </Box>
                                    )}
                                </Box>
                            )}

                            {tabValue === 1 && (
                                <Box textAlign="center">
                                    <Box
                                        sx={{
                                            height: { xs: 200, sm: 300 },
                                            bgcolor: '#000',
                                            mb: 2,
                                            position: 'relative',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center'
                                        }}
                                    >
                                        {!isWebcamActive && (
                                            <Button variant="contained" onClick={startWebcam}>{t.members.startCamera}</Button>
                                        )}
                                        <video
                                            ref={videoRef}
                                            autoPlay
                                            playsInline
                                            style={{
                                                width: '100%',
                                                height: '100%',
                                                objectFit: 'contain',
                                                display: isWebcamActive ? 'block' : 'none'
                                            }}
                                        />
                                        <canvas ref={canvasRef} style={{ display: 'none' }} />
                                    </Box>
                                    <Button
                                        variant="contained"
                                        color="primary"
                                        startIcon={<CameraIcon />}
                                        disabled={!isWebcamActive || enrollMutation.isPending}
                                        onClick={captureWebcam}
                                        fullWidth={isMobile}
                                        sx={{ minHeight: 44 }}
                                    >
                                        {enrollMutation.isPending ? t.members.processing : t.members.captureEnroll}
                                    </Button>
                                    {enrollMutation.isPending && (
                                        <Box sx={{ mt: 2 }}>
                                            <LinearProgress />
                                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                                                {t.members.enrollingHint}
                                            </Typography>
                                        </Box>
                                    )}
                                </Box>
                            )}

                            {tabValue === 2 && (
                                <Box>
                                    <Typography gutterBottom>
                                        {t.members.selectSystemCamera}
                                    </Typography>
                                    <FormControl fullWidth sx={{ mb: 3 }}>
                                        <InputLabel>{t.members.selectCameraLabel}</InputLabel>
                                        <Select
                                            value={selectedCameraId}
                                            label={t.members.selectCameraLabel}
                                            onChange={(e) => setSelectedCameraId(e.target.value)}
                                        >
                                            {systemCameras?.map((cam) => (
                                                <MenuItem key={cam.id} value={cam.id}>
                                                    {cam.name} ({cam.enabled ? t.cameras.active : t.members.inactive})
                                                </MenuItem>
                                            ))}
                                        </Select>
                                    </FormControl>
                                    <Button
                                        variant="contained"
                                        fullWidth
                                        disabled={!selectedCameraId || enrollCameraMutation.isPending}
                                        onClick={() => enrollCameraMutation.mutate(selectedCameraId)}
                                    >
                                        {enrollCameraMutation.isPending ? t.members.capturing : t.members.captureFromCamera}
                                    </Button>
                                    {enrollCameraMutation.isPending && (
                                        <Box sx={{ mt: 2 }}>
                                            <LinearProgress />
                                            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                                                {t.members.enrollingHint}
                                            </Typography>
                                        </Box>
                                    )}
                                </Box>
                            )}

                            {tabValue === 3 && (
                                <Box textAlign="center">
                                    {tabletStatus === 'idle' && (
                                        <Box sx={{ py: 4 }}>
                                            <TabletIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
                                            <Typography variant="body1" color="text.secondary" gutterBottom>
                                                {t.members.chooseMethod}
                                            </Typography>
                                            <Button
                                                variant="contained"
                                                startIcon={<TabletIcon />}
                                                onClick={() => {
                                                    setTabletStatus('creating');
                                                    createTabletRequestMutation.mutate();
                                                }}
                                            >
                                                {t.members.tabletStartEnroll}
                                            </Button>
                                        </Box>
                                    )}

                                    {(tabletStatus === 'creating' || tabletStatus === 'pending' || tabletStatus === 'processing') && (
                                        <Box sx={{ py: 2 }}>
                                            <Stepper activeStep={
                                                tabletStatus === 'creating' ? 0
                                                : tabletStatus === 'pending' ? 1
                                                : 2
                                            } alternativeLabel>
                                                <Step completed={tabletStatus !== 'creating'}>
                                                    <StepLabel>{t.members.tabletRequestSent}</StepLabel>
                                                </Step>
                                                {/* This Stepper only renders while tabletStatus is
                                                    creating/pending/processing (see the guard above) — it is
                                                    replaced by a dedicated success/failure screen once the
                                                    request resolves, so "completed" here never needs to check
                                                    for the 'complete'/'failed' statuses. */}
                                                <Step completed={tabletStatus === 'processing'}>
                                                    <StepLabel StepIconComponent={() => (
                                                        tabletStatus === 'pending' ? <CircularProgress size={20} /> : undefined
                                                    )}>
                                                        {t.members.tabletWaiting}
                                                    </StepLabel>
                                                </Step>
                                                <Step>
                                                    <StepLabel StepIconComponent={() => (
                                                        tabletStatus === 'processing' ? <CircularProgress size={20} /> : undefined
                                                    )}>
                                                        {t.members.tabletCapturing}
                                                    </StepLabel>
                                                </Step>
                                                <Step>
                                                    <StepLabel>{t.members.tabletCompleted}</StepLabel>
                                                </Step>
                                            </Stepper>

                                            <Box sx={{ mt: 4 }}>
                                                <CircularProgress size={32} sx={{ mb: 2 }} />
                                                <Typography variant="body1">
                                                    {tabletStatus === 'creating' && t.members.tabletRequestSent}
                                                    {tabletStatus === 'pending' && t.members.tabletWaiting}
                                                    {tabletStatus === 'processing' && t.members.tabletCapturing}
                                                </Typography>
                                            </Box>

                                            <Box sx={{ mt: 3 }}>
                                                <Button
                                                    variant="outlined"
                                                    color="error"
                                                    disabled={cancelTabletRequestMutation.isPending}
                                                    onClick={() => cancelTabletRequestMutation.mutate()}
                                                >
                                                    {t.members.tabletCancel}
                                                </Button>
                                            </Box>
                                        </Box>
                                    )}

                                    {(tabletStatus as string) === 'complete' && (
                                        <Box sx={{ py: 3 }}>
                                            <Alert icon={<CheckIcon fontSize="inherit" />} severity="success" sx={{ mb: 2 }}>
                                                {t.members.tabletEnrollSuccess}
                                            </Alert>
                                            {tabletQualityScore !== null && (
                                                <Typography variant="h6" color="primary" sx={{ mb: 2 }}>
                                                    {t.members.tabletQualityScore}: {tabletQualityScore.toFixed(1)}%
                                                </Typography>
                                            )}
                                            {tabletResultMessage && (
                                                <Typography variant="body2" color="text.secondary">
                                                    {tabletResultMessage}
                                                </Typography>
                                            )}
                                        </Box>
                                    )}

                                    {(tabletStatus as string) === 'failed' && (
                                        <Box sx={{ py: 3 }}>
                                            <Alert severity="error" sx={{ mb: 2 }}>
                                                {t.members.tabletEnrollError}
                                            </Alert>
                                            {tabletResultMessage && (
                                                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                                                    {tabletResultMessage}
                                                </Typography>
                                            )}
                                            <Button
                                                variant="contained"
                                                onClick={() => {
                                                    setTabletStatus('idle');
                                                    setTabletRequestId(null);
                                                    setTabletQualityScore(null);
                                                    setTabletResultMessage(null);
                                                }}
                                            >
                                                {t.members.retry}
                                            </Button>
                                        </Box>
                                    )}

                                    {tabletStatus === 'cancelled' && (
                                        <Box sx={{ py: 3 }}>
                                            <Alert severity="warning" sx={{ mb: 2 }}>
                                                {t.members.tabletCancelled}
                                            </Alert>
                                            <Button
                                                variant="contained"
                                                onClick={() => {
                                                    setTabletStatus('idle');
                                                    setTabletRequestId(null);
                                                    setTabletQualityScore(null);
                                                    setTabletResultMessage(null);
                                                }}
                                            >
                                                {t.members.retry}
                                            </Button>
                                        </Box>
                                    )}
                                </Box>
                            )}
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>
        </Box>
    );
};
