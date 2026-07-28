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

/**
 * Masked remote-backup configuration as returned by the admin-only
 * GET /system/backup-config. `has_password` is the only password signal —
 * plaintext/ciphertext are never exposed.
 */
export interface BackupConfig {
    type: string;
    host: string;
    port: number | null;
    share: string;
    path: string;
    username: string;
    has_password: boolean;
}

/**
 * Write payload for PUT /system/backup-config. `password` omitted or "" keeps
 * the stored secret (keep-sentinel); any non-empty value replaces it.
 */
export interface BackupConfigInput {
    type: string;
    host?: string;
    port?: number | null;
    share?: string;
    path?: string;
    username?: string;
    password?: string;
}

/** Sanitized connection-probe result from POST /system/backup-config/test. */
export interface BackupTestResult {
    ok: boolean;
    message: string;
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
    /**
     * Download a fresh custom-format database dump (GET /system/db-export).
     * Admin-only on the server. Returns a Blob so the caller can trigger a
     * client-side download with an object URL.
     */
    exportDatabase: async (): Promise<Blob> => {
        const response = await apiClient.get('/system/db-export', {
            responseType: 'blob',
        });
        return response.data;
    },
    /**
     * Fetch the masked remote-backup configuration (admin-only).
     * Never returns the password or its ciphertext.
     */
    getBackupConfig: async (): Promise<BackupConfig> => {
        const response = await apiClient.get<BackupConfig>('/system/backup-config');
        return response.data;
    },
    /**
     * Persist the remote-backup configuration (admin-only). Send an empty/omitted
     * `password` to keep the current secret; any other value replaces it.
     */
    putBackupConfig: async (data: BackupConfigInput): Promise<BackupConfig> => {
        const response = await apiClient.put<BackupConfig>('/system/backup-config', data);
        return response.data;
    },
    /**
     * Run the bounded, sanitized connection probe against the stored
     * configuration (admin-only). Returns {ok, message} with no secrets/banners.
     */
    testBackupConfig: async (): Promise<BackupTestResult> => {
        const response = await apiClient.post<BackupTestResult>('/system/backup-config/test');
        return response.data;
    },
};
