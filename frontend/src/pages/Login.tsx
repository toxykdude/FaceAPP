/**
 * Login page component.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
    Box,
    Card,
    CardContent,
    TextField,
    Button,
    Typography,
    Alert,
    Container,
} from '@mui/material';
import apiClient from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { useLanguage } from '@/i18n/LanguageContext';

export const LoginPage: React.FC = () => {
    const navigate = useNavigate();
    const { login } = useAuth();
    const { t } = useLanguage();

    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);

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

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            await login({ username, password });
            navigate('/');
        } catch (err: any) {
            setError(err.response?.data?.detail || t.login.loginFailed);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Container maxWidth="sm">
            <Box
                display="flex"
                flexDirection="column"
                justifyContent="center"
                alignItems="center"
                minHeight="100vh"
            >
                <Card sx={{ width: '100%', maxWidth: 450 }}>
                    <CardContent sx={{ p: 4 }}>
                        <Box sx={{ textAlign: 'center', mb: 1 }}>
                            <img src={orgLogo} alt={orgName} style={{ width: 72, height: 72, borderRadius: 16, marginBottom: 12 }} />
                        </Box>
                        <Typography variant="h4" component="h1" gutterBottom align="center">
                            {orgName}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" align="center" mb={3}>
                            {t.login.membershipPlatform}
                        </Typography>

                        {error && (
                            <Alert severity="error" sx={{ mb: 2 }}>
                                {error}
                            </Alert>
                        )}

                        <form onSubmit={handleSubmit}>
                            <TextField
                                fullWidth
                                label={t.login.username}
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                margin="normal"
                                required
                                autoFocus
                                disabled={isLoading}
                            />

                            <TextField
                                fullWidth
                                label={t.login.password}
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                margin="normal"
                                required
                                disabled={isLoading}
                            />

                            <Button
                                fullWidth
                                type="submit"
                                variant="contained"
                                size="large"
                                sx={{ mt: 3 }}
                                disabled={isLoading}
                            >
                                {isLoading ? t.login.loggingIn : t.login.signIn}
                            </Button>
                        </form>

                        <Button
                            fullWidth
                            variant="text"
                            sx={{ mt: 1 }}
                            onClick={() => navigate("/forgot-password")}
                        >
                            {t.login.forgotPassword}
                        </Button>

                    </CardContent>
                </Card>
            </Box>
        </Container>
    );
};
