/**
 * Application entry point.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import { SnackbarProvider } from 'notistack';
import App from './App';
import { LanguageProvider } from './i18n/LanguageContext';
import { ThemeModeProvider } from './contexts/ThemeContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ThemeModeProvider>
            <LanguageProvider>
                <SnackbarProvider maxSnack={3} autoHideDuration={4000}>
                    <App />
                </SnackbarProvider>
            </LanguageProvider>
        </ThemeModeProvider>
    </React.StrictMode>
);
