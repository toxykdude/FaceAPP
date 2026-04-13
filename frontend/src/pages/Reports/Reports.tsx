import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { salesApi } from '@/api/sales';
import { eventsApi } from '@/api/events';
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
import { format, subDays } from 'date-fns';

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

export const Reports: React.FC = () => {
    const queryClient = useQueryClient();
    const [timeRange, setTimeRange] = useState('30days');

    const { data: salesReport } = useQuery({
        queryKey: ['sales-report'],
        queryFn: () => salesApi.getReportSummary(),
    });

    const { data: membersData } = useQuery({
        queryKey: ['members-count'],
        queryFn: () => membersApi.getMembers({ limit: 1 }),
    });

    const { data: eventsStats } = useQuery({
        queryKey: ['events-stats'],
        queryFn: () => eventsApi.getEvents(0, 1000),
    });

    const totalCheckins = eventsStats?.events?.filter((e: any) => e.access_granted || e.event_type === 'check_in').length || 0;
    const metrics = {
        totalRevenue: { value: `$${(salesReport?.total_revenue || 0).toLocaleString()}`, change: 0, label: 'this period' },
        activeMembers: { value: (membersData?.total || 0).toLocaleString(), change: 0, label: 'total registered' },
        newSignups: { value: '0', change: 0, label: 'this period' },
        checkIns: { value: totalCheckins.toLocaleString(), change: 0, label: 'this period' },
        avgRevPerMember: { value: membersData?.total ? `$${((salesReport?.total_revenue || 0) / membersData.total).toFixed(2)}` : '$0', change: 0, label: 'average' },
        retention: { value: '0%', change: 0, label: 'this period' },
    };

    // Revenue Chart Data
    const revenueChartData = {
        labels: Array.from({ length: 30 }, (_, i) => format(subDays(new Date(), 29 - i), 'MMM dd')),
        datasets: [
            {
                label: 'Revenue',
                data: Array.from({ length: 30 }, () => 0),
                borderColor: '#2e7d32',
                backgroundColor: 'rgba(46, 125, 50, 0.1)',
                fill: true,
                tension: 0.4,
            },
        ],
    };

    // Member Growth Chart
    const memberGrowthData = {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        datasets: [
            {
                label: 'New Members',
                data: [65, 78, 90, 81, 96, 87],
                backgroundColor: '#2e7d32',
            },
            {
                label: 'Cancelled',
                data: [12, 15, 8, 10, 7, 9],
                backgroundColor: '#d32f2f',
            },
        ],
    };

    // Membership Distribution
    const membershipDistribution = {
        labels: ['Basic', 'Premium', 'VIP', 'Student'],
        datasets: [
            {
                data: [320, 450, 180, 284],
                backgroundColor: ['#2e7d32', '#388e3c', '#43a047', '#4caf50'],
                borderWidth: 0,
            },
        ],
    };

    // Peak Hours Data
    const peakHoursData = {
        labels: ['6AM', '8AM', '10AM', '12PM', '2PM', '4PM', '6PM', '8PM', '10PM'],
        datasets: [
            {
                label: 'Check-ins',
                data: [45, 120, 85, 95, 110, 180, 250, 190, 80],
                backgroundColor: 'rgba(46, 125, 50, 0.8)',
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
                        onClick={() => {
                            queryClient.invalidateQueries({ queryKey: ['sales-report'] });
                            queryClient.invalidateQueries({ queryKey: ['events-stats'] });
                            queryClient.invalidateQueries({ queryKey: ['members-count'] });
                        }}
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
                        title="Total Check-ins"
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

            {/* Charts Row 1 */}
            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} lg={8}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Revenue Trend
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            <Line data={revenueChartData} options={chartOptions} />
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} lg={4}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Membership Distribution
                        </Typography>
                        <Box sx={{ height: 320, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Doughnut
                                data={membershipDistribution}
                                options={{
                                    ...chartOptions,
                                    plugins: {
                                        legend: {
                                            position: 'bottom',
                                        },
                                    },
                                }}
                            />
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            {/* Charts Row 2 */}
            <Grid container spacing={3} mb={4}>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Member Growth
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            <Bar data={memberGrowthData} options={chartOptions} />
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3, height: 400 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Peak Hours Analysis
                        </Typography>
                        <Box sx={{ height: 320 }}>
                            <Bar data={peakHoursData} options={chartOptions} />
                        </Box>
                    </Paper>
                </Grid>
            </Grid>

            {/* Sales by Payment Method & Recent Activity */}
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
                                    <Typography variant="h6" fontWeight="bold" color="#2e7d32">${(revenue as number).toLocaleString()}</Typography>
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
                        <Box sx={{ mt: 2 }}>
                            {salesReport?.total_transactions === 0 && (
                                <Typography textAlign="center" color="text.secondary" py={4}>No transactions yet</Typography>
                            )}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        </Box>
    );
};
