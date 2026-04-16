/**
 * Dashboard page component — Theme-aware (light + dark mode)
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
    alpha,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    Card,
    CardHeader,
    CardContent,
} from "@mui/material";
import {
    PersonAdd as PersonAddIcon,
    Videocam as VideocamIcon,
    Assessment as AssessmentIcon,
    Schedule as ScheduleIcon,
    Warning as WarningIcon,
    CheckCircle as CheckCircleIcon,
    OpenInNew as OpenInNewIcon,
} from "@mui/icons-material";
import { eventsApi } from "@/api/events";
import { membersApi } from "@/api/members";
import { useAuth } from "@/contexts/AuthContext";
import { useLanguage } from "@/i18n/LanguageContext";
import { format } from "date-fns";
import { camerasApi } from "@/api/cameras";
import { salesApi } from '@/api/sales';
import { cvServiceApi } from "@/api/cvService";

export const Dashboard: React.FC = () => {
    const navigate = useNavigate();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const isDark = theme.palette.mode === 'dark';
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

    const { data: expiringTodayData } = useQuery({
        queryKey: ["expiring-today"],
        queryFn: () => eventsApi.getExpiringToday(20),
        staleTime: 1000 * 60 * 30,
    });
    const expiringToday = expiringTodayData?.expiring || [];

    const hasReportsAccess = user?.role === 'admin' || user?.permissions?.pages?.includes('all') || user?.permissions?.pages?.includes('reports');

    const { data: recognizedData } = useQuery({
        queryKey: ["today-recognized"],
        queryFn: () => eventsApi.getTodayRecognized(),
        refetchInterval: 30000,
    });

    const recognized = recognizedData?.recognized || [];
    const recognizedActive = recognized.filter((r: any) => r.membership_status === "active");
    const recognizedExpired = recognized.filter((r: any) => r.membership_status === "expired");

    // Camera Widget
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

    const stats = {
        activeMembers: membersData?.total || 0,
        todayCheckIns: recognizedActive.length + recognizedExpired.length,
        monthlyRevenue: Number(salesReport?.total_revenue || 0),
    };

    const currentDate = format(new Date(), "EEE, MMMM d");

    // Theme-aware colors
    const paperBg = theme.palette.background.paper;
    const borderColor = isDark ? alpha(theme.palette.divider, 0.12) : theme.palette.divider;
    const successMain = theme.palette.success.main;
    const warningMain = theme.palette.warning.main;
    const errorMain = theme.palette.error.main;
    const textSecondary = theme.palette.text.secondary;

    // Warning panel colors (theme-aware)
    const warnBg = isDark
        ? alpha(theme.palette.warning.dark, 0.15)
        : alpha(theme.palette.warning.light, 0.3);
    const warnBorder = isDark
        ? alpha(theme.palette.warning.main, 0.4)
        : theme.palette.warning.main;
    const warnHeaderText = isDark
        ? theme.palette.warning.light
        : theme.palette.warning.dark;

    const MemberTooltip: React.FC<{ member: any; children: React.ReactElement }> = ({ member, children }) => {
        const [photoUrl, setPhotoUrl] = React.useState<string | null>(null);

        React.useEffect(() => {
            if (member.member_id) {
                setPhotoUrl(`/api/members/${member.member_id}/photo?t=${Date.now()}`);
            }
        }, [member.member_id]);

        const isActive = member.membership_status === 'active';
        const tooltipBg = isDark ? '#1a1a2e' : '#1e1e1e';

        return (
            <Tooltip
                placement="left"
                componentsProps={{
                    tooltip: {
                        sx: {
                            bgcolor: tooltipBg,
                            border: `1px solid ${isDark ? '#3a3a5a' : '#333'}`,
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
                                bgcolor: isDark ? '#3a3a5a' : '#444',
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
                                    <Typography variant="caption" sx={{ color: isActive ? '#4caf50' : '#f44336', fontWeight: 'bold' }}>
                                        {isActive ? 'Activa hasta' : 'Vencida'} {format(new Date(member.membership_end), 'MMM d, yyyy')}
                                    </Typography>
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
        <Box sx={{ maxWidth: "1400px", margin: "0 auto", padding: { xs: 2, sm: 3, md: 4 } }}>
            {/* Header */}
            <Paper
                elevation={0}
                sx={{
                    mb: { xs: 2, md: 4 },
                    borderRadius: 3,
                    border: `1px solid ${borderColor}`,
                    bgcolor: paperBg,
                    overflow: 'hidden',
                    position: 'relative',
                }}
            >
                <Box
                    sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: { xs: 2, md: 3 },
                        p: { xs: 2, md: 3 },
                        background: isDark
                            ? `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.15)} 0%, ${alpha(theme.palette.secondary.dark, 0.1)} 100%)`
                            : `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.05)} 0%, ${alpha(theme.palette.secondary.main, 0.05)} 100%)`,
                    }}
                >
                    <Box
                        component="img"
                        src="/logo.png"
                        alt="PowerHouse GYM"
                        sx={{
                            width: { xs: 56, md: 72 },
                            height: { xs: 56, md: 72 },
                            borderRadius: 2,
                            objectFit: 'contain',
                            flexShrink: 0,
                        }}
                    />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography
                            variant={isMobile ? "h6" : "h4"}
                            sx={{
                                fontWeight: 800,
                                letterSpacing: '-0.02em',
                                lineHeight: 1.2,
                                mb: 0.5,
                                background: isDark
                                    ? `linear-gradient(135deg, ${theme.palette.primary.light}, ${theme.palette.secondary.light})`
                                    : `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
                                WebkitBackgroundClip: 'text',
                                WebkitTextFillColor: 'transparent',
                                backgroundClip: 'text',
                            }}
                        >
                            Sistema Biometrico con Reconocimiento Facial
                        </Typography>
                        <Typography
                            variant={isMobile ? "subtitle1" : "h5"}
                            sx={{
                                fontWeight: 700,
                                color: isDark ? theme.palette.warning.light : theme.palette.warning.dark,
                                letterSpacing: '0.05em',
                                textTransform: 'uppercase',
                            }}
                        >
                            PowerHouse GYM
                        </Typography>
                    </Box>
                    <Typography
                        variant="body2"
                        sx={{
                            color: textSecondary,
                            fontWeight: 500,
                            display: { xs: 'none', sm: 'block' },
                            textAlign: 'right',
                            flexShrink: 0,
                        }}
                    >
                        {currentDate}
                    </Typography>
                </Box>
            </Paper>

            {/* Main Layout */}
            <Box sx={{ display: "flex", gap: { xs: 2, md: 3 }, flexDirection: { xs: "column", lg: "row" } }}>

                {/* LEFT COLUMN */}
                <Box sx={{ flex: 1 }}>

                    {/* Quick Actions */}
                    <Paper elevation={0} sx={{ p: { xs: 2, md: 3 }, borderRadius: 3, border: `1px solid ${borderColor}`, bgcolor: paperBg }}>
                        <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, fontSize: { xs: '1rem', md: '1.25rem' } }}>
                            {t.dashboard.quickActions}
                        </Typography>
                        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                            {[
                                { icon: <PersonAddIcon />, label: t.dashboard.addMember, path: "/members/new" },
                                { icon: <VideocamIcon />, label: t.dashboard.viewCameras, path: "/cameras" },
                                { icon: <AssessmentIcon />, label: t.dashboard.viewReports, path: "/reports" },
                            ].map((action) => (
                                <Button
                                    key={action.path}
                                    variant="outlined"
                                    startIcon={action.icon}
                                    onClick={() => navigate(action.path)}
                                    sx={{
                                        justifyContent: "flex-start",
                                        p: 1.5,
                                        borderRadius: 2,
                                        textTransform: "none",
                                        borderColor: borderColor,
                                        minHeight: 44,
                                        color: 'text.primary',
                                        '&:hover': { borderColor: 'primary.main', bgcolor: alpha(theme.palette.primary.main, 0.05) },
                                    }}
                                >
                                    {action.label}
                                </Button>
                            ))}
                        </Box>
                    </Paper>

                    {/* Expiring Today — Dynamic Daily */}
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 }, mt: { xs: 2, md: 3 }, borderRadius: 3,
                            border: `1px solid ${expiringToday.length > 0 ? warnBorder : borderColor}`,
                            bgcolor: expiringToday.length > 0 ? warnBg : paperBg,
                        }}
                    >
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <WarningIcon sx={{ mr: 1.5, color: expiringToday.length > 0 ? errorMain : textSecondary }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, fontSize: { xs: '1rem', md: '1.25rem' }, color: expiringToday.length > 0 ? warnHeaderText : 'text.primary' }}>
                                    Membresias Vencidas Hoy
                                </Typography>
                            </Box>
                            <Chip label={expiringToday.length} color={expiringToday.length > 0 ? "warning" : "default"} size="small" />
                        </Box>
                        <TableContainer sx={{ overflowX: 'auto' }}>
                            <Table size="small">
                                <TableHead>
                                    <TableRow>
                                        <TableCell>Miembro</TableCell>
                                        <TableCell>Plan</TableCell>
                                        <TableCell>Vencio</TableCell>
                                        <TableCell>Dias</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {expiringToday.map((m: any) => (
                                        <TableRow key={m.member_id + m.end_date} hover onClick={() => navigate(`/members/${m.member_id}`)} sx={{ cursor: "pointer" }}>
                                            <TableCell>{m.member_name}</TableCell>
                                            <TableCell>{m.plan_name || "-"}</TableCell>
                                            <TableCell sx={{ color: m.days_expired > 0 ? errorMain : warningMain, fontWeight: "bold" }}>
                                                {format(new Date(m.end_date), "MMM d")}
                                            </TableCell>
                                            <TableCell>
                                                <Chip
                                                    label={m.days_expired === 0 ? "Hoy" : `${m.days_expired}d`}
                                                    color={m.days_expired === 0 ? "warning" : "error"}
                                                    size="small"
                                                />
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                    {expiringToday.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center" sx={{ py: 3, color: textSecondary }}>
                                                No hay membresias vencidas hoy
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>

                    {/* Today Check-ins — Active */}
                    <Paper elevation={0} sx={{ p: { xs: 2, md: 3 }, mt: { xs: 2, md: 3 }, borderRadius: 3, border: `1px solid ${borderColor}`, bgcolor: paperBg }}>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <CheckCircleIcon sx={{ mr: 1.5, color: successMain }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, fontSize: { xs: '1rem', md: '1.25rem' } }}>
                                    {t.dashboard.todayCheckinsActive}
                                </Typography>
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
                                            <TableRow hover onClick={() => navigate(`/members/${r.member_id}`)} sx={{ cursor: "pointer" }}>
                                                <TableCell>{r.member_name}</TableCell>
                                                <TableCell>{r.membership_plan || "-"}</TableCell>
                                                <TableCell sx={{ color: successMain }}>
                                                    {r.membership_end ? format(new Date(r.membership_end), "MMM d, yyyy") : "-"}
                                                </TableCell>
                                                <TableCell>{r.last_seen ? format(new Date(r.last_seen), "h:mm a") : "-"}</TableCell>
                                            </TableRow>
                                        </MemberTooltip>
                                    ))}
                                    {recognizedActive.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center" sx={{ color: textSecondary }}>{t.dashboard.noActive}</TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>

                    {/* Today Check-ins — Expired */}
                    {recognizedExpired.length > 0 && (
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 }, mt: { xs: 2, md: 3 }, borderRadius: 3,
                            border: `1px solid ${warnBorder}`,
                            bgcolor: warnBg,
                        }}
                    >
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                            <Box display="flex" alignItems="center">
                                <WarningIcon sx={{ mr: 1.5, color: errorMain }} />
                                <Typography variant="h6" sx={{ fontWeight: 600, color: warnHeaderText, fontSize: { xs: '1rem', md: '1.25rem' } }}>
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
                                            <TableRow hover onClick={() => navigate(`/members/${r.member_id}`)} sx={{ cursor: "pointer" }}>
                                                <TableCell>{r.member_name}</TableCell>
                                                <TableCell>{r.membership_plan || "-"}</TableCell>
                                                <TableCell sx={{ color: errorMain, fontWeight: "bold" }}>
                                                    {r.membership_end ? format(new Date(r.membership_end), "MMM d, yyyy") : "-"}
                                                </TableCell>
                                                <TableCell>{r.last_seen ? format(new Date(r.last_seen), "h:mm a") : "-"}</TableCell>
                                            </TableRow>
                                        </MemberTooltip>
                                    ))}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    </Paper>
                    )}
                </Box>

                {/* RIGHT SIDEBAR */}
                <Box sx={{ width: { xs: "100%", lg: "320px" } }}>

                    {/* Live Feed Widget */}
                    <Card sx={{ mb: { xs: 2, md: 3 }, borderRadius: 3, border: `1px solid ${borderColor}` }}>
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
                                <Select value={selectedCam} label={t.dashboard.camera} onChange={(e) => setSelectedCam(e.target.value)}>
                                    {camerasData?.map((cam: any) => (
                                        <MenuItem key={cam.id} value={cam.id}>{cam.name}</MenuItem>
                                    ))}
                                </Select>
                            </FormControl>
                            <Box sx={{ width: "100%", aspectRatio: "16/9", bgcolor: "black", borderRadius: 1, overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                {selectedCam ? (
                                    <img src={cvServiceApi.getStreamUrl(selectedCam)} style={{ width: "100%", height: "100%", objectFit: "contain" }} alt="Live Feed" />
                                ) : (
                                    <Typography variant="body2" sx={{ color: 'grey.500' }}>{t.dashboard.selectCamera}</Typography>
                                )}
                            </Box>
                        </CardContent>
                    </Card>

                    {/* Quick Stats — Only with reports permission */}
                    {hasReportsAccess && (
                    <Paper
                        elevation={0}
                        sx={{
                            p: { xs: 2, md: 3 }, mb: { xs: 2, md: 3 }, borderRadius: 3,
                            border: `1px solid ${isDark ? alpha(theme.palette.primary.dark, 0.3) : alpha(theme.palette.primary.main, 0.2)}`,
                            background: isDark
                                ? `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.5)} 0%, ${alpha(theme.palette.secondary.dark, 0.5)} 100%)`
                                : `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
                            color: "white",
                            position: "relative",
                            overflow: "hidden",
                        }}
                    >
                        <Box sx={{ position: "absolute", top: -20, right: -20, width: 100, height: 100, borderRadius: "50%", background: "rgba(255, 255, 255, 0.1)" }} />
                        <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, position: "relative", fontSize: { xs: '1rem', md: '1.25rem' } }}>
                            {t.dashboard.quickStats}
                        </Typography>
                        <Box sx={{ position: "relative" }}>
                            {[
                                { label: t.dashboard.activeMembers, value: stats.activeMembers },
                                { label: t.dashboard.todayCheckins, value: stats.todayCheckIns },
                                { label: t.dashboard.monthlyRevenue, value: `$${stats.monthlyRevenue.toLocaleString()}` },
                            ].map((stat, i) => (
                                <Box key={i} sx={{ mb: 2 }}>
                                    <Typography variant="body2" sx={{ opacity: 0.9, mb: 0.5 }}>{stat.label}</Typography>
                                    <Typography variant={isMobile ? "h5" : "h4"} sx={{ fontWeight: 700 }}>{stat.value}</Typography>
                                </Box>
                            ))}
                        </Box>
                    </Paper>
                    )}

                    {/* Recent Activity */}
                    <Paper elevation={0} sx={{ p: { xs: 2, md: 3 }, borderRadius: 3, border: `1px solid ${borderColor}`, bgcolor: paperBg }}>
                        <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
                            <ScheduleIcon sx={{ mr: 1.5, color: theme.palette.info.main }} />
                            <Typography variant="h6" sx={{ fontWeight: 600, fontSize: { xs: '1rem', md: '1.25rem' } }}>
                                {t.dashboard.recentActivity}
                            </Typography>
                        </Box>
                        <Box>
                            {recentEvents?.slice(0, 3).map((event, index) => {
                                const conf = event.confidence ?? event.confidence_score ?? 0;
                                const granted = (event as any).access_granted;
                                return (
                                    <Box
                                        key={event.id}
                                        sx={{
                                            display: "flex", alignItems: "center", gap: 2, py: 2,
                                            borderBottom: index < Math.min(recentEvents.length - 1, 2) ? `1px solid ${borderColor}` : "none",
                                        }}
                                    >
                                        <Avatar sx={{ width: 40, height: 40, background: `linear-gradient(135deg, ${theme.palette.primary.main}, ${theme.palette.secondary.main})` }}>
                                            {(event.member_name || "M")[0]}
                                        </Avatar>
                                        <Box sx={{ flex: 1, minWidth: 0 }}>
                                            <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {event.member_name || t.dashboard.unknown}
                                            </Typography>
                                            <Typography variant="caption" sx={{ color: textSecondary }}>
                                                {granted ? "Acceso" : "Denegado"} — {event.timestamp ? format(new Date(event.timestamp), "h:mm a") : ""}
                                            </Typography>
                                        </Box>
                                        {conf > 0 && (
                                            <Chip
                                                label={`${(conf * 100).toFixed(0)}%`}
                                                size="small"
                                                color={granted ? "success" : "error"}
                                                sx={{ fontWeight: 600 }}
                                            />
                                        )}
                                    </Box>
                                );
                            })}
                            {(!recentEvents || recentEvents.length === 0) && (
                                <Typography variant="body2" sx={{ color: textSecondary, py: 2 }}>
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
