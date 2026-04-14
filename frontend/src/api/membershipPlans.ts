/**
 * Membership Plans API methods.
 */
import apiClient from './client';

export interface MembershipPlan {
    id: string;
    name: string;
    duration_days: number;
    duration_months: number | null;
    price: number;
    description?: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export const membershipPlansApi = {
    /**
     * Get all membership plans.
     */
    getPlans: async (activeOnly = false): Promise<{ total: number; plans: MembershipPlan[] }> => {
        const response = await apiClient.get('/membership-plans', {
            params: { active_only: activeOnly },
        });
        return response.data;
    },

    /**
     * Create a new membership plan.
     */
    createPlan: async (data: Partial<MembershipPlan>): Promise<MembershipPlan> => {
        const response = await apiClient.post('/membership-plans', data);
        return response.data;
    },

    /**
     * Update a membership plan.
     */
    updatePlan: async (id: string, data: Partial<MembershipPlan>): Promise<MembershipPlan> => {
        const response = await apiClient.put(`/membership-plans/${id}`, data);
        return response.data;
    },

    /**
     * Delete a membership plan.
     */
    deletePlan: async (id: string): Promise<void> => {
        await apiClient.delete(`/membership-plans/${id}`);
    },
};

export default membershipPlansApi;
