import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { salesApi } from '@/api/sales';
import { buildReportRange, type ReportRangeParams } from '@/api/reportRange';
import {
    Box,
    Typography,
    Grid,
    Card,
    CardContent,
    Button,
    Select,
    MenuItem,
    FormControl,
    InputLabel,
    TextField,
    Paper,
    Avatar,
    CircularProgress,
    useMediaQuery,
    useTheme,
} from '@mui/material';
import {
    TrendingUp as TrendingUpIcon,
    People as PeopleIcon,
    AttachMoney as MoneyIcon,
    FitnessCenter as FitnessCenterIcon,
    CalendarToday as CalendarIcon,
    ArrowUpward as ArrowUpIcon,
    ArrowDownward as ArrowDownIcon,
    Download as DownloadIcon,
    Refresh as RefreshIcon,
} from '@mui/icons-material';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    ArcElement,
    Title,
    Tooltip,
    Legend,
    Filler,
} from 'chart.js';
import { Line, Bar, Doughnut } from 'react-chartjs-2';
import { useLanguage } from '@/i18n/LanguageContext';
import { useAppTimezone } from '@/hooks/useAppTimezone';
import { formatDateLabel, formatLocalDateTime } from '@/utils/dateTime';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Title, Tooltip, Legend, Filler);

interface MetricCardProps {
    title: string;
    value: string | number;
    change: number;
    changeLabel: string;
    icon: React.ReactNode;
    color: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ title, value, change, changeLabel, icon, color }) => {
    const isPositive = change >= 0;

    return (
        <Card
            sx={{
                height: '100%',
                background: `linear-gradient(135deg, ${color}15 0%, ${color}05 100%)`,
                border: `1px solid ${color}30`,
                transition: 'all 0.3s ease',
                '&:hover': {
                    transform: 'translateY(-4px)',
                    boxShadow: `0 8px 24px ${color}25`,
                }
            }}
        >
            <CardContent>
                <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                            {title}
                        </Typography>
                        <Typography variant="h4" fontWeight="bold" sx={{ mb: 1 }}>
                            {value}
                        </Typography>
                        <Box display="flex" alignItems="center" gap={0.5}>
                            {isPositive ? (
                                <ArrowUpIcon sx={{ fontSize: 16, color: 'success.main' }} />
                            ) : (
                                <ArrowDownIcon sx={{ fontSize: 16, color: 'error.main' }} />
                            )}
                            <Typography
                                variant="caption"
                                color={isPositive ? 'success.main' : 'error.main'}
                                fontWeight="600"
                            >
                                {Math.abs(change)}%
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {changeLabel}
                            </Typography>
                        </Box>
                    </Box>
                    <Avatar
                        sx={{
                            bgcolor: color,
                            width: { xs: 44, sm: 56 },
                            height: { xs: 44, sm: 56 },
                        }}
                    >
                        {icon}
                    </Avatar>
                </Box>
            </CardContent>
        </Card>
    );
};

const GREEN_PALETTE = ['#1b5e20', '#2e7d32', '#388e3c', '#43a047', '#4caf50', '#66bb6a', '#81c784', '#a5d6a7'];

