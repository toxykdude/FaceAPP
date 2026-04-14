/**
 * Main application layout with modern sidebar navigation
 */
import React, { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    Box,
    Drawer,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Avatar,
    IconButton,
    Menu,
    MenuItem,
    Divider,
    useMediaQuery,
    useTheme,
    Typography,
} from '@mui/material';
import {
    Home as HomeIcon,
    People as PeopleIcon,
    Assessment as ReportsIcon,
    Settings as SettingsIcon,
    Menu as MenuIcon,
    KeyboardArrowDown as ArrowDownIcon,
    Logout,
    Add as AddIcon,
    DarkMode as DarkModeIcon,
    LightMode as LightModeIcon,
} from '@mui/icons-material';
import apiClient from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { useThemeMode } from '@/contexts/ThemeContext';
import { useLanguage } from '@/i18n/LanguageContext';

const drawerWidth = 280;

export const MainLayout: React.FC = () => {
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('md'));
    const navigate = useNavigate();
    const location = useLocation();
    const { user, logout } = useAuth();
    const { mode, toggleTheme } = useThemeMode();
    const { t } = useLanguage();

    const { data: publicSettings } = useQuery({
        queryKey: ['public-settings'],
        queryFn: async () => {
            const response = await apiClient.get('/settings/public');
            return response.data;
        },
        staleTime: 60000,
    });

    const orgName = publicSettings?.business_name || 'PowerHouse';
    const orgLogo = publicSettings?.business_logo || '/logo.png';

    const canAccess = (page: string): boolean => {
        if (!user) return false;
        if (user.role === 'admin') return true;
        const pages = (user as any).permissions?.pages || [];
        return pages.includes('all') || pages.includes(page);
    };

    const menuItems = [
        { text: t.nav.home, icon: <HomeIcon />, path: '/', page: 'dashboard' },
        { text: t.nav.members, icon: <PeopleIcon />, path: '/members', page: 'members' },
        { text: t.nav.reports, icon: <ReportsIcon />, path: '/reports', page: 'reports' },
    ];

    const projectItems = [
        { text: t.nav.members, icon: '🟣', color: '#8b5cf6', path: '/members', page: 'members' },
        { text: t.nav.memberships, icon: '🔵', color: '#3b82f6', path: '/memberships', page: 'memberships' },
        { text: t.nav.cameras, icon: '🔷', color: '#06b6d4', path: '/cameras', page: 'cameras' },
        { text: t.nav.sales, icon: '🟢', color: '#22c55e', path: '/sales', page: 'sales' },
    ];

    const filteredMenuItems = menuItems.filter(item => canAccess(item.page));
    const filteredProjectItems = projectItems.filter(item => canAccess(item.page));

    const [mobileOpen, setMobileOpen] = useState(false);
    const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

    const handleDrawerToggle = () => {
        setMobileOpen(!mobileOpen);
    };

    const handleMenuClick = (path: string) => {
        navigate(path);
        if (isMobile) {
            setMobileOpen(false);
        }
    };

    const handleUserMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
        setAnchorEl(event.currentTarget);
    };

    const handleUserMenuClose = () => {
        setAnchorEl(null);
    };

    const handleLogout = async () => {
        handleUserMenuClose();
        await logout();
        navigate('/login');
    };

    const isActivePath = (path: string) => {
        return location.pathname === path;
    };

    const drawer = (
        <Box
            sx={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--bg-sidebar)',
                borderRight: '1px solid var(--border-color)',
            }}
        >
            {/* Logo Section */}
            <Box sx={{ p: 2.5, pb: 0, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <img src={orgLogo} alt={orgName} style={{ width: 36, height: 36, borderRadius: 8 }} />
                <Typography variant="h6" sx={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '1.1rem' }}>
                    {orgName}
                </Typography>
            </Box>

            {/* User Profile Section */}
            <Box sx={{ p: 3 }}>
                <Box
                    sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1.5,
                        p: 1.5,
                        borderRadius: 'var(--radius-lg)',
                        cursor: 'pointer',
                        transition: 'var(--transition-base)',
                        '&:hover': {
                            background: 'var(--bg-primary)',
                        },
                    }}
                    onClick={handleUserMenuOpen}
                >
                    <Avatar
                        sx={{
                            width: 40,
                            height: 40,
                            background: 'var(--primary-gradient)',
                        }}
                    >
                        {user?.username?.[0]?.toUpperCase() || 'A'}
                    </Avatar>
                    <Box sx={{ flex: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                            {user?.username || 'Admin'}
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'var(--text-secondary)' }}>
                            {t.dashboard.online}
                        </Typography>
                    </Box>
                    <ArrowDownIcon sx={{ color: 'var(--text-muted)', fontSize: 20 }} />
                </Box>
            </Box>

            {/* Main Navigation */}
            <Box sx={{ px: 2, flex: 1, overflowY: 'auto' }}>
                <List sx={{ py: 0 }}>
                    {filteredMenuItems.map((item) => (
                        <ListItem key={item.text} disablePadding sx={{ mb: 0.5 }}>
                            <ListItemButton
                                onClick={() => handleMenuClick(item.path)}
                                sx={{
                                    borderRadius: 'var(--radius-md)',
                                    py: 1.25,
                                    px: 2,
                                    background: isActivePath(item.path) ? 'var(--bg-primary)' : 'transparent',
                                    '&:hover': {
                                        background: 'var(--bg-primary)',
                                    },
                                }}
                            >
                                <ListItemIcon
                                    sx={{
                                        minWidth: 40,
                                        color: isActivePath(item.path) ? 'var(--text-primary)' : 'var(--text-secondary)',
                                    }}
                                >
                                    {item.icon}
                                </ListItemIcon>
                                <ListItemText
                                    primary={item.text}
                                    primaryTypographyProps={{
                                        fontSize: '0.95rem',
                                        fontWeight: isActivePath(item.path) ? 600 : 500,
                                        color: isActivePath(item.path) ? 'var(--text-primary)' : 'var(--text-secondary)',
                                    }}
                                />
                            </ListItemButton>
                        </ListItem>
                    ))}
                </List>

                {/* Projects Section */}
                <Box sx={{ mt: 3, mb: 2 }}>
                    <Box
                        sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            px: 2,
                            mb: 1.5,
                        }}
                    >
                        <Typography
                            variant="caption"
                            sx={{
                                fontWeight: 600,
                                color: 'var(--text-muted)',
                                textTransform: 'uppercase',
                                letterSpacing: '0.5px',
                            }}
                        >
                            {t.common.add}
                        </Typography>
                        <IconButton
                            size="small"
                            sx={{
                                color: 'var(--accent-purple)',
                                '&:hover': {
                                    background: 'var(--bg-primary)',
                                },
                            }}
                        >
                            <AddIcon fontSize="small" />
                        </IconButton>
                    </Box>
                    <List sx={{ py: 0 }}>
                        {filteredProjectItems.map((item) => (
                            <ListItem key={item.text} disablePadding sx={{ mb: 0.5 }}>
                                <ListItemButton
                                    onClick={() => handleMenuClick(item.path)}
                                    sx={{
                                        borderRadius: 'var(--radius-md)',
                                        py: 1,
                                        px: 2,
                                        background: isActivePath(item.path) ? 'var(--bg-primary)' : 'transparent',
                                        '&:hover': {
                                            background: 'var(--bg-primary)',
                                        },
                                    }}
                                >
                                    <Box
                                        sx={{
                                            width: 8,
                                            height: 8,
                                            borderRadius: '50%',
                                            background: item.color,
                                            mr: 2,
                                        }}
                                    />
                                    <ListItemText
                                        primary={item.text}
                                        primaryTypographyProps={{
                                            fontSize: '0.9rem',
                                            fontWeight: isActivePath(item.path) ? 600 : 500,
                                            color: isActivePath(item.path) ? 'var(--text-primary)' : 'var(--text-secondary)',
                                        }}
                                    />
                                </ListItemButton>
                            </ListItem>
                        ))}
                    </List>
                </Box>
            </Box>

            {/* Settings at Bottom */}
            <Box sx={{ p: 2, borderTop: '1px solid var(--border-color)' }}>
                <Box sx={{ display: 'flex', gap: 0.5 }}>
                    <ListItemButton
                        onClick={() => handleMenuClick('/settings')}
                        sx={{
                            borderRadius: 'var(--radius-md)',
                            py: 1.25,
                            px: 2,
                            flex: 1,
                            background: isActivePath('/settings') ? 'var(--bg-primary)' : 'transparent',
                            '&:hover': {
                                background: 'var(--bg-primary)',
                            },
                        }}
                    >
                        <ListItemIcon
                            sx={{
                                minWidth: 40,
                                color: isActivePath('/settings') ? 'var(--text-primary)' : 'var(--text-secondary)',
                            }}
                        >
                            <SettingsIcon />
                        </ListItemIcon>
                        <ListItemText
                            primary={t.nav.settings}
                            primaryTypographyProps={{
                                fontSize: '0.95rem',
                                fontWeight: isActivePath('/settings') ? 600 : 500,
                                color: isActivePath('/settings') ? 'var(--text-primary)' : 'var(--text-secondary)',
                            }}
                        />
                    </ListItemButton>
                    <IconButton
                        onClick={toggleTheme}
                        sx={{
                            color: 'var(--text-secondary)',
                            alignSelf: 'center',
                            '&:hover': { background: 'var(--bg-primary)' },
                        }}
                        title={mode === 'dark' ? t.settings.lightMode : t.settings.darkMode}
                    >
                        {mode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />}
                    </IconButton>
                </Box>
            </Box>

            {/* User Menu */}
            <Menu
                anchorEl={anchorEl}
                open={Boolean(anchorEl)}
                onClose={handleUserMenuClose}
                PaperProps={{
                    sx: {
                        mt: 1,
                        minWidth: 200,
                        borderRadius: 'var(--radius-lg)',
                        border: '1px solid var(--border-color)',
                    },
                }}
            >
                <MenuItem disabled>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {user?.username}
                    </Typography>
                </MenuItem>
                <Divider />
                <MenuItem onClick={handleLogout}>
                    <ListItemIcon>
                        <Logout fontSize="small" />
                    </ListItemIcon>
                    {t.nav.logout}
                </MenuItem>
            </Menu>
        </Box>
    );

    return (
        <Box sx={{ display: 'flex', minHeight: '100vh' }}>
            {/* Mobile Header */}
            {isMobile && (
                <Box
                    sx={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        height: 64,
                        background: 'var(--bg-secondary)',
                        borderBottom: '1px solid var(--border-color)',
                        display: 'flex',
                        alignItems: 'center',
                        px: 2,
                        zIndex: 1200,
                    }}
                >
                    <IconButton
                        edge="start"
                        onClick={handleDrawerToggle}
                        sx={{ mr: 2 }}
                    >
                        <MenuIcon />
                    </IconButton>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <img src={orgLogo} alt={orgName} style={{ width: 36, height: 36, borderRadius: 8 }} />
                        <Typography variant="h6" sx={{ fontWeight: 700 }}>
                            {orgName}
                        </Typography>
                    </Box>
                    <Box sx={{ flex: 1 }} />
                    <IconButton
                        onClick={toggleTheme}
                        sx={{ color: 'var(--text-secondary)' }}
                        title={mode === 'dark' ? t.settings.lightMode : t.settings.darkMode}
                    >
                        {mode === 'dark' ? <LightModeIcon /> : <DarkModeIcon />}
                    </IconButton>
                </Box>
            )}

            {/* Sidebar Drawer */}
            <Box
                component="nav"
                sx={{
                    width: { md: drawerWidth },
                    flexShrink: { md: 0 },
                }}
            >
                {/* Mobile Drawer */}
                <Drawer
                    variant="temporary"
                    open={mobileOpen}
                    onClose={handleDrawerToggle}
                    ModalProps={{ keepMounted: true }}
                    sx={{
                        display: { xs: 'block', md: 'none' },
                        '& .MuiDrawer-paper': {
                            boxSizing: 'border-box',
                            width: drawerWidth,
                            border: 'none',
                        },
                    }}
                >
                    {drawer}
                </Drawer>

                {/* Desktop Drawer */}
                <Drawer
                    variant="permanent"
                    sx={{
                        display: { xs: 'none', md: 'block' },
                        '& .MuiDrawer-paper': {
                            boxSizing: 'border-box',
                            width: drawerWidth,
                            border: 'none',
                        },
                    }}
                    open
                >
                    {drawer}
                </Drawer>
            </Box>

            {/* Main Content */}
            <Box
                component="main"
                sx={{
                    flexGrow: 1,
                    width: { md: `calc(100% - ${drawerWidth}px)` },
                    minHeight: '100vh',
                    background: 'var(--bg-primary)',
                    pt: { xs: '64px', md: 0 },
                }}
            >
                <Outlet />
            </Box>
        </Box>
    );
};
