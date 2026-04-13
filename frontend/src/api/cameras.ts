/**
 * Cameras API methods.
 */
import apiClient from './client';

export interface Camera {
    id: string;
    name: string;
    description: string;
    rtsp_url?: string;
    location: string;
    enabled: boolean;
    created_at: string;
    updated_at: string;
}

export interface CameraCreate {
    name: string;
    description?: string;
    rtsp_url: string;
    location?: string;
    enabled?: boolean;
}

export interface CameraUpdate {
    name?: string;
    description?: string;
    rtsp_url?: string;
    location?: string;
    enabled?: boolean;
}

export interface VideoDevice {
    path: string;
    name: string;
}

export const camerasApi = {
    /**
     * Get all cameras.
     */
    getCameras: async (skip = 0, limit = 100): Promise<Camera[]> => {
        const response = await apiClient.get<{ total: number; cameras: Camera[] }>('/cameras', {
            params: { skip, limit },
        });
        return response.data.cameras;
    },

    /**
     * Create a new camera.
     */
    createCamera: async (data: CameraCreate): Promise<Camera> => {
        const response = await apiClient.post<Camera>('/cameras', data);
        return response.data;
    },

    /**
     * Get camera details by ID.
     */
    getCamera: async (id: string): Promise<Camera> => {
        const response = await apiClient.get<Camera>(`/cameras/${id}`);
        return response.data;
    },

    /**
     * Update camera details.
     */
    updateCamera: async (id: string, data: CameraUpdate): Promise<Camera> => {
        const response = await apiClient.put<Camera>(`/cameras/${id}`, data);
        return response.data;
    },

    /**
     * Delete a camera.
     */
    deleteCamera: async (id: string): Promise<void> => {
        await apiClient.delete(`/cameras/${id}`);
    },

    /**
     * Detect available video devices on server.
     */
    detectDevices: async (): Promise<VideoDevice[]> => {
        const response = await apiClient.get<{ devices: VideoDevice[] }>('/cameras/devices/detect');
        return response.data.devices;
    },

    /**
     * Test camera connection.
     */
    testCamera: async (id: string): Promise<{ status: string; message: string }> => {
        const response = await apiClient.post<{ status: string; message: string }>(`/cameras/${id}/test`);
        return response.data;
    },

    /**
     * Get decrypted RTSP URL (Admin only).
     */
    getRtspUrl: async (id: string): Promise<{ rtsp_url: string }> => {
        const response = await apiClient.get<{ rtsp_url: string }>(`/cameras/${id}/rtsp-url`);
        return response.data;
    },
};

export default camerasApi;
