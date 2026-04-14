/**
 * Dashboard page component - Modern task management interface
 */
import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
    Box,
    Typography,
    Paper,
    Chip,
    IconButton,
    Avatar,
    Button,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
} from '@mui/material';
import {
    PersonAdd as PersonAddIcon,
    Videocam as VideocamIcon,
    Assessment as AssessmentIcon,
    Schedule as ScheduleIcon,
    Warning as WarningIcon,
} from '@mui/icons-material';
import { eventsApi } from '@/api/events';
import { membersApi } from '@/api/members';
import { useAuth } from '@/contexts/AuthContext';
import { format } from 'date-fns';
import {
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Card,
    CardHeader,
    CardContent
} from '@mui/material';
import {
    OpenInNew as OpenInNewIcon,
} from '@mui/icons-material';
import { camerasApi } from '@/api/cameras';
import { membershipsApi } from '@/api/memberships';
import { cvServiceApi } from '@/api/cvService';

export const Dashboard: React.FC = () => {
    const navigate = useNavigate();
    const { user } = useAuth();

    // Note: Member count query removed - using hardcoded stats for now
    // In production, fetch from a dedicated stats endpoint

    const { data: recentEvents } = useQuery({
        queryKey: ['recent-events'],
        queryFn: () => eventsApi.getRecentEvents(5),
        retry: false,
    });

    const { data: membersData } = useQuery({
        queryKey: ['members-stats'],
        queryFn: () => membersApi.getMembers({ limit: 1 }),
    });

    const { data: expiredMemberships } = useQuery({
        queryKey: ['expired-memberships'],
        queryFn: async () => {
            const response = await membershipsApi.getMemberships(0, 20, undefined, 'expired');
            return response;
        },
        staleTime: 1000 * 60 * 60,
    });


    // Camera Widget Logic
    const [selectedCam, setSelectedCam] = useState('');

    const { data: camerasData } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras()
    });

    // Auto-select first camera (cameras are auto-started by CV service on startup)
    useEffect(() => {
        if (camerasData?.length && !selectedCam) {
            setSelectedCam(camerasData[0].id);
        }
    }, [camerasData]);

    const handleOpenKiosk = () => {
        window.open(`/kiosk?cameraId=${selectedCam}`, 'PowerHouseKiosk', 'width=1000,height=800');
    };

    const handleCamChange = (e: any) => {
        setSelectedCam(e.target.value);
    };