export const Reports: React.FC = () => {
    const queryClient = useQueryClient();
    const { t } = useLanguage();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
    const isXs = useMediaQuery(theme.breakpoints.down('xs'));
    // Configured app timezone from public settings — every timestamp on this
    // page renders in this zone, never the browser's local zone.
    const timezone = useAppTimezone();
    const [timeRange, setTimeRange] = useState('30days');
    const [customStart, setCustomStart] = useState('');
    const [customEnd, setCustomEnd] = useState('');

    // Resolve the selection into API params. Presets -> { days }; custom ->
    // { start_date, end_date }. An incomplete/reversed custom selection yields
    // null so both queries are disabled until the user finishes picking dates,
    // and — when both dates are filled but reversed — an inline message is
    // shown instead of silently falling back to unfiltered/partial data.
    let dashboardParams: ReportRangeParams | null = null;
    let rangeErrorMessage: string | null = null;
    try {
        dashboardParams = buildReportRange(timeRange, customStart, customEnd);
    } catch {
        dashboardParams = null;
        if (timeRange === 'custom' && customStart && customEnd) {
            rangeErrorMessage = t.reports.invalidRange || 'Start date must not be after end date';
        }
    }
    const customReady = dashboardParams !== null;
    // Summary shares the custom window when one is selected; presets keep the
    // cumulative (unfiltered) summary, preserving existing preset behaviour.
    const summaryParams: { start_date?: string; end_date?: string } =
        dashboardParams && 'start_date' in dashboardParams
            ? { start_date: dashboardParams.start_date, end_date: dashboardParams.end_date }
            : {};

    const { data: reportData, isLoading: loadingReport } = useQuery({
        queryKey: ['dashboard-report', timeRange, customStart, customEnd],
        queryFn: () => salesApi.getDashboardReport(dashboardParams as ReportRangeParams),
        enabled: customReady,
    });

    const { data: salesReport } = useQuery({
        queryKey: ['sales-report', timeRange, customStart, customEnd],
        queryFn: () => salesApi.getReportSummary(summaryParams),
        enabled: customReady,
    });


    const { data: recentSales } = useQuery({
        queryKey: ['recent-sales'],
        queryFn: () => salesApi.getTransactions({ skip: 0, limit: 10 }),
    });

    const periodRevenue = (reportData?.revenue_trend || []).reduce((sum: number, d: any) => sum + (d.amount || 0), 0);
    const totalRevenue = salesReport?.total_revenue || 0;
    const activeMembers = reportData?.active_vs_expired?.active || 0;
    const expiredMembers = reportData?.active_vs_expired?.expired || 0;
    const totalMemberships = activeMembers + expiredMembers;
    const retentionRate = totalMemberships > 0 ? ((activeMembers / totalMemberships) * 100) : 0;
    const periodLabel = timeRange === 'today' ? (t.reports.today || 'Hoy') : timeRange === '7days' ? t.reports.last7Days : timeRange === '90days' ? t.reports.last90Days : timeRange === 'year' ? t.reports.thisYear : t.reports.last30Days;

    const metrics = {
        totalRevenue: {
            value: `$${Number(periodRevenue).toLocaleString()}`,
            change: reportData?.revenue_change_pct || 0,
            label: periodLabel,
        },
        activeMembers: {
            value: activeMembers.toLocaleString(),
            change: 0,
            label: `${t.reports.activeMemberships} (${retentionRate.toFixed(0)}%)`,
        },
        newSignups: {
            value: (reportData?.new_signups?.this_month || 0).toLocaleString(),
            change: reportData?.new_signups?.change_pct || 0,
            label: t.reports.vsLastMonth,
        },
        checkIns: {
            value: (reportData?.checkins_today || 0).toLocaleString(),
            change: 0,
            label: `${reportData?.checkins_week || 0} ${t.reports.thisWeek}`,
        },
        totalTransactions: {
            value: salesReport?.total_transactions?.toLocaleString() || '0',
            change: 0,
            label: `${periodLabel} — $${Number(totalRevenue).toLocaleString()} acumulado`,
        },
        retention: {
            value: `${retentionRate.toFixed(1)}%`,
            change: 0,
            label: `${activeMembers} activas / ${totalMemberships} total`,
        },
    };

    const revenueChartData = {
        labels: (reportData?.revenue_trend || []).map((d: any) => formatDateLabel(d.date)),
        datasets: [
            {
                label: 'Revenue',
                data: (reportData?.revenue_trend || []).map((d: any) => d.amount),
                borderColor: '#2e7d32',
                backgroundColor: 'rgba(46, 125, 50, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
            },
        ],
    };

    const checkinTrendData = {
        labels: (reportData?.checkin_trend || []).map((d: any) => formatDateLabel(d.date)),
        datasets: [
            {
                label: 'Check-ins',
                data: (reportData?.checkin_trend || []).map((d: any) => d.count),
                borderColor: '#1976d2',
                backgroundColor: 'rgba(25, 118, 210, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 2,
                pointHoverRadius: 5,
            },
        ],
    };

    const memberGrowthData = {
        labels: (reportData?.member_growth || []).map((d: any) => d.month),
        datasets: [
            {
                label: 'New Members',
                data: (reportData?.member_growth || []).map((d: any) => d.count),
                backgroundColor: '#2e7d32',
                borderRadius: 6,
            },
        ],
    };

    const distData = reportData?.membership_distribution || [];
    const membershipDistribution = {
        labels: distData.map((d: any) => d.plan),
        datasets: [
            {
                data: distData.map((d: any) => d.count),
                backgroundColor: distData.map((_: any, i: number) => GREEN_PALETTE[i % GREEN_PALETTE.length]),
                borderWidth: 0,
            },
        ],
    };

    const peakHoursData = {
        labels: (reportData?.peak_hours || []).map((d: any) => d.label),
        datasets: [
            {
                label: 'Check-ins',
                data: (reportData?.peak_hours || []).map((d: any) => d.checkins),
                backgroundColor: 'rgba(46, 125, 50, 0.8)',
                borderRadius: 6,
            },
        ],
    };

    const chartHeight = isXs ? 250 : 320;
    const paperHeight = isXs ? 330 : 400;

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: true, position: 'bottom' as const },
        },
        scales: { y: { beginAtZero: true } },
    };

    const doughnutOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom' as const } },
    };

    const handleRefresh = () => {
        queryClient.invalidateQueries({ queryKey: ['dashboard-report'] });
        queryClient.invalidateQueries({ queryKey: ['sales-report'] });
        queryClient.invalidateQueries({ queryKey: ['members-count'] });
        queryClient.invalidateQueries({ queryKey: ['recent-sales'] });
    };

    // Export the currently selected range (preset or custom) as a server-side
    // CSV. Uses the SAME resolved params as the on-screen queries so the file
    // matches what the admin sees. Disabled while a custom range is incomplete.
    const handleExport = async () => {
        if (!dashboardParams) return;
        const blob = await salesApi.exportReport(dashboardParams);
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `sales_report_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    };

    return (
        <Box sx={{ p: { xs: 2, sm: 3 } }}>
            <Box display="flex" flexDirection={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', sm: 'center' }} mb={4} gap={2}>
                <Box>
                    <Typography variant={isMobile ? "h5" : "h4"} fontWeight="bold" gutterBottom>
                        {t.reports.title}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        {t.reports.subtitle}
                    </Typography>
                </Box>
                <Box display="flex" gap={2} flexDirection={{ xs: 'column', sm: 'row' }} width={isMobile ? '100%' : 'auto'}>
                    <FormControl size="small" fullWidth={isMobile}>
                        <InputLabel>{t.reports.timeRange}</InputLabel>
                        <Select
                            value={timeRange}
                            label={t.reports.timeRange}
                            onChange={(e) => setTimeRange(e.target.value)}
                        >
                            <MenuItem value="today">{t.reports.today || 'Hoy'}</MenuItem>
                            <MenuItem value="7days">{t.reports.last7Days}</MenuItem>
                            <MenuItem value="30days">{t.reports.last30Days}</MenuItem>
                            <MenuItem value="90days">{t.reports.last90Days}</MenuItem>
                            <MenuItem value="year">{t.reports.thisYear}</MenuItem>
                            <MenuItem value="custom">{t.reports.customRange || 'Custom range'}</MenuItem>
                        </Select>
                    </FormControl>
                    {timeRange === 'custom' && (
                        <Box display="flex" flexDirection="column" gap={0.5}>
                            <Box display="flex" gap={1} alignItems="center">
                                <TextField
                                    type="date"
                                    size="small"
                                    label={t.reports.startDate || 'Start'}
                                    value={customStart}
                                    InputLabelProps={{ shrink: true }}
                                    onChange={(e) => setCustomStart(e.target.value)}
                                    error={Boolean(rangeErrorMessage)}
                                />
                                <TextField
                                    type="date"
                                    size="small"
                                    label={t.reports.endDate || 'End'}
                                    value={customEnd}
                                    InputLabelProps={{ shrink: true }}
                                    onChange={(e) => setCustomEnd(e.target.value)}
                                    error={Boolean(rangeErrorMessage)}
                                />
                            </Box>
                            {rangeErrorMessage && (
                                <Typography variant="caption" color="error" role="alert">
                                    {rangeErrorMessage}
                                </Typography>
                            )}
                        </Box>
                    )}
                    <Box display="flex" gap={1}>
                    <Button
                        variant="outlined"
                        startIcon={<RefreshIcon />}
                        sx={{ borderColor: '#2e7d32', color: '#2e7d32' }}
                        onClick={handleRefresh}
                    >
                        {isMobile ? '' : t.reports.refresh}
                    </Button>
                    <Button
                        variant="contained"
                        startIcon={<DownloadIcon />}
                        sx={{ bgcolor: '#2e7d32', '&:hover': { bgcolor: '#1b5e20' } }}
                        onClick={handleExport}
                        disabled={!customReady}
                    >
                        {isMobile ? '' : t.reports.exportReport}
                    </Button>
                    </Box>
                </Box>
            </Box>

            <Grid container spacing={2} mb={4}>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard title={t.reports.totalRevenue} value={metrics.totalRevenue.value} change={metrics.totalRevenue.change} changeLabel={metrics.totalRevenue.label} icon={<MoneyIcon />} color="#2e7d32" />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard title={t.reports.activeMembers} value={metrics.activeMembers.value} change={metrics.activeMembers.change} changeLabel={metrics.activeMembers.label} icon={<PeopleIcon />} color="#1976d2" />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard title={t.reports.newSignups} value={metrics.newSignups.value} change={metrics.newSignups.change} changeLabel={metrics.newSignups.label} icon={<TrendingUpIcon />} color="#9c27b0" />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard title={t.reports.checkinsToday} value={metrics.checkIns.value} change={metrics.checkIns.change} changeLabel={metrics.checkIns.label} icon={<FitnessCenterIcon />} color="#f57c00" />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard title={t.reports.avgRevPerMember || 'Transacciones'} value={metrics.totalTransactions.value} change={metrics.totalTransactions.change} changeLabel={metrics.totalTransactions.label} icon={<MoneyIcon />} color="#00897b" />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard title={t.reports.retentionRate} value={metrics.retention.value} change={metrics.retention.change} changeLabel={metrics.retention.label} icon={<CalendarIcon />} color="#d32f2f" />
                </Grid>
            </Grid>

            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} lg={8}>
                    <Paper sx={{ p: { xs: 2, md: 3 }, height: paperHeight }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.revenueTrend}</Typography>
                        <Box sx={{ height: chartHeight }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%"><CircularProgress /></Box>
                            ) : (
                                <Line data={revenueChartData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} lg={4}>
                    <Paper sx={{ p: { xs: 2, md: 3 }, height: paperHeight }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.membershipDistribution}</Typography>
                        <Box sx={{ height: chartHeight, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            {loadingReport ? (
                                <CircularProgress />
                            ) : distData.length > 0 ? (
                                <Doughnut data={membershipDistribution} options={doughnutOptions} />
                            ) : (
                                <Typography color="text.secondary">{t.reports.noActiveMemberships}</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: { xs: 2, md: 3 }, height: paperHeight }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.memberGrowth}</Typography>
                        <Box sx={{ height: chartHeight }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%"><CircularProgress /></Box>
                            ) : (
                                <Bar data={memberGrowthData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: { xs: 2, md: 3 }, height: paperHeight }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.peakHoursAnalysis}</Typography>
                        <Box sx={{ height: chartHeight }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%"><CircularProgress /></Box>
                            ) : (
                                <Bar data={peakHoursData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            <Grid container spacing={3} mb={4}>
                <Grid item xs={12}>
                    <Paper sx={{ p: { xs: 2, md: 3 }, height: paperHeight }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.checkinTrend}</Typography>
                        <Box sx={{ height: chartHeight }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%"><CircularProgress /></Box>
                            ) : (
                                <Line data={checkinTrendData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: { xs: 2, md: 3 } }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.salesByMethod}</Typography>
                        <Box sx={{ mt: 2 }}>
                            {Object.entries(salesReport?.revenue_by_method || {}).map(([method, revenue], index) => (
                                <Box key={index} sx={{ mb: 2, p: 2, bgcolor: 'var(--bg-primary)', borderRadius: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <Box sx={{ minWidth: 0, flex: 1, mr: 1 }}>
                                        <Typography variant="subtitle1" fontWeight="600">{method.toUpperCase()}</Typography>
                                        <Typography variant="body2" color="text.secondary">{salesReport?.transactions_by_method?.[method] || 0} {t.reports.transactions}</Typography>
                                    </Box>
                                    <Typography variant="h6" fontWeight="bold" color="#2e7d32">${Number(revenue).toLocaleString()}</Typography>
                                </Box>
                            ))}
                            {Object.keys(salesReport?.revenue_by_method || {}).length === 0 && (
                                <Typography textAlign="center" color="text.secondary" py={4}>{t.reports.noSalesData}</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: { xs: 2, md: 3 } }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>{t.reports.recentTransactions}</Typography>
                        <Box sx={{ mt: 2, maxHeight: 400, overflow: 'auto' }}>
                            {recentSales?.transactions?.map((tx: any) => (
                                <Box key={tx.id} sx={{ mb: 2, p: 2, bgcolor: 'var(--bg-primary)', borderRadius: 2 }}>
                                    <Box display="flex" justifyContent="space-between">
                                        <Typography variant="subtitle2" fontWeight="600">
                                            {tx.member_name || t.dashboard.unknown}
                                        </Typography>
                                        <Typography variant="subtitle2" fontWeight="bold" color="#2e7d32">
                                            ${Number(tx.amount).toLocaleString()}
                                        </Typography>
                                    </Box>
                                    <Typography variant="caption" color="text.secondary">
                                        {formatLocalDateTime(tx.transaction_date, timezone)} &bull; {tx.payment_method}
                                    </Typography>
                                </Box>
                            ))}
                            {recentSales?.transactions?.length === 0 && (
                                <Typography textAlign="center" color="text.secondary" py={4}>{t.reports.noTransactionsYet}</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        </Box>
    );
};
