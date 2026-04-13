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
} from '@mui/material';
import { CameraAlt as CameraIcon, PhotoLibrary as PhotoIcon, CheckCircle as CheckIcon, Videocam as VideoIcon, ConnectedTv as SystemIcon } from '@mui/icons-material';
import { membersApi } from '@/api/members';
import { camerasApi } from '@/api/cameras';

export const FaceEnrollment: React.FC = () => {
    const { id } = useParams();
    const navigate = useNavigate();
    const queryClient = useQueryClient();

    const [tabValue, setTabValue] = useState(0);

    // File Upload State
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Webcam State
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [stream, setStream] = useState<MediaStream | null>(null);
    const [isWebcamActive, setIsWebcamActive] = useState(false);

    // System Camera State
    const [selectedCameraId, setSelectedCameraId] = useState('');

    // Queries
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

    // Mutations
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
        alert('Face enrollment successful!');
        stopWebcam();
        navigate('/members');
    }

    function handleError(error: any) {
        alert(`Enrollment failed: ${error.response?.data?.detail || error.message}`);
    }

    // Webcam Logic
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

    // UI Handlers
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
            <Typography variant="h4" gutterBottom>
                Face Enrollment: {member?.first_name} {member?.last_name}
            </Typography>

            <Grid container spacing={3}>
                <Grid item xs={12} md={5}>
                    <Card>
                        <CardContent>
                            <Typography variant="h6" gutterBottom>Current Status</Typography>
                            {status?.enrolled ? (
                                <Alert icon={<CheckIcon fontSize="inherit" />} severity="success">
                                    Enrolled ({status.template_count} templates).
                                </Alert>
                            ) : (
                                <Alert severity="warning">Not enrolled yet.</Alert>
                            )}

                            <Box mt={2}>
                                <Typography variant="caption" color="text.secondary">
                                    Choose an enrollment method on the right. Ensure good lighting and a clear view of the face.
                                </Typography>
                            </Box>
                        </CardContent>
                    </Card>
                </Grid>

                <Grid item xs={12} md={7}>
                    <Card>
                        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                            <Tabs value={tabValue} onChange={(_, v) => { setTabValue(v); if (v !== 1) stopWebcam(); }} variant="fullWidth">
                                <Tab icon={<PhotoIcon />} label="Upload Photo" />
                                <Tab icon={<VideoIcon />} label="Webcam" />
                                <Tab icon={<SystemIcon />} label="System Camera" />
                            </Tabs>
                        </Box>

                        <CardContent>
                            {/* TAB 0: Upload */}
                            {tabValue === 0 && (
                                <Box textAlign="center">
                                    <Box
                                        sx={{
                                            height: 300,
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
                                            <Typography color="text.secondary">Select a photo</Typography>
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
                                        Choose File
                                    </Button>
                                    <Button
                                        variant="contained"
                                        disabled={!selectedFile || enrollMutation.isPending}
                                        onClick={() => selectedFile && enrollMutation.mutate(selectedFile)}
                                    >
                                        {enrollMutation.isPending ? 'Enrolling...' : 'Upload & Enroll'}
                                    </Button>
                                </Box>
                            )}

                            {/* TAB 1: Webcam */}
                            {tabValue === 1 && (
                                <Box textAlign="center">
                                    <Box
                                        sx={{
                                            height: 300,
                                            bgcolor: '#000',
                                            mb: 2,
                                            position: 'relative',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center'
                                        }}
                                    >
                                        {!isWebcamActive && (
                                            <Button variant="contained" onClick={startWebcam}>Start Camera</Button>
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
                                    >
                                        {enrollMutation.isPending ? 'Processing...' : 'Capture & Enroll'}
                                    </Button>
                                </Box>
                            )}

                            {/* TAB 2: System Camera */}
                            {tabValue === 2 && (
                                <Box>
                                    <Typography gutterBottom>
                                        Select a connected system camera (RTSP/Server USB) to capture a frame.
                                    </Typography>
                                    <FormControl fullWidth sx={{ mb: 3 }}>
                                        <InputLabel>Select Camera</InputLabel>
                                        <Select
                                            value={selectedCameraId}
                                            label="Select Camera"
                                            onChange={(e) => setSelectedCameraId(e.target.value)}
                                        >
                                            {systemCameras?.map((cam) => (
                                                <MenuItem key={cam.id} value={cam.id}>
                                                    {cam.name} ({cam.enabled ? 'Active' : 'Inactive'})
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
                                        {enrollCameraMutation.isPending ? 'Capturing...' : 'Capture from Camera'}
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
