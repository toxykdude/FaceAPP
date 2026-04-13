/**
 * CV Service API client.
 * Proxied via Nginx at /cv/
 */
import axios from 'axios';

// Create a dedicated client for CV service
const cvClient = axios.create({
    baseURL: '/cv', // Nginx proxy handles the port 8001
    timeout: 10000,
});

export interface StartCameraRequest {
    camera_id: string;
    rtsp_url: string;
    fps?: number;
}

export interface StopCameraRequest {
    camera_id: string;
}

export const cvServiceApi = {
    /**
     * Start processing a camera stream.
     */
    startCamera: async (data: StartCameraRequest) => {
        const response = await cvClient.post('/cameras/start', data);
        return response.data;
    },

    /**
     * Stop processing a camera stream.
     */
    stopCamera: async (data: StopCameraRequest) => {
        const response = await cvClient.post('/cameras/stop', data);
        return response.data;
    },

    /**
     * Get stream URL for a camera.
     * Note: This returns the URL string to be used in img src.
     */
    getStreamUrl: (cameraId: string) => {
        // We use the proxy path
        return `/cv/stream/${cameraId}`;
    }
};
