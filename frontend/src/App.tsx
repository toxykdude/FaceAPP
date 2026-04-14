/**
 * Main application component with routing.
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { MainLayout } from '@/components/Layout/MainLayout';
import { LoginPage } from '@/pages/Login';
import { ForgotPasswordPage } from '@/pages/ForgotPassword';
import { ResetPasswordPage } from '@/pages/ResetPassword';
import { Dashboard } from '@/pages/Dashboard';
import { MembersList } from '@/pages/Members/MembersList';
import { MemberForm } from '@/pages/Members/MemberForm';
import { MembershipsList } from '@/pages/Memberships/MembershipsList';
import { MembershipForm } from '@/pages/Memberships/MembershipForm';
import { CamerasList } from '@/pages/Cameras/CamerasList';
import { FaceEnrollment } from '@/pages/Members/FaceEnrollment';
import { Kiosk } from '@/pages/Kiosk/Kiosk';
import { SettingsPage } from '@/pages/Settings/Settings';
import { Reports } from '@/pages/Reports/Reports';
import { SalesList } from '@/pages/Sales/SalesList';

// Create React Query client
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            refetchOnWindowFocus: false,
            retry: 1,
        },
    },
});

function App() {
    return (
        <QueryClientProvider client={queryClient}>
            <AuthProvider>
                <BrowserRouter>
                    <Routes>
                        <Route path="/login" element={<LoginPage />} />
                        <Route path="forgot-password" element={<ForgotPasswordPage />} />
                        <Route path="reset-password" element={<ResetPasswordPage />} />
                        <Route
                            path="/kiosk"
                            element={
                                <ProtectedRoute>
                                    <Kiosk />
                                </ProtectedRoute>
                            }
                        />
                        <Route
                            path="/"
                            element={
                                <ProtectedRoute>
                                    <MainLayout />
                                </ProtectedRoute>
                            }
                        >
                            <Route index element={<Dashboard />} />
                            <Route path="members" element={<MembersList />} />
                            <Route path="members/new" element={<MemberForm />} />
                            <Route path="members/:id/edit" element={<MemberForm />} />
                            <Route path="members/:id/membership" element={<MemberForm />} />
                            <Route path="members/:id/enroll" element={<FaceEnrollment />} />
                            <Route path="memberships" element={<MembershipsList />} />
                            <Route path="memberships/new" element={<MembershipForm />} />
                            <Route path="sales" element={<SalesList />} />
                            <Route path="cameras" element={<CamerasList />} />
                            <Route path="reports" element={<Reports />} />
                            <Route path="enrollment" element={<div>Enrollment (Coming Soon)</div>} />
                            <Route path="settings" element={<SettingsPage />} />
                        </Route>
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </BrowserRouter>
            </AuthProvider>
        </QueryClientProvider>
    );
}

export default App;
