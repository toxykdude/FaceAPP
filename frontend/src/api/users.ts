/**
 * Users API methods.
 */
import apiClient from './client';

export interface User {
    id: string;
    username: string;
    email?: string;
    full_name?: string;
    role: 'admin' | 'staff';
    is_active: boolean;
    created_at: string;
    last_login?: string;
    permissions?: {
        pages: string[];
    };
}

export interface UserCreate {
    username: string;
    email?: string;
    full_name?: string;
    password: string;
    role: 'admin' | 'staff';
    is_active?: boolean;
    permissions?: {
        pages: string[];
    };
}

export interface UserUpdate {
    username?: string;
    email?: string;
    full_name?: string;
    role?: 'admin' | 'staff';
    is_active?: boolean;
    permissions?: {
        pages: string[];
    };
}

export interface PasswordChange {
    current_password?: string;
    new_password: string;
}

/** Paginated wrapper returned by GET /users. */
export interface UserListResponse {
    total: number;
    users: User[];
}

export const usersApi = {
    /**
     * Get all users.
     */
    getUsers: async (): Promise<User[]> => {
        const response = await apiClient.get<UserListResponse>('/users');
        return response.data.users;
    },

    /**
     * Create a new user.
     */
    createUser: async (data: UserCreate): Promise<User> => {
        const response = await apiClient.post<User>('/users', data);
        return response.data;
    },

    /**
     * Get user by ID.
     */
    getUser: async (id: string): Promise<User> => {
        const response = await apiClient.get<User>(`/users/${id}`);
        return response.data;
    },

    /**
     * Update user.
     */
    updateUser: async (id: string, data: UserUpdate): Promise<User> => {
        const response = await apiClient.put<User>(`/users/${id}`, data);
        return response.data;
    },

    /**
     * Delete user.
     */
    deleteUser: async (id: string): Promise<void> => {
        await apiClient.delete(`/users/${id}`);
    },

    /**
     * Change user password.
     */
    changePassword: async (id: string, data: PasswordChange): Promise<void> => {
        await apiClient.post(`/users/${id}/change-password`, data);
    },
};

export default usersApi;
