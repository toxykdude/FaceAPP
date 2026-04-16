/**
 * Permission guard for routes.
 * Redirects to dashboard if user lacks the required page permission.
 */
import React from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

interface RequirePermissionProps {
    page: string;
    children: React.ReactNode;
}

export const RequirePermission: React.FC<RequirePermissionProps> = ({ page, children }) => {
    const { user } = useAuth();

    if (!user) return <Navigate to="/login" replace />;

    // Admin always has access
    if (user.role === "admin") return <>{children}</>;

    // Check pages array
    const pages = (user as any).permissions?.pages || [];
    if (pages.includes("all") || pages.includes(page)) {
        return <>{children}</>;
    }

    // No permission — redirect to dashboard
    return <Navigate to="/" replace />;
};
