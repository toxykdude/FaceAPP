/**
 * Memberships API methods.
 */
import apiClient from './client';

export interface Membership {
    id: string;
    member_id: string;
    plan_id?: string;
    type: string;
    start_date: string;
    end_date: string;
    price: number;
    status: 'active' | 'expired' | 'cancelled' | 'suspended';
    created_at: string;
    updated_at: string;
    member_name?: string;
    member_id_number?: string;
    plan_name?: string;
}

export interface MembershipCreate {
    member_id: string;
    plan_id?: string;
    type: string;
    start_date: string;
    end_date: string;
    price: number;
}

export const membershipsApi = {
    /**
     * Get all memberships with pagination.
     */
    getMemberships: async (skip = 0, limit = 100, memberId?: string, status?: string): Promise<Membership[]> => {
        // Handle backend response format {total, memberships} or legacy array?
        // Backend `list_memberships` returns {total, memberships}.
        // Frontend expects array currently in `useQuery` but `apiClient.get<Membership[]>` assumes array?
        // Let's check backend response schema `MembershipListResponse`.
        const response = await apiClient.get<any>('/memberships', {
            params: { skip, limit, member_id: memberId, status },
        });
        return response.data.memberships || response.data; // Flexible
    },

    /**
     * Create a new membership for a member.
     */
    createMembership: async (data: MembershipCreate): Promise<Membership> => {
        const response = await apiClient.post<Membership>('/memberships', data);
        return response.data;
    },

    /**
     * Get membership details by ID.
     */
    getMembership: async (id: string): Promise<Membership> => {
        const response = await apiClient.get<Membership>(`/memberships/${id}`);
        return response.data;
    },

    /**
     * Update a membership (dates, price, status, etc).
     */
    updateMembership: async (id: string, data: Partial<Omit<MembershipCreate, 'member_id'>>): Promise<Membership> => {
        const response = await apiClient.put<Membership>(`/memberships/${id}`, data);
        return response.data;
    },

    /**
     * Cancel a membership.
     */
    cancelMembership: async (id: string): Promise<Membership> => {
        const response = await apiClient.post<Membership>(`/memberships/${id}/cancel`);
        return response.data;
    },
};

export default membershipsApi;
