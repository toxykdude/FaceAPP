/**
 * Dashboard page component - Modern task management interface
 */
import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
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
    Tooltip,
    useMediaQuery,
    useTheme,
} from "@mui/material";
import {
    PersonAdd as PersonAddIcon,
    Videocam as VideocamIcon,
    Assessment as AssessmentIcon,
    Schedule as ScheduleIcon,
    Warning as WarningIcon,
    CheckCircle as CheckCircleIcon,
} from "@mui/icons-material";
import { eventsApi } from "@/api/events";
import { membersApi } from "@/api/members";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/i18n/LanguageContext";
import { format } from "date-fns";
import {
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Card,
    CardHeader,
    CardContent,
} from "@mui/material";
import {
    OpenInNew as OpenInNewIcon,
} from "@mui/icons-material";
import { camerasApi } from "@/api/cameras";
import { membershipsApi } from "@/api/memberships";
import { salesApi } from '@/api/sales';
import { cvServiceApi } from "@/api/cvService";

export const Dashboard: React.FC = () => {
    const navigate = useNavigate();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const { user } = useAuth();
    const { t } = useLanguage();

    const { data: recentEvents } = useQuery({
        queryKey: ["recent-events"],
        queryFn: () => eventsApi.getRecentEvents(5),
        retry: false,
    });

    const { data: membersData } = useQuery({
        queryKey: ["members-stats"],
        queryFn: () => membersApi.getMembers({ limit: 1 }),
    });

    const { data: salesReport } = useQuery({
        queryKey: ['sales-report-summary'],
        queryFn: () => salesApi.getReportSummary(),
    });

    const { data: expiredMemberships } = useQuery({
        queryKey: ["expired-memberships"],
        queryFn: async () => {
            const response = await membershipsApi.getMemberships(0, 20, undefined, "expired");
            return response;
        },
        staleTime: 1000 * 60 * 60,
    });

    const { data: recognizedData } = useQuery({
        queryKey: ["today-recognized"],
        queryFn: () => eventsApi.getTodayRecognized(),
        refetchInterval: 30000,
    });

    const recognized = recognizedData?.recognized || [];
    const recognizedActive = recognized.filter((r: any) => r.membership_status === "active");
    const recognizedExpired = recognized.filter((r: any) => r.membership_status === "expired");

    // Camera Widget Logic
    const [selectedCam, setSelectedCam] = useState("");

    const { data: camerasData } = useQuery({
        queryKey: ["cameras"],
        queryFn: () => camerasApi.getCameras(),
    });

    useEffect(() => {
        if (camerasData?.length && !selectedCam) {
            setSelectedCam(camerasData[0].id);
        }
    }, [camerasData]);

    const handleOpenKiosk = () => {
        window.open(`/kiosk?cameraId=${selectedCam}`, "PowerHouseKiosk", "width=1000,height=800");
    };

    const handleCamChange = (e: any) => {
        setSelectedCam(e.target.value);
    };

    const stats = {
        activeMembers: membersData?.total || 0,
        todayCheckIns: recognizedActive.length + recognizedExpired.length,
        monthlyRevenue: Number(salesReport?.total_revenue || 0),
    };

    const currentDate = format(new Date(), "EEE, MMMM d");

    const MemberTooltip: React.FC<{ member: any; children: React.ReactElement }> = ({ member, children }) => {
        const [photoUrl, setPhotoUrl] = React.useState<string | null>(null);

        React.useEffect(() => {
            if (member.member_id) {
                setPhotoUrl(`/api/members/${member.member_id}/photo?t=${Date.now()}`);
            }
        }, [member.member_id]);

        const isActive = member.membership_status === 'active';

        return (
            <Tooltip
                placement="left"
                componentsProps={{
                    tooltip: {
                        sx: {
                            bgcolor: '#1e1e1e',
                            border: '1px solid #333',
                            borderRadius: 2,
                            p: 2,
                            maxWidth: 280,
                        }
                    }
                }}
                title={
                    <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                        <Avatar
                            src={photoUrl || undefined}
                            sx={{
                                width: 56,
                                height: 56,
                                bgcolor: '#444',
                                fontSize: '1.2rem',
                            }}
                        >
                            {member.member_name?.split(' ').map((n: string) => n[0]).join('').substring(0, 2)}
                        </Avatar>
                        <Box>
                            <Typography variant="subtitle2" sx={{ color: 'white', fontWeight: 'bold' }}>
                                {member.member_name}
                            </Typography>
                            {member.membership_plan && (
                                <Typography variant="caption" sx={{ color: '#aaa' }}>
                                    {member.membership_plan}
                                </Typography>
                            )}
                            {member.membership_end && (
                                <Box display="flex" alignItems="center" gap={0.5} mt={0.5}>
                                    {isActive ? (
                                        <Typography variant="caption" sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                                            ✅ {t.dashboard.activeUntil} {format(new Date(member.membership_end), 'MMM d, yyyy')}
                                        </Typography>
                                    ) : (
                                        <Typography variant="caption" sx={{ color: '#f44336', fontWeight: 'bold' }}>
                                            ❌ {t.dashboard.expiredOn} {format(new Date(member.membership_end), 'MMM d, yyyy')}
                                        </Typography>
                                    )}
                                </Box>
                            )}
                        </Box>
                    </Box>
                }
            >
                {children}
            </Tooltip>
        );
    };

    return (
        <Box
            sx={{
                maxWidth: "1400px",
                margin: "0 auto",
                padding: { xs: 2, sm: 3, md: 4 },
            }}
        >
            {/* Header Section */}
            <Box sx={{ mb: { xs: 2, md: 4 } }}>
                <Typography
                    variant="body2"
                    sx={{
                        color: "var(--text-secondary)",
                        mb: 0.5,
                        fontWeight: 500,
                    }}
                >
                    {currentDate}
                </Typography>
                <Typography
                    variant={isMobile ? "h5" : "h3"}
                    sx={{
                        fontWeight: 800,
                        color: "var(--text-primary)",
                        mb: 0.5,
                    }}
                >
                    {t.dashboard.title.replace('{name}', user?.username || 'Admin')}
                </Typography>
                <Typography
                    variant={isMobile ? "h6" : "h4"}
                    className="gradient-text"
                    sx={{
                        fontWeight: 700,
                    }}
                >
                    {t.dashboard.subtitle}
                </Typography>
            </Box>

            {/* Main Content */}
            <Box sx={{ display: "flex", gap: { xs: 2, md: 3 }, flexDirection: { xs: "column", lg: "row" } }}>
                {/* Quick Actions Section */}
                <Box sx={{ flex: 1 }}>
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 },
                            borderRadius: "var(--radius-xl)",
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-secondary)",
                        }}
                    >
                        <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, fontSize: { xs: '1rem', md: '1.25rem' } }}>
                            {t.dashboard.quickActions}
                        </Typography>
                        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                            <Button
                                variant="outlined"
                                startIcon={<PersonAddIcon />}
                                onClick={() => navigate("/members/new")}
                                sx={{
                                    justifyContent: "flex-start",
                                    p: 1.5,
                                    borderRadius: "var(--radius-lg)",
                                    textTransform: "none",
                                    borderColor: "var(--border-color)",
                                    minHeight: 44,
                                }}
                            >
                                {t.dashboard.addMember}
                            </Button>
                            <Button
                                variant="outlined"
                                startIcon={<VideocamIcon />}
                                onClick={() => navigate("/cameras")}
                                sx={{
                                    justifyContent: "flex-start",
                                    p: 1.5,
                                    borderRadius: "var(--radius-lg)",
                                    textTransform: "none",
                                    borderColor: "var(--border-color)",
                                    minHeight: 44,
                                }}
                            >
                                {t.dashboard.viewCameras}
                            </Button>
                            <Button
                                variant="outlined"
                                startIcon={<AssessmentIcon />}
                                onClick={() => navigate("/reports")}
                                sx={{
                                    justifyContent: "flex-start",
                                    p: 1.5,
                                    borderRadius: "var(--radius-lg)",
                                    textTransform: "none",
                                    borderColor: "var(--border-color)",
                                    minHeight: 44,
                                }}
                            >
                                {t.dashboard.viewReports}
                            </Button>
                        </Box>
                    </Paper>

                    {/* Expired Memberships Widget */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 },
                            mt: { xs: 2, md: 3 },
                            borderRadius: "var(--radius-xl)",
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-secondary)",
                        }}
                    >
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <WarningIcon sx={{ mr: 1.5, color: "#f44336" }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, fontSize: { xs: '1rem', md: '1.25rem' } }}>{t.dashboard.expiredMemberships}</Typography>
                            </Box>
                            <Button size="small" onClick={() => navigate("/memberships")}>{t.dashboard.viewAll}</Button>
                        </Box>
                        <TableContainer sx={{ overflowX: 'auto' }}>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t.dashboard.member}</TableCell>
                                        <TableCell>{t.dashboard.plan}</TableCell>
                                        <TableCell>{t.dashboard.expired}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {[...(expiredMemberships || [])]
                                        .sort((a: any, b: any) => new Date(b.end_date).getTime() - new Date(a.end_date).getTime())
                                        .slice(0, 20)
                                        .map((m: any) => (
                                            <MemberTooltip key={m.id} member={{
                                                member_id: m.member_id,
                                                member_name: m.member_name,
                                                membership_plan: m.plan_name,
                                                membership_end: m.end_date,
                                                membership_status: "expired",
                                            }}>
                                            <TableRow
                                                hover
                                                onClick={() => navigate(`/members/${m.member_id}`)}
                                                sx={{ cursor: "pointer" }}
                                            >
                                                <TableCell>{m.member_name || t.dashboard.unknown}</TableCell>
                                                <TableCell>{m.plan_name || m.type}</TableCell>
                                                <TableCell>{format(new Date(m.end_date), "MMM d, yyyy")}</TableCell>
                                            </TableRow>
                                            </MemberTooltip>
                                        ))}
                                    {(!expiredMemberships || expiredMemberships.length === 0) && (
                                        <TableRow>
                                            <TableCell colSpan={3} align="center">{t.dashboard.noExpired}</TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>

                    {/* Today Check-ins - Active */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 },
                            mt: { xs: 2, md: 3 },
                            borderRadius: "var(--radius-xl)",
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-secondary)",
                        }}
                    >
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <CheckCircleIcon sx={{ mr: 1.5, color: "#4caf50" }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, fontSize: { xs: '1rem', md: '1.25rem' } }}>{t.dashboard.todayCheckinsActive}</Typography>
                            </Box>
                            <Chip label={recognizedActive.length} color="success" size="small" />
                        </Box>
                        <TableContainer sx={{ overflowX: 'auto' }}>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t.dashboard.member}</TableCell>
                                        <TableCell>{t.dashboard.plan}</TableCell>
                                        <TableCell>{t.dashboard.expires}</TableCell>
                                        <TableCell>{t.dashboard.lastSeen}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {recognizedActive.map((r: any) => (
                                        <MemberTooltip key={r.member_id} member={r}>
                                        <TableRow
                                            hover
                                            onClick={() => navigate(`/members/${r.member_id}`)}
                                            sx={{ cursor: "pointer" }}
                                        >
                                            <TableCell>{r.member_name}</TableCell>
                                            <TableCell>{r.membership_plan || "-"}</TableCell>
                                            <TableCell>
                                                {r.membership_end ? format(new Date(r.membership_end), "MMM d, yyyy") : "-"}
                                            </TableCell>
                                            <TableCell>
                                                {r.last_seen ? format(new Date(r.last_seen), "h:mm a") : "-"}
                                            </TableCell>
                                        </TableRow>
                                        </MemberTooltip>
                                    ))}
                                    {recognizedActive.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center">{t.dashboard.noActive}</TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>

                    {/* Today Check-ins - Expired */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 },
                            mt: { xs: 2, md: 3 },
                            borderRadius: "var(--radius-xl)",
                            border: "1px solid #ff9800",
                            background: "#fff8e1",
                        }}
                    >
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <WarningIcon sx={{ mr: 1.5, color: "#f44336" }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, color: "#e65100", fontSize: { xs: '1rem', md: '1.25rem' } }}>
                                    {t.dashboard.todayCheckinsExpired}
                                </Typography>
                            </Box>
                            <Chip label={recognizedExpired.length} color="error" size="small" />
                        </Box>
                        <TableContainer sx={{ overflowX: 'auto' }}>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>{t.dashboard.member}</TableCell>
                                        <TableCell>{t.dashboard.plan}</TableCell>
                                        <TableCell>{t.dashboard.expired}</TableCell>
                                        <TableCell>{t.dashboard.lastSeen}</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {recognizedExpired.map((r: any) => (
                                        <MemberTooltip key={r.member_id} member={r}>
                                        <TableRow
                                            hover
                                            onClick={() => navigate(`/members/${r.member_id}`)}
                                            sx={{ cursor: "pointer" }}
                                        >
                                            <TableCell>{r.member_name}</TableCell>
                                            <TableCell>{r.membership_plan || "-"}</TableCell>
                                            <TableCell sx={{ color: "#f44336", fontWeight: "bold" }}>
                                                {r.membership_end ? format(new Date(r.membership_end), "MMM d, yyyy") : "-"}
                                            </TableCell>
                                            <TableCell>
                                                {r.last_seen ? format(new Date(r.last_seen), "h:mm a") : "-"}
                                            </TableCell>
                                        </TableRow>
                                        </MemberTooltip>
                                    ))}
                                    {recognizedExpired.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center">{t.dashboard.noActiveCheckins}</TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>
                </Box>

                {/* Stats & Quick Actions Sidebar */}
                <Box sx={{ width: { xs: "100%", lg: "320px" } }}>
                    {/* Live Feed Widget */}
                    <Card sx={{ mb: { xs: 2, md: 3 }, borderRadius: "var(--radius-xl)", border: "1px solid var(--border-color)" }}>
                        <CardHeader
                            title={t.dashboard.liveAccessMonitor}
                            avatar={<VideocamIcon color="primary" />}
                            action={
                                <IconButton onClick={handleOpenKiosk} title="Detach Window" sx={{ minWidth: 44, minHeight: 44 }}>
                                    <OpenInNewIcon />
                                </IconButton>
                            }
                            titleTypographyProps={{ fontSize: { xs: '0.95rem', md: '1.25rem' } }}
                        />
                        <CardContent>
                            <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                                <InputLabel>{t.dashboard.camera}</InputLabel>
                                <Select value={selectedCam} label={t.dashboard.camera} onChange={handleCamChange}>
                                    {camerasData?.map((cam: any) => (
                                        <MenuItem key={cam.id} value={cam.id}>{cam.name}</MenuItem>
                                    ))}
                                </Select>
                            </FormControl>

                            <Box
                                sx={{
                                    width: "100%",
                                    aspectRatio: "16/9",
                                    bgcolor: "black",
                                    borderRadius: 1,
                                    overflow: "hidden",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                }}
                            >
                                {selectedCam ? (
                                    <img
                                        src={cvServiceApi.getStreamUrl(selectedCam)}
                                        style={{ width: "100%", height: "100%", objectFit: "contain" }}
                                        alt="Live Feed"
                                    />
                                ) : (
                                    <Typography variant="body2" color="grey.500">{t.dashboard.selectCamera}</Typography>
                                )}
                            </Box>
                        </CardContent>
                    </Card>

                    {/* Quick Stats */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 },
                            mb: { xs: 2, md: 3 },
                            borderRadius: "var(--radius-xl)",
                            border: "1px solid var(--border-color)",
                            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
                            color: "white",
                            position: "relative",
                            overflow: "hidden",
                        }}
                    >
                        <Box
                            sx={{
                                position: "absolute",
                                top: -20,
                                right: -20,
                                width: 100,
                                height: 100,
                                borderRadius: "50%",
                                background: "rgba(255, 255, 255, 0.1)",
                            }}
                        />
                        <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, position: "relative", fontSize: { xs: '1rem', md: '1.25rem' } }}>
                            {t.dashboard.quickStats}
                        </Typography>
                        <Box sx={{ position: "relative" }}>
                            <Box sx={{ mb: 2 }}>
                                <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>
                                    {t.dashboard.activeMembers}
                                </Typography>
                                <Typography variant={isMobile ? "h5" : "h4"} sx={{ fontWeight: 700 }}>
                                    {stats.activeMembers}
                                </Typography>
                            </Box>
                            <Box sx={{ mb: 2 }}>
                                <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>
                                    {t.dashboard.todayCheckins}
                                </Typography>
                                <Typography variant={isMobile ? "h5" : "h4"} sx={{ fontWeight: 700 }}>
                                    {stats.todayCheckIns}
                                </Typography>
                            </Box>
                            <Box>
                                <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>
                                    {t.dashboard.monthlyRevenue}
                                </Typography>
                                <Typography variant={isMobile ? "h5" : "h4"} sx={{ fontWeight: 700 }}>
                                    ${stats.monthlyRevenue.toLocaleString()}
                                </Typography>
                            </Box>
                        </Box>
                    </Paper>

                    {/* Recent Activity */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 },
                            borderRadius: "var(--radius-xl)",
                            border: "1px solid var(--border-color)",
                            background: "var(--bg-secondary)",
                        }}
                    >
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                            <ScheduleIcon sx={{ mr: 1.5, color: "var(--accent-cyan)" }} />
                            <Typography variant="h6" sx={{ fontWeight: 600, fontSize: { xs: '1rem', md: '1.25rem' } }}>
                                {t.dashboard.recentActivity}
                            </Typography>
                        </Box>
                        <Box>
                            {recentEvents?.slice(0, 3).map((event, index) => (
                                <Box
                                    key={event.id}
                                    sx={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 2,
                                        py: 2,
                                        borderBottom: index < 2 ? "1px solid var(--border-color)" : "none",
                                    }}
                                >
                                    <Avatar
                                        sx={{
                                            width: 40,
                                            height: 40,
                                            background: "var(--primary-gradient)",
                                        }}
                                    >
                                        {event.member_name?.[0] || "M"}
                                    </Avatar>
                                    <Box sx={{ flex: 1, minWidth: 0 }}>
                                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                            {event.member_name || (event?.member_id ? `${t.dashboard.member} ${event.member_id.substring(0, 8)}` : t.dashboard.unknown)}
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: "var(--text-secondary)" }}>
                                            {event.event_type} • {event.timestamp ? format(new Date(event.timestamp), "h:mm a") : ""}
                                        </Typography>
                                    </Box>
                                    <Chip
                                        label={`${(event.confidence * 100).toFixed(0)}%`}
                                        size="small"
                                        sx={{
                                            background: "var(--status-progress)",
                                            color: "var(--status-progress-text)",
                                            fontWeight: 600,
                                        }}
                                    />
                                </Box>
                            ))}
                            {(!recentEvents || recentEvents.length === 0) && (
                                <Typography variant="body2" sx={{ color: "var(--text-secondary)", py: 2 }}>
                                    {t.dashboard.noActivity}
                                </Typography>
                            )}
                        </Box>
                    </Paper>
                </Box>
            </Box>
        </Box>
    );
};
