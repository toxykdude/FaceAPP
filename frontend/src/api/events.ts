/**
 * Access Events API methods.
 */
import apiClient from './client';

export interface AccessEvent {
    id: string;
    member_id: string;
    camera_id: string;
    event_type: 'check_in' | 'check_out' | 'unauthorized';
    confidence: number;
    confidence_score?: number;
    image_path: string;
    timestamp: string;
    member_name?: string;
    camera_name?: string;
}

export const eventsApi = {
    /**
     * Get all access events with filters.
     */
    getEvents: async (skip = 0, limit = 50, member_id?: string, camera_id?: string): Promise<{ total: number, events: AccessEvent[] }> => {
        const response = await apiClient.get('/events', {
            params: { skip, limit, member_id, camera_id },
        });
        return response.data;
    },

    /**
     * Get recent access events.
     */
    getRecentEvents: async (limit = 10): Promise<AccessEvent[]> => {
        const response = await apiClient.get('/events', {
            params: { limit, skip: 0 },
        });
        return response.data.events;
    },

    /**
     * Get event details by ID.
     */
    getEvent: async (id: string): Promise<AccessEvent> => {
        const response = await apiClient.get<AccessEvent>(`/events/${id}`);
        return response.data;
    },
};

export default eventsApi;
