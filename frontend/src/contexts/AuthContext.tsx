/**
 * Authentication context and provider.
 */
import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authApi, User, LoginCredentials } from '@/api/auth';

interface AuthContextType {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    login: (credentials: LoginCredentials) => Promise<void>;
    logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within AuthProvider');
    }
    return context;
};

interface AuthProviderProps {
    children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Load user from localStorage on mount
    useEffect(() => {
        const loadUser = async () => {
            const token = localStorage.getItem('auth_token');
            const storedUser = localStorage.getItem('user');

            if (token && storedUser) {
                try {
                    // Set cached user first
                    const cachedUser = JSON.parse(storedUser);
                    setUser(cachedUser);

                    // Try to verify token with backend (optional)
                    try {
                        const currentUser = await authApi.getCurrentUser();
                        setUser(currentUser);
                        localStorage.setItem('user', JSON.stringify(currentUser));
                    } catch (verifyError) {
                        // If verification fails, keep using cached user
                        console.warn('Token verification failed, using cached user:', verifyError);
                    }
                } catch (error) {
                    // If cached user is invalid, clear storage
                    console.error('Failed to load user:', error);
                    localStorage.removeItem('auth_token');
                    localStorage.removeItem('user');
                    setUser(null);
                }
            }

            setIsLoading(false);
        };

        loadUser();
    }, []);

    const login = async (credentials: LoginCredentials) => {
        const response = await authApi.login(credentials);

        // Store token and user
        localStorage.setItem('auth_token', response.access_token);
        localStorage.setItem('user', JSON.stringify(response.user));

        setUser(response.user);
    };

    const logout = async () => {
        try {
            await authApi.logout();
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            // Clear storage and state
            localStorage.removeItem('auth_token');
            localStorage.removeItem('user');
            setUser(null);
        }
    };

    const value: AuthContextType = {
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