const stats = {
        activeMembers: membersData?.total || 0,
        todayCheckIns: recentEvents?.filter(e => {
            const date = new Date(e.timestamp);
            const today = new Date();
            return date.getDate() === today.getDate() &&
                date.getMonth() === today.getMonth() &&
                date.getFullYear() === today.getFullYear();
        }).length || 0,
        // TODO: connect to sales report API
        monthlyRevenue: 0,
    };

    const currentDate = format(new Date(), 'EEE, MMMM d');

    return (
        <Box
            sx={{
                maxWidth: '1400px',
                margin: '0 auto',
                padding: { xs: 2, md: 4 },
            }}
        >
            {/* Header Section */}
            <Box sx={{ mb: 4 }}>
                <Typography
                    variant="body2"
                    sx={{
                        color: 'var(--text-secondary)',
                        mb: 1,
                        fontWeight: 500,
                    }}
                >
                    {currentDate}
                </Typography>
                <Typography
                    variant="h3"
                    sx={{
                        fontWeight: 800,
                        color: 'var(--text-primary)',
                        mb: 0.5,
                    }}
                >
                    Hello, {user?.username || 'Admin'}
                </Typography>
                <Typography
                    variant="h4"
                    className="gradient-text"
                    sx={{
                        fontWeight: 700,
                    }}
                >
                    How can I help you today?
                </Typography>
            </Box>

            {/* Main Content */}
            <Box sx={{ display: 'flex', gap: 3, flexDirection: { xs: 'column', lg: 'row' } }}>
                {/* Quick Actions Section */}
                <Box sx={{ flex: 1 }}>
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            borderRadius: 'var(--radius-xl)',
                            border: '1px solid var(--border-color)',
                            background: 'var(--bg-secondary)',
                        }}
                    >
                        <Typography variant="h6" sx={{ fontWeight: 600, mb: 3 }}>
                            Quick Actions
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                            <Button
                                variant="outlined"
                                startIcon={<PersonAddIcon />}
                                onClick={() => navigate('/members/new')}
                                sx={{
                                    justifyContent: 'flex-start',
                                    p: 1.5,
                                    borderRadius: 'var(--radius-lg)',
                                    textTransform: 'none',
                                    borderColor: 'var(--border-color)',
                                }}
                            >
                                Add Member
                            </Button>
                            <Button
                                variant="outlined"
                                startIcon={<VideocamIcon />}
                                onClick={() => navigate('/cameras')}
                                sx={{
                                    justifyContent: 'flex-start',
                                    p: 1.5,
                                    borderRadius: 'var(--radius-lg)',
                                    textTransform: 'none',
                                    borderColor: 'var(--border-color)',
                                }}
                            >
                                View Cameras
                            </Button>
                            <Button
                                variant="outlined"
                                startIcon={<AssessmentIcon />}
                                onClick={() => navigate('/reports')}
                                sx={{
                                    justifyContent: 'flex-start',
                                    p: 1.5,
                                    borderRadius: 'var(--radius-lg)',
                                    textTransform: 'none',
                                    borderColor: 'var(--border-color)',
                                }}
                            >
                                View Reports
                            </Button>
                        </Box>
                    </Paper>

                    {/* Expired Memberships Widget */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            mt: 3,
                            borderRadius: 'var(--radius-xl)',
                            border: '1px solid var(--border-color)',
                            background: 'var(--bg-secondary)',
                        }}
                    >
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <WarningIcon sx={{ mr: 1.5, color: '#f44336' }} />
                                <Typography variant="h6" sx={{ fontWeight: 600 }}>Expired Memberships</Typography>
                            </Box>
                            <Button size="small" onClick={() => navigate('/memberships')}>View All</Button>
                        </Box>
                        <TableContainer>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Member</TableCell>
                                        <TableCell>ID</TableCell>
                                        <TableCell>Plan</TableCell>
                                        <TableCell>Expired</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {[...(expiredMemberships || [])].sort((a: any, b: any) => new Date(b.end_date).getTime() - new Date(a.end_date).getTime()).slice(0, 20).map((m: any) => (
                                        <TableRow
                                            key={m.id}
                                            hover
                                            onClick={() => navigate(`/members/${m.member_id}`)}
                                            sx={{ cursor: 'pointer' }}
                                        >
                                            <TableCell>{m.member_name || 'Unknown'}</TableCell>
                                            <TableCell>{m.member_id_number || '-'}</TableCell>
                                            <TableCell>{m.plan_name || m.type}</TableCell>
                                            <TableCell>{format(new Date(m.end_date), 'MMM d, yyyy')}</TableCell>
                                        </TableRow>
                                    ))}
                                    {(!expiredMemberships || expiredMemberships.length === 0) && (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center">No expired memberships</TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>
                </Box>

                {/* Stats & Quick Actions Sidebar */}
                <Box sx={{ width: { xs: '100%', lg: '320px' } }}>

                    {/* Live Feed Widget */}
                    <Card sx={{ mb: 3, borderRadius: 'var(--radius-xl)', border: '1px solid var(--border-color)' }}>
                        <CardHeader
                            title="Live Access Monitor"
                            avatar={<VideocamIcon color="primary" />}
                            action={
                                <IconButton onClick={handleOpenKiosk} title="Detach Window">
                                    <OpenInNewIcon />
                                </IconButton>
                            }
                        />
                        <CardContent>
                            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                                <InputLabel>Camera</InputLabel>
                                <Select value={selectedCam} label="Camera" onChange={handleCamChange}>
                                    {camerasData?.map((cam: any) => (
                                        <MenuItem key={cam.id} value={cam.id}>{cam.name}</MenuItem>
                                    ))}
                                </Select>
                            </FormControl>

                            <Box
                                sx={{
                                    width: '100%',
                                    aspectRatio: '16/9',
                                    bgcolor: 'black',
                                    borderRadius: 1,
                                    overflow: 'hidden',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center'
                                }}
                            >
                                {selectedCam ? (
                                    <img
                                        src={cvServiceApi.getStreamUrl(selectedCam)}
                                        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                                        alt="Live Feed"
                                    />
                                ) : (
                                    <Typography variant="body2" color="grey.500">Select a camera</Typography>
                                )}
                            </Box>
                        </CardContent>
                    </Card>

                    {/* Quick Stats */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            mb: 3,
                            borderRadius: 'var(--radius-xl)',
                            border: '1px solid var(--border-color)',
                            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                            color: 'white',
                            position: 'relative',
                            overflow: 'hidden',
                        }}
                    >
                        <Box
                            sx={{
                                position: 'absolute',
                                top: -20,
                                right: -20,
                                width: 100,
                                height: 100,
                                borderRadius: '50%',
                                background: 'rgba(255, 255, 255, 0.1)',
                            }}
                        />
                        <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, position: 'relative' }}>
                            Quick Stats
                        </Typography>
                        <Box sx={{ position: 'relative' }}>
                            <Box sx={{ mb: 2 }}>
                                <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>
                                    Active Members
                                </Typography>
                                <Typography variant="h4" sx={{ fontWeight: 700 }}>
                                    {stats.activeMembers}
                                </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                                <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>
                                    Today's Check-ins
                                </Typography>
                                <Typography variant="h4" sx={{ fontWeight: 700 }}>
                                    {stats.todayCheckIns}
                                </Typography>
                            </Box>
                            <Box>
                                <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>
                                    Monthly Revenue
                                </Typography>
                                <Typography variant="h4" sx={{ fontWeight: 700 }}>
                                    ${stats.monthlyRevenue.toLocaleString()}
                                </Typography>
                            </Box>
                        </Box>
                    </Paper>

                    {/* Recent Activity */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: 3,
                            borderRadius: 'var(--radius-xl)',
                            border: '1px solid var(--border-color)',
                            background: 'var(--bg-secondary)',
                        }}
                    >
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                            <ScheduleIcon sx={{ mr: 1.5, color: 'var(--accent-cyan)' }} />
                            <Typography variant="h6" sx={{ fontWeight: 600 }}>
                                Recent Activity
                            </Typography>
                        </Box>
                        <Box>
                            {recentEvents?.slice(0, 3).map((event, index) => (
                                <Box
                                    key={event.id}
                                    sx={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 2,
                                        py: 2,
                                        borderBottom: index < 2 ? '1px solid var(--border-color)' : 'none',
                                    }}
                                >
                                    <Avatar
                                        sx={{
                                            width: 40,
                                            height: 40,
                                            background: 'var(--primary-gradient)',
                                        }}
                                    >
                                        {event.member_name?.[0] || 'M'}
                                    </Avatar>
                                    <Box sx={{ flex: 1 }}>
                                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                                            {event.member_name || (event?.member_id ? `Member ${event.member_id.substring(0, 8)}` : 'Unknown')}
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: 'var(--text-secondary)' }}>
                                            {event.event_type} • {event.timestamp ? format(new Date(event.timestamp), 'h:mm a') : ''}
                                        </Typography>
                                    </Box>
                                    <Chip
                                        label={`${(event.confidence * 100).toFixed(0)}%`}
                                        size="small"
                                        sx={{
                                            background: 'var(--status-progress)',
                                            color: 'var(--status-progress-text)',
                                            fontWeight: 600,
                                        }}
                                    />
                                </Box>
                            ))}
                            {(!recentEvents || recentEvents.length === 0) && (
                                <Typography variant="body2" sx={{ color: 'var(--text-secondary)', py: 2 }}>
                                    No recent activity
                                </Typography>
                            )}
                        </Box>
                    </Paper>
                </Box>
            </Box>
        </Box>
    );
};
