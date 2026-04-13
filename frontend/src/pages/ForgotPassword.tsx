/**
 * Forgot password page — request a password reset link.
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Box, Card, CardContent, TextField, Button, Typography, Alert, Container, CircularProgress
} from '@mui/material';
import apiClient from '@/api/client';

export const ForgotPasswordPage: React.FC = () => {
    const navigate = useNavigate();
    const [email, setEmail] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            await apiClient.post('/auth/forgot-password', { email });
            setSuccess(true);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to send reset email');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <Container maxWidth="sm">
            <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" minHeight="100vh">
                <Card sx={{ width: '100%', maxWidth: 450 }}>
                    <CardContent sx={{ p: 4 }}>
                        <Typography variant="h4" component="h1" gutterBottom align="center">
                            PowerHouse
                        </Typography>
                        <Typography variant="h6" color="text.secondary" align="center" mb={3}>
                            Reset Your Password
                        </Typography>

                        {success ? (
                            <Box>
                                <Alert severity="success" sx={{ mb: 2 }}>
                                    If an account with that email exists, a reset link has been sent.
                                </Alert>
                                <Button fullWidth variant="outlined" onClick={() => navigate('/login')} sx={{ mt: 2 }}>
                                    Back to Login
                                </Button>
                            </Box>
                        ) : (
                            <form onSubmit={handleSubmit}>
                                {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                                <Typography variant="body2" color="text.secondary" mb={2}>
                                    Enter your email address and we'll send you a link to reset your password.
                                </Typography>
                                <TextField
                                    fullWidth label="Email" type="email"
                                    value={email} onChange={(e) => setEmail(e.target.value)}
                                    margin="normal" required disabled={isLoading} autoFocus
                                />
                                <Button fullWidth type="submit" variant="contained" size="large" sx={{ mt: 3 }} disabled={isLoading}>
                                    {isLoading ? <CircularProgress size={24} /> : 'Send Reset Link'}
                                </Button>
                                <Button fullWidth variant="text" onClick={() => navigate('/login')} sx={{ mt: 1 }}>
                                    Back to Login
                                </Button>
                            </form>
                        )}
                    </CardContent>
                </Card>
            </Box>
        </Container>
    );
};
