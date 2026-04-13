/**
 * Password reset page — accessed via email link.
 */
import React, { useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
    Box, Card, CardContent, TextField, Button, Typography, Alert, Container, CircularProgress
} from '@mui/material';
import apiClient from '@/api/client';

export const ResetPasswordPage: React.FC = () => {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get('token') || '';

    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [success, setSuccess] = useState(false);
    const [isLoading, setIsLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (newPassword.length < 8) {
            setError('Password must be at least 8 characters');
            return;
        }
        if (newPassword !== confirmPassword) {
            setError('Passwords do not match');
            return;
        }
        if (!token) {
            setError('Invalid reset link');
            return;
        }

        setIsLoading(true);
        try {
            await apiClient.post('/auth/reset-password', { token, new_password: newPassword });
            setSuccess(true);
            setTimeout(() => navigate('/login'), 3000);
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to reset password');
        } finally {
            setIsLoading(false);
        }
    };

    if (!token) {
        return (
            <Container maxWidth="sm">
                <Box display="flex" justifyContent="center" alignItems="center" minHeight="100vh">
                    <Alert severity="error">Invalid or missing reset token. Please request a new password reset link.</Alert>
                </Box>
            </Container>
        );
    }

    return (
        <Container maxWidth="sm">
            <Box display="flex" flexDirection="column" justifyContent="center" alignItems="center" minHeight="100vh">
                <Card sx={{ width: '100%', maxWidth: 450 }}>
                    <CardContent sx={{ p: 4 }}>
                        <Typography variant="h4" component="h1" gutterBottom align="center">
                            Reset Password
                        </Typography>
                        <Typography variant="body2" color="text.secondary" align="center" mb={3}>
                            Enter your new password
                        </Typography>

                        {success ? (
                            <Alert severity="success">
                                Password reset successfully! Redirecting to login...
                            </Alert>
                        ) : (
                            <form onSubmit={handleSubmit}>
                                {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
                                <TextField
                                    fullWidth label="New Password" type="password"
                                    value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                                    margin="normal" required disabled={isLoading}
                                />
                                <TextField
                                    fullWidth label="Confirm Password" type="password"
                                    value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                                    margin="normal" required disabled={isLoading}
                                />
                                <Button fullWidth type="submit" variant="contained" size="large"
                                    sx={{ mt: 3 }} disabled={isLoading}>
                                    {isLoading ? <CircularProgress size={24} /> : 'Reset Password'}
                                </Button>
                            </form>
                        )}
                    </CardContent>
                </Card>
            </Box>
        </Container>
    );
};
