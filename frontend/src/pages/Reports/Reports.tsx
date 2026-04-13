import React, { useState } from 'react';
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
    Chip,
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
    const [timeRange, setTimeRange] = useState('30days');

    // Mock data - replace with actual API calls
    const metrics = {
        totalRevenue: { value: '$45,230', change: 12.5, label: 'from last month' },
        activeMembers: { value: '1,234', change: 8.3, label: 'from last month' },
        newSignups: { value: '87', change: 15.2, label: 'from last month' },
        checkIns: { value: '3,456', change: -2.1, label: 'from last month' },
        avgRevPerMember: { value: '$36.67', change: 4.2, label: 'from last month' },
        retention: { value: '94.2%', change: 1.8, label: 'from last month' },
    };

    // Revenue Chart Data
    const revenueChartData = {
        labels: Array.from({ length: 30 }, (_, i) => format(subDays(new Date(), 29 - i), 'MMM dd')),
        datasets: [
            {
                label: 'Revenue',
                data: Array.from({ length: 30 }, () => Math.floor(Math.random() * 2000) + 1000),
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

            {/* Top Performers & Recent Activity */}
            <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Top Membership Plans
                        </Typography>
                        <Box sx={{ mt: 2 }}>
                            {[
                                { name: 'Premium Annual', revenue: '$12,450', members: 450, growth: 12 },
                                { name: 'Basic Monthly', revenue: '$8,960', members: 320, growth: 8 },
                                { name: 'VIP Unlimited', revenue: '$6,480', members: 180, growth: 15 },
                                { name: 'Student Discount', revenue: '$4,260', members: 284, growth: -3 },
                            ].map((plan, index) => (
                                <Box
                                    key={index}
                                    sx={{
                                        mb: 2,
                                        p: 2,
                                        bgcolor: '#f5f5f5',
                                        borderRadius: 2,
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                    }}
                                >
                                    <Box>
                                        <Typography variant="subtitle1" fontWeight="600">
                                            {plan.name}
                                        </Typography>
                                        <Typography variant="body2" color="text.secondary">
                                            {plan.members} members
                                        </Typography>
                                    </Box>
                                    <Box textAlign="right">
                                        <Typography variant="h6" fontWeight="bold" color="#2e7d32">
                                            {plan.revenue}
                                        </Typography>
                                        <Chip
                                            label={`${plan.growth > 0 ? '+' : ''}${plan.growth}%`}
                                            size="small"
                                            color={plan.growth >= 0 ? 'success' : 'error'}
                                            sx={{ mt: 0.5 }}
                                        />
                                    </Box>
                                </Box>
                            ))}
                        </Box>
                    </Paper>
                </Grid>
                <Grid item xs={12} md={6}>
                    <Paper sx={{ p: 3 }}>
                        <Typography variant="h6" fontWeight="600" gutterBottom>
                            Recent Transactions
                        </Typography>
                        <Box sx={{ mt: 2 }}>
                            {[
                                { member: 'John Smith', plan: 'Premium Annual', amount: '$299', date: '2 hours ago' },
                                { member: 'Sarah Johnson', plan: 'Basic Monthly', amount: '$29', date: '5 hours ago' },
                                { member: 'Mike Davis', plan: 'VIP Unlimited', amount: '$399', date: '1 day ago' },
                                { member: 'Emily Brown', plan: 'Student Discount', amount: '$15', date: '1 day ago' },
                            ].map((transaction, index) => (
                                <Box
                                    key={index}
                                    sx={{
                                        mb: 2,
                                        p: 2,
                                        bgcolor: '#f5f5f5',
                                        borderRadius: 2,
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                    }}
                                >
                                    <Box display="flex" alignItems="center" gap={2}>
                                        <Avatar sx={{ bgcolor: '#2e7d32' }}>
                                            {transaction.member.charAt(0)}
                                        </Avatar>
                                        <Box>
                                            <Typography variant="subtitle2" fontWeight="600">
                                                {transaction.member}
                                            </Typography>
                                            <Typography variant="caption" color="text.secondary">
                                                {transaction.plan}
                                            </Typography>
                                        </Box>
                                    </Box>
                                    <Box textAlign="right">
                                        <Typography variant="subtitle1" fontWeight="bold" color="#2e7d32">
                                            {transaction.amount}
                                        </Typography>
                                        <Typography variant="caption" color="text.secondary">
                                            {transaction.date}
                                        </Typography>
                                    </Box>
                                </Box>
                            ))}
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        </Box>
    );
};
