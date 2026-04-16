/**
 * Face enrollment page for capturing member's facial data.
 */
import React, { useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Button,
    Card,
    CardContent,
    CircularProgress,
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
} from '@mui/material';
import { CameraAlt as CameraIcon, PhotoLibrary as PhotoIcon, CheckCircle as CheckIcon, Videocam as VideoIcon, ConnectedTv as SystemIcon } from '@mui/icons-material';
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

    function handleSuccess() {
        queryClient.invalidateQueries({ queryKey: ['biometric-status', id] });
        alert(t.members.enrolledSuccess);
        stopWebcam();
        navigate('/members');
    }

    function handleError(error: any) {
        alert(`${t.members.enrollmentFailed}: ${error.response?.data?.detail || error.message}`);
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
            alert("Could not access webcam. Please check permissions.");
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
                                </Box>
                            )}
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>
        </Box>
    );
};
