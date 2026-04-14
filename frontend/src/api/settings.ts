import apiClient from './client';

export interface Setting {
    key: string;
    value: any;
    description?: string;
    category: string;
    updated_at: string;
}

export interface SettingUpdate {
    value: any;
    description?: string;
}

export const settingsApi = {
    getAll: async () => {
        const response = await apiClient.get<Setting[]>('/settings');
        return response.data;
    },
    getPublic: async () => {
        const response = await apiClient.get('/settings/public');
        return response.data;
    },
    getByKey: async (key: string) => {
        const response = await apiClient.get<Setting>(`/settings/${key}`);
        return response.data;
    },
    update: async (key: string, data: SettingUpdate) => {
        const response = await apiClient.put<Setting>(`/settings/${key}`, data);
        return response.data;
    },
    bulkUpdate: async (settings: { key: string, value: any, category?: string, description?: string }[]) => {
        const response = await apiClient.post<Setting[]>('/settings/bulk', settings);
        return response.data;
    },
    uploadLogo: async (file: File): Promise<any> => {
        const formData = new FormData();
        formData.append('file', file);
        const response = await apiClient.post('/settings/upload-logo', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
        });
        return response.data;
    },
};
