import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { salesApi } from '@/api/sales';
import { membersApi } from '@/api/members';
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
    Paper,
    Avatar,
    CircularProgress,

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
import { format, parseISO } from 'date-fns';

// Register ChartJS components
ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    ArcElement,
    Title,
    Tooltip,
    Legend,
    Filler
);

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
                    <Box>
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
                            <Typography variant="caption" color="text.secondary">
                                {changeLabel}
                            </Typography>
                        </Box>
                    </Box>
                    <Avatar
                        sx={{
                            bgcolor: color,
                            width: 56,
                            height: 56,
                        }}
                    >
                        {icon}
                    </Avatar>
                </Box>
            </CardContent>
        </Card>
    );
};

// Green color palette for doughnut charts
const GREEN_PALETTE = ['#1b5e20', '#2e7d32', '#388e3c', '#43a047', '#4caf50', '#66bb6a', '#81c784', '#a5d6a7'];

export const Reports: React.FC = () => {
    const queryClient = useQueryClient();
    const [timeRange, setTimeRange] = useState('30days');

    const daysMap: Record<string, number> = {
        '7days': 7,
        '30days': 30,
        '90days': 90,
        'year': 365,
    };

    // Dashboard report from new endpoint
    const { data: reportData, isLoading: loadingReport } = useQuery({
        queryKey: ['dashboard-report', timeRange],
        queryFn: () => salesApi.getDashboardReport(daysMap[timeRange] || 30),
    });

    // Sales report summary (for payment method breakdown + total revenue)
    const { data: salesReport } = useQuery({
        queryKey: ['sales-report'],
        queryFn: () => salesApi.getReportSummary(),
    });

    // Members total count
    const { data: membersData } = useQuery({
        queryKey: ['members-count'],
        queryFn: () => membersApi.getMembers({ limit: 1 }),
    });

    // Recent transactions
    const { data: recentSales } = useQuery({
        queryKey: ['recent-sales'],
        queryFn: () => salesApi.getTransactions({ skip: 0, limit: 10 }),
    });

    // Derived metrics from real data
    const totalMembers = membersData?.total || 0;
    const totalRevenue = salesReport?.total_revenue || 0;
    const activeMembers = reportData?.active_vs_expired?.active || 0;
    const expiredMembers = reportData?.active_vs_expired?.expired || 0;
    const totalMemberships = activeMembers + expiredMembers;
    const retentionRate = totalMemberships > 0 ? ((activeMembers / totalMemberships) * 100) : 0;

    const metrics = {
        totalRevenue: {
            value: `$${Number(totalRevenue).toLocaleString()}`,
            change: reportData?.revenue_change_pct || 0,
            label: 'vs last month',
        },
        activeMembers: {
            value: activeMembers.toLocaleString(),
            change: 0,
            label: 'active memberships',
        },
        newSignups: {
            value: (reportData?.new_signups?.this_month || 0).toLocaleString(),
            change: reportData?.new_signups?.change_pct || 0,
            label: 'vs last month',
        },
        checkIns: {
            value: (reportData?.checkins_today || 0).toLocaleString(),
            change: 0,
            label: `${reportData?.checkins_week || 0} this week`,
        },
        avgRevPerMember: {
            value: totalMembers > 0
                ? `$${(Number(totalRevenue) / totalMembers).toFixed(2)}`
                : '$0',
            change: 0,
            label: 'per member',
        },
        retention: {
            value: `${retentionRate.toFixed(1)}%`,
            change: 0,
            label: `${activeMembers}/${totalMemberships} active`,
        },
    };

    // Revenue Chart Data — from API
    const revenueChartData = {
        labels: (reportData?.revenue_trend || []).map((d: any) => {
            try { return format(parseISO(d.date), 'MMM dd'); } catch { return d.date; }
        }),
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

    // Check-in Trend Chart Data — from API
    const checkinTrendData = {
        labels: (reportData?.checkin_trend || []).map((d: any) => {
            try { return format(parseISO(d.date), 'MMM dd'); } catch { return d.date; }
        }),
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

    // Member Growth Chart — from API
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

    // Membership Distribution — from API
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

    // Peak Hours Data — from API
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

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                position: 'bottom' as const,
            },
        },
        scales: {
            y: {
                beginAtZero: true,
            },
        },
    };

    const doughnutOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'bottom' as const,
            },
        },
    };

    const handleRefresh = () => {
        queryClient.invalidateQueries({ queryKey: ['dashboard-report'] });
        queryClient.invalidateQueries({ queryKey: ['sales-report'] });
        queryClient.invalidateQueries({ queryKey: ['members-count'] });
        queryClient.invalidateQueries({ queryKey: ['recent-sales'] });
    };

    return (
        <Box sx={{ p: 3 }}>
            {/* Header */}
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={4}>
                <Box>
                    <Typography variant="h4" fontWeight="bold" gutterBottom>
                        Reports & Analytics
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                        Track your gym's performance and member insights
                    </Typography>
                </Box>
                <Box display="flex" gap={2}>
                    <FormControl size="small" sx={{ minWidth: 150 }}>
                        <InputLabel>Time Range</InputLabel>
                        <Select
                            value={timeRange}
                            label="Time Range"
                            onChange={(e) => setTimeRange(e.target.value)}
                        >
                            <MenuItem value="7days">Last 7 Days</MenuItem>
                            <MenuItem value="30days">Last 30 Days</MenuItem>
                            <MenuItem value="90days">Last 90 Days</MenuItem>
                            <MenuItem value="year">This Year</MenuItem>
                        </Select>
                    </FormControl>
                    <Button
                        variant="outlined"
                        startIcon={<RefreshIcon />}
                        sx={{ borderColor: '#2e7d32', color: '#2e7d32' }}
                        onClick={handleRefresh}
                    >
                        Refresh
                    </Button>
                    <Button
                        variant="contained"
                        startIcon={<DownloadIcon />}
                        sx={{
                            bgcolor: '#2e7d32',
                            '&:hover': { bgcolor: '#1b5e20' }
                        }}
                    >
                        Export Report
                    </Button>
                </Box>
            </Box>

            {/* Key Metrics */}
            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard
                        title="Total Revenue"
                        value={metrics.totalRevenue.value}
                        change={metrics.totalRevenue.change}
                        changeLabel={metrics.totalRevenue.label}
                        icon={<MoneyIcon />}
                        color="#2e7d32"
                    />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard
                        title="Active Members"
                        value={metrics.activeMembers.value}
                        change={metrics.activeMembers.change}
                        changeLabel={metrics.activeMembers.label}
                        icon={<PeopleIcon />}
                        color="#1976d2"
                    />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard
                        title="New Signups"
                        value={metrics.newSignups.value}
                        change={metrics.newSignups.change}
                        changeLabel={metrics.newSignups.label}
                        icon={<TrendingUpIcon />}
                        color="#9c27b0"
                    />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard
                        title="Check-ins Today"
                        value={metrics.checkIns.value}
                        change={metrics.checkIns.change}
                        changeLabel={metrics.checkIns.label}
                        icon={<FitnessCenterIcon />}
                        color="#f57c00"
                    />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard
                        title="Avg Revenue/Member"
                        value={metrics.avgRevPerMember.value}
                        change={metrics.avgRevPerMember.change}
                        changeLabel={metrics.avgRevPerMember.label}
                        icon={<MoneyIcon />}
                        color="#00897b"
                    />
                </Grid>
                <Grid item xs={12} sm={6} md={4}>
                    <MetricCard
                        title="Retention Rate"
                        value={metrics.retention.value}
                        change={metrics.retention.change}
                        changeLabel={metrics.retention.label}
                        icon={<CalendarIcon />}
                        color="#d32f2f"
                    />
                </Grid>
            </Grid>

            {/* Charts Row 1: Revenue Trend + Membership Distribution */}
            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} lg={8}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Revenue Trend
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%">
                                    <CircularProgress />
                                </Box>
                            ) : (
                                <Line data={revenueChartData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} lg={4}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Membership Distribution
                        </Typography>
                        <Box sx={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            {loadingReport ? (
                                <CircularProgress />
                            ) : distData.length > 0 ? (
                                <Doughnut data={membershipDistribution} options={doughnutOptions} />
                            ) : (
                                <Typography color="text.secondary">No active memberships</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            {/* Charts Row 2: Member Growth + Peak Hours */}
            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Member Growth
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%">
                                    <CircularProgress />
                                </Box>
                            ) : (
                                <Bar data={memberGrowthData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Peak Hours Analysis
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%">
                                    <CircularProgress />
                                </Box>
                            ) : (
                                <Bar data={peakHoursData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            {/* Charts Row 3: Check-in Trend */}
            <Grid container spacing={3} mb={4}>
                <Grid item xs={12}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Check-in Trend
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            {loadingReport ? (
                                <Box display="flex" alignItems="center" justifyContent="center" height="100%">
                                    <CircularProgress />
                                </Box>
                            ) : (
                                <Line data={checkinTrendData} options={chartOptions} />
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            {/* Sales by Payment Method & Recent Transactions */}
            <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Sales by Payment Method
                        </Typography>
                        <Box sx={{ mt: 2 }}>
                            {Object.entries(salesReport?.revenue_by_method || {}).map(([method, revenue], index) => (
                                <Box key={index} sx={{ mb: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <Box>
                                        <Typography variant="subtitle1" fontWeight="600">{method.toUpperCase()}</Typography>
                                        <Typography variant="body2" color="text.secondary">{salesReport?.transactions_by_method?.[method] || 0} transactions</Typography>
                                    </Box>
                                    <Typography variant="h6" fontWeight="bold" color="#2e7d32">${Number(revenue).toLocaleString()}</Typography>
                                </Box>
                            ))}
                            {Object.keys(salesReport?.revenue_by_method || {}).length === 0 && (
                                <Typography textAlign="center" color="text.secondary" py={4}>No sales data yet</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Recent Transactions
                        </Typography>
                        <Box sx={{ mt: 2, maxHeight: 400, overflow: 'auto' }}>
                            {recentSales?.transactions?.map((tx: any) => (
                                <Box key={tx.id} sx={{ mb: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 2 }}>
                                    <Box display="flex" justifyContent="space-between">
                                        <Typography variant="subtitle2" fontWeight="600">
                                            {tx.member_name || 'Unknown'}
                                        </Typography>
                                        <Typography variant="subtitle2" fontWeight="bold" color="#2e7d32">
                                            ${Number(tx.amount).toLocaleString()}
                                        </Typography>
                                    </Box>
                                    <Typography variant="caption" color="text.secondary">
                                        {(() => {
                                            try {
                                                return format(new Date(tx.transaction_date), 'MMM d, yyyy h:mm a');
                                            } catch {
                                                return tx.transaction_date;
                                            }
                                        })()} &bull; {tx.payment_method}
                                    </Typography>
                                </Box>
                            ))}
                            {recentSales?.transactions?.length === 0 && (
                                <Typography textAlign="center" color="text.secondary" py={4}>No transactions yet</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        </Box>
    );
};
