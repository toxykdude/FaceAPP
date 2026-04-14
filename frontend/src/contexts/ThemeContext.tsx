import React, { createContext, useContext, useState, ReactNode } from 'react';
import { ThemeProvider as MuiThemeProvider, createTheme, CssBaseline } from '@mui/material';

type ThemeMode = 'light' | 'dark';

interface ThemeContextType {
    mode: ThemeMode;
    toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const useThemeMode = () => {
    const context = useContext(ThemeContext);
    if (!context) throw new Error('useThemeMode must be used within ThemeModeProvider');
    return context;
};

const baseTypography = {
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", sans-serif',
    h1: { fontSize: '3rem', fontWeight: 800, lineHeight: 1.2 },
    h2: { fontSize: '2.5rem', fontWeight: 700, lineHeight: 1.3 },
    h3: { fontSize: '2rem', fontWeight: 700, lineHeight: 1.3 },
    h4: { fontSize: '1.5rem', fontWeight: 600, lineHeight: 1.4 },
    h5: { fontSize: '1.25rem', fontWeight: 600, lineHeight: 1.4 },
    h6: { fontSize: '1rem', fontWeight: 600, lineHeight: 1.5 },
    body1: { fontSize: '1rem', lineHeight: 1.6 },
    body2: { fontSize: '0.875rem', lineHeight: 1.6 },
    button: { fontWeight: 600, textTransform: 'none' as const },
};

const lightTheme = createTheme({
    palette: {
        mode: 'light',
        primary: { main: '#667eea', light: '#8b9cf7', dark: '#5568d3' },
        secondary: { main: '#764ba2', light: '#a77bca', dark: '#65408b' },
        success: { main: '#059669', light: '#10b981', dark: '#047857' },
        error: { main: '#dc2626', light: '#ef4444', dark: '#b91c1c' },
        warning: { main: '#f59e0b', light: '#fbbf24', dark: '#d97706' },
        info: { main: '#3b82f6', light: '#60a5fa', dark: '#2563eb' },
        background: { default: '#f8f9fe', paper: '#ffffff' },
        text: { primary: '#1a1a2e', secondary: '#6b7280' },
    },
    typography: baseTypography,
    shape: { borderRadius: 12 },
    components: {
        MuiButton: {
            styleOverrides: {
                root: { textTransform: 'none', borderRadius: 12, fontWeight: 600, padding: '10px 20px', boxShadow: 'none' },
                contained: { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', '&:hover': { background: 'linear-gradient(135deg, #5568d3 0%, #65408b 100%)' } },
            },
        },
        MuiCard: { styleOverrides: { root: { borderRadius: 16, boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.1)', border: '1px solid #e5e7eb' } } },
        MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
        MuiChip: { styleOverrides: { root: { fontWeight: 600, borderRadius: 8 } } },
        MuiTextField: { styleOverrides: { root: { '& .MuiOutlinedInput-root': { borderRadius: 12 } } } },
        MuiDrawer: { styleOverrides: { paper: { borderRight: 'none' } } },
    },
});

const darkTheme = createTheme({
    palette: {
        mode: 'dark',
        primary: { main: '#8b9cf7', light: '#a5b4fa', dark: '#6f81e9' },
        secondary: { main: '#a77bca', light: '#c4a0d8', dark: '#8a5fb0' },
        success: { main: '#34d399', light: '#6ee7b7', dark: '#059669' },
        error: { main: '#f87171', light: '#fca5a5', dark: '#dc2626' },
        warning: { main: '#fbbf24', light: '#fcd34d', dark: '#f59e0b' },
        info: { main: '#60a5fa', light: '#93c5fd', dark: '#3b82f6' },
        background: { default: '#0f0f1a', paper: '#1a1a2e' },
        text: { primary: '#e2e8f0', secondary: '#94a3b8' },
    },
    typography: baseTypography,
    shape: { borderRadius: 12 },
    components: {
        MuiButton: {
            styleOverrides: {
                root: { textTransform: 'none', borderRadius: 12, fontWeight: 600, padding: '10px 20px', boxShadow: 'none' },
                contained: { background: 'linear-gradient(135deg, #8b9cf7 0%, #a77bca 100%)', '&:hover': { background: 'linear-gradient(135deg, #6f81e9 0%, #8a5fb0 100%)' } },
            },
        },
        MuiCard: { styleOverrides: { root: { borderRadius: 16, boxShadow: '0 1px 3px 0 rgba(0, 0, 0, 0.3)', border: '1px solid #2d2d4a' } } },
        MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
        MuiChip: { styleOverrides: { root: { fontWeight: 600, borderRadius: 8 } } },
        MuiTextField: { styleOverrides: { root: { '& .MuiOutlinedInput-root': { borderRadius: 12 } } } },
        MuiDrawer: { styleOverrides: { paper: { borderRight: 'none' } } },
    },
});

const CSS_VARS = (mode: 'light' | 'dark') => `
    :root {
        --bg-primary: ${mode === 'dark' ? '#0f0f1a' : '#f8f9fe'};
        --bg-secondary: ${mode === 'dark' ? '#1a1a2e' : '#ffffff'};
        --bg-sidebar: ${mode === 'dark' ? '#141428' : '#ffffff'};
        --text-primary: ${mode === 'dark' ? '#e2e8f0' : '#1a1a2e'};
        --text-secondary: ${mode === 'dark' ? '#94a3b8' : '#6b7280'};
        --text-muted: ${mode === 'dark' ? '#64748b' : '#9ca3af'};
        --border-color: ${mode === 'dark' ? '#2d2d4a' : '#e5e7eb'};
        --status-high: ${mode === 'dark' ? '#3b1c1c' : '#fee2e2'};
        --status-high-text: ${mode === 'dark' ? '#fca5a5' : '#dc2626'};
        --status-normal: ${mode === 'dark' ? '#1e2a4a' : '#dbeafe'};
        --status-normal-text: ${mode === 'dark' ? '#93c5fd' : '#2563eb'};
        --status-low: ${mode === 'dark' ? '#1e1e2e' : '#f3f4f6'};
        --status-low-text: ${mode === 'dark' ? '#94a3b8' : '#6b7280'};
        --status-progress: ${mode === 'dark' ? '#0d3320' : '#d1fae5'};
        --status-progress-text: ${mode === 'dark' ? '#6ee7b7' : '#059669'};
    }
`;

export const ThemeModeProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
    const [mode, setMode] = useState<ThemeMode>(() => {
        return (localStorage.getItem('themeMode') as ThemeMode) || 'dark';
    });

    const toggleTheme = () => {
        setMode(prev => {
            const next = prev === 'light' ? 'dark' : 'light';
            localStorage.setItem('themeMode', next);
            return next;
        });
    };

    const theme = mode === 'light' ? lightTheme : darkTheme;

    return (
        <ThemeContext.Provider value={{ mode, toggleTheme }}>
            <MuiThemeProvider theme={theme}>
                <CssBaseline />
                <style>{CSS_VARS(mode)}</style>
                {children}
            </MuiThemeProvider>
        </ThemeContext.Provider>
    );
};
