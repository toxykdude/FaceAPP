/**
 * Dashboard page component - Modern task management interface
 */
import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    Box,
    Typography,
    Paper,
    Chip,
    IconButton,
    Avatar,
    Button,
    Collapse,
    Checkbox,
} from '@mui/material';
import {
    ExpandMore as ExpandMoreIcon,
    ExpandLess as ExpandLessIcon,
    Add as AddIcon,
    CheckCircle as CheckCircleIcon,
    Schedule as ScheduleIcon,
} from '@mui/icons-material';
import { eventsApi } from '@/api/events';
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
    Videocam as VideocamIcon
} from '@mui/icons-material';
import { camerasApi } from '@/api/cameras';
import { cvServiceApi } from '@/api/cvService';

interface Task {
    id: string;
    name: string;
    priority: 'High' | 'Normal' | 'Low';
    dueDate: string;
    completed: boolean;
}

export const Dashboard: React.FC = () => {
    const [inProgressExpanded, setInProgressExpanded] = useState(true);
    const [todoExpanded, setTodoExpanded] = useState(true);

    // Note: Member count query removed - using hardcoded stats for now
    // In production, fetch from a dedicated stats endpoint

    const { data: recentEvents } = useQuery({
        queryKey: ['recent-events'],
        queryFn: () => eventsApi.getRecentEvents(5),
        retry: false,
    });


    // Camera Widget Logic
    const [selectedCam, setSelectedCam] = useState('');

    const { data: camerasData } = useQuery({
        queryKey: ['cameras'],
        queryFn: () => camerasApi.getCameras()
    });

    // Auto-select first camera (cameras are auto-started by CV service on startup)
    React.useEffect(() => {
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

    // Mock tasks - In production, these would come from API
    const [inProgressTasks, setInProgressTasks] = useState<Task[]>([
        {
            id: '1',
            name: 'Review new member applications',
            priority: 'High',
            dueDate: 'Today',
            completed: false
        },
        {
            id: '2',
            name: 'Process membership renewals',
            priority: 'Low',
            dueDate: '3 days left',
            completed: false
        },
        {
            id: '3',
            name: 'Update facial recognition database',
            priority: 'Low',
            dueDate: '5 days left',
            completed: false
        },
    ]);

    const [todoTasks, setTodoTasks] = useState<Task[]>([
        {
            id: '4',
            name: 'Check camera system status',
            priority: 'Normal',
            dueDate: '4 days left',
            completed: false
        },
    ]);

    const stats = {
        activeMembers: 150,
        todayCheckIns: recentEvents?.filter(e => {
            const date = new Date(e.timestamp);
            const today = new Date();
            return date.getDate() === today.getDate() &&
                date.getMonth() === today.getMonth() &&
                date.getFullYear() === today.getFullYear();
        }).length || 0,
        monthlyRevenue: 12500,
    };

    const currentDate = format(new Date(), 'EEE, MMMM d');
    const currentUser = 'Admin'; // This should come from auth context

    const toggleTask = (taskId: string, section: 'inProgress' | 'todo') => {
        if (section === 'inProgress') {
            setInProgressTasks(tasks =>
                tasks.map(t => t.id === taskId ? { ...t, completed: !t.completed } : t)
            );
        } else {
            setTodoTasks(tasks =>
                tasks.map(t => t.id === taskId ? { ...t, completed: !t.completed } : t)
            );
        }
    };

    const getPriorityColor = (priority: string) => {
        switch (priority) {
            case 'High':
                return {
                    bg: 'var(--status-high)',
                    color: 'var(--status-high-text)',
                };
            case 'Normal':
                return {
                    bg: 'var(--status-normal)',
                    color: 'var(--status-normal-text)',
                };
            case 'Low':
                return {
                    bg: 'var(--status-low)',
                    color: 'var(--status-low-text)',
                };
            default:
                return {
                    bg: 'var(--status-low)',
                    color: 'var(--status-low-text)',
                };
        }
    };

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
                    Hello, {currentUser}
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
                {/* Tasks Section */}
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
                        {/* Tasks Header */}
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
                            <CheckCircleIcon sx={{ mr: 1.5, color: 'var(--accent-purple)' }} />
                            <Typography variant="h6" sx={{ fontWeight: 600 }}>
                                My Tasks
                            </Typography>
                        </Box>

                        {/* In Progress Section */}
                        <Box sx={{ mb: 3 }}>
                            <Box
                                sx={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    mb: 2,
                                    cursor: 'pointer',
                                    '&:hover': { opacity: 0.8 },
                                }}
                                onClick={() => setInProgressExpanded(!inProgressExpanded)}
                            >
                                <IconButton size="small" sx={{ mr: 1 }}>
                                    {inProgressExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                </IconButton>
                                <Chip
                                    label="IN PROGRESS"
                                    size="small"
                                    sx={{
                                        background: 'var(--status-progress)',
                                        color: 'var(--status-progress-text)',
                                        fontWeight: 600,
                                        fontSize: '0.7rem',
                                        mr: 1.5,
                                    }}
                                />
                                <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                                    • {inProgressTasks.length} tasks
                                </Typography>
                            </Box>

                            <Collapse in={inProgressExpanded}>
                                <Box>
                                    {/* Table Header */}
                                    <Box
                                        sx={{
                                            display: 'grid',
                                            gridTemplateColumns: '1fr 120px 120px',
                                            gap: 2,
                                            px: 2,
                                            py: 1,
                                            borderBottom: '1px solid var(--border-color)',
                                        }}
                                    >
                                        <Typography variant="caption" sx={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                            Name
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                            Priority
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                            Due date
                                        </Typography>
                                    </Box>

                                    {/* Task Items */}
                                    {inProgressTasks.map((task) => (
                                        <Box
                                            key={task.id}
                                            sx={{
                                                display: 'grid',
                                                gridTemplateColumns: '1fr 120px 120px',
                                                gap: 2,
                                                px: 2,
                                                py: 2,
                                                alignItems: 'center',
                                                borderBottom: '1px solid var(--border-color)',
                                                transition: 'var(--transition-base)',
                                                '&:hover': {
                                                    background: 'var(--bg-primary)',
                                                },
                                            }}
                                        >
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                                <Checkbox
                                                    checked={task.completed}
                                                    onChange={() => toggleTask(task.id, 'inProgress')}
                                                    size="small"
                                                    sx={{
                                                        color: 'var(--accent-cyan)',
                                                        '&.Mui-checked': {
                                                            color: 'var(--accent-cyan)',
                                                        },
                                                    }}
                                                />
                                                <Typography
                                                    variant="body2"
                                                    sx={{
                                                        fontWeight: 500,
                                                        textDecoration: task.completed ? 'line-through' : 'none',
                                                        color: task.completed ? 'var(--text-muted)' : 'var(--text-primary)',
                                                    }}
                                                >
                                                    {task.name}
                                                </Typography>
                                            </Box>
                                            <Chip
                                                label={task.priority}
                                                size="small"
                                                sx={{
                                                    background: getPriorityColor(task.priority).bg,
                                                    color: getPriorityColor(task.priority).color,
                                                    fontWeight: 600,
                                                    fontSize: '0.75rem',
                                                }}
                                            />
                                            <Typography
                                                variant="body2"
                                                sx={{
                                                    color: task.dueDate === 'Today' ? 'var(--status-high-text)' : 'var(--text-secondary)',
                                                    fontWeight: task.dueDate === 'Today' ? 600 : 400,
                                                }}
                                            >
                                                {task.dueDate}
                                            </Typography>
                                        </Box>
                                    ))}

                                    <Button
                                        startIcon={<AddIcon />}
                                        sx={{
                                            mt: 2,
                                            color: 'var(--text-secondary)',
                                            textTransform: 'none',
                                            fontWeight: 500,
                                            '&:hover': {
                                                background: 'var(--bg-primary)',
                                            },
                                        }}
                                    >
                                        Add task
                                    </Button>
                                </Box>
                            </Collapse>
                        </Box>

                        {/* To Do Section */}
                        <Box>
                            <Box
                                sx={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    mb: 2,
                                    cursor: 'pointer',
                                    '&:hover': { opacity: 0.8 },
                                }}
                                onClick={() => setTodoExpanded(!todoExpanded)}
                            >
                                <IconButton size="small" sx={{ mr: 1 }}>
                                    {todoExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                                </IconButton>
                                <Chip
                                    label="TO DO"
                                    size="small"
                                    sx={{
                                        background: 'var(--status-low)',
                                        color: 'var(--text-secondary)',
                                        fontWeight: 600,
                                        fontSize: '0.7rem',
                                        mr: 1.5,
                                    }}
                                />
                                <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                                    • {todoTasks.length} task
                                </Typography>
                            </Box>

                            <Collapse in={todoExpanded}>
                                <Box>
                                    {/* Table Header */}
                                    <Box
                                        sx={{
                                            display: 'grid',
                                            gridTemplateColumns: '1fr 120px 120px',
                                            gap: 2,
                                            px: 2,
                                            py: 1,
                                            borderBottom: '1px solid var(--border-color)',
                                        }}
                                    >
                                        <Typography variant="caption" sx={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                            Name
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                            Priority
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: 'var(--text-muted)', fontWeight: 600 }}>
                                            Due date
                                        </Typography>
                                    </Box>

                                    {/* Task Items */}
                                    {todoTasks.map((task) => (
                                        <Box
                                            key={task.id}
                                            sx={{
                                                display: 'grid',
                                                gridTemplateColumns: '1fr 120px 120px',
                                                gap: 2,
                                                px: 2,
                                                py: 2,
                                                alignItems: 'center',
                                                borderBottom: '1px solid var(--border-color)',
                                                transition: 'var(--transition-base)',
                                                '&:hover': {
                                                    background: 'var(--bg-primary)',
                                                },
                                            }}
                                        >
                                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                                <Checkbox
                                                    checked={task.completed}
                                                    onChange={() => toggleTask(task.id, 'todo')}
                                                    size="small"
                                                    sx={{
                                                        color: 'var(--accent-cyan)',
                                                        '&.Mui-checked': {
                                                            color: 'var(--accent-cyan)',
                                                        },
                                                    }}
                                                />
                                                <Typography
                                                    variant="body2"
                                                    sx={{
                                                        fontWeight: 500,
                                                        textDecoration: task.completed ? 'line-through' : 'none',
                                                        color: task.completed ? 'var(--text-muted)' : 'var(--text-primary)',
                                                    }}
                                                >
                                                    {task.name}
                                                </Typography>
                                            </Box>
                                            <Chip
                                                label={task.priority}
                                                size="small"
                                                sx={{
                                                    background: getPriorityColor(task.priority).bg,
                                                    color: getPriorityColor(task.priority).color,
                                                    fontWeight: 600,
                                                    fontSize: '0.75rem',
                                                }}
                                            />
                                            <Typography
                                                variant="body2"
                                                sx={{
                                                    color: 'var(--text-secondary)',
                                                }}
                                            >
                                                {task.dueDate}
                                            </Typography>
                                        </Box>
                                    ))}

                                    <Button
                                        startIcon={<AddIcon />}
                                        sx={{
                                            mt: 2,
                                            color: 'var(--text-secondary)',
                                            textTransform: 'none',
                                            fontWeight: 500,
                                            '&:hover': {
                                                background: 'var(--bg-primary)',
                                            },
                                        }}
                                    >
                                        Add task
                                    </Button>
                                </Box>
                            </Collapse>
                        </Box>
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
