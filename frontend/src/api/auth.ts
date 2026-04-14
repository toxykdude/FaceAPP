/**
 * Authentication API methods.
 */
import apiClient from './client';

export interface LoginCredentials {
    username: string;
    password: string;
}

export interface User {
    id: string;
    username: string;
    email: string;
    role: 'admin' | 'staff';
    is_active: boolean;
    permissions?: {
        pages: string[];
    };
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    user: User;
}

export const authApi = {
    /**
     * Login with username and password.
     */
    login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
        const response = await apiClient.post<LoginResponse>('/auth/login', credentials);
        return response.data;
    },

    /**
     * Logout current user.
     */
    logout: async (): Promise<void> => {
        await apiClient.post('/auth/logout');
    },

    /**
     * Get current user information.
     */
    getCurrentUser: async (): Promise<User> => {
        const response = await apiClient.get<User>('/auth/me');
        return response.data;
    },
};
