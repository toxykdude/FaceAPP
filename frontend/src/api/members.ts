/**
 * Members API methods.
 */
import apiClient from './client';

export interface Member {
    id: string;
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    id_number?: string;  // Cédula / personal ID
    date_of_birth?: string;
    address?: string;
    status: 'active' | 'inactive' | 'suspended';
    facial_data_enrolled: boolean;
    consent_given: boolean;
    created_at: string;
    updated_at: string;
    membership_status: string | null;
    membership_end_date: string | null;
    membership_plan_name: string | null;
}

export interface MemberCreate {
    first_name: string;
    last_name: string;
    email: string;
    phone: string;
    id_number?: string;  // Cédula / personal ID
    date_of_birth?: string;
    address?: string;
    consent_given: boolean;
}

export interface MemberUpdate {
    first_name?: string;
    last_name?: string;
    email?: string;
    phone?: string;
    date_of_birth?: string;
    address?: string;
    status?: 'active' | 'inactive' | 'suspended';
    // Grant (true) or withdraw (false) biometric consent. Withdrawing also
    // deletes the member's enrolled face server-side. Omit to leave unchanged.
    consent_given?: boolean;
}

export interface MembersListParams {
    skip?: number;
    limit?: number;
    search?: string;
    status?: string;
}

export interface MembersListResponse {
    total: number;
    members: Member[];
}

export interface BiometricStatus {
    enrolled: boolean;
    template_count: number;
    last_updated?: string;
}

export interface EnrollmentRequest {
    id: string;
    status: 'pending' | 'processing' | 'complete' | 'failed' | 'cancelled';
    quality_score: number | null;
    result_message: string | null;
    member_name: string | null;
    member_id: string;
    device_id: string;
    created_at: string;
    updated_at: string;
}

export const membersApi = {
    /**
     * Get list of members with pagination and filtering.
     */
    getMembers: async (params?: MembersListParams): Promise<MembersListResponse> => {
        const response = await apiClient.get<MembersListResponse>('/members', { params });
        return response.data;
    },

    /**
     * Get member by ID.
     */
    getMember: async (id: string): Promise<Member> => {
        const response = await apiClient.get<Member>(`/members/${id}`);
        return response.data;
    },

    /**
     * Create new member.
     */
    createMember: async (data: MemberCreate): Promise<Member> => {
        const response = await apiClient.post<Member>('/members', data);
        return response.data;
    },

    /**
     * Update member.
     */
    updateMember: async (id: string, data: MemberUpdate): Promise<Member> => {
        const response = await apiClient.put<Member>(`/members/${id}`, data);
        return response.data;
    },

    /**
     * Delete member.
     */
    deleteMember: async (id: string): Promise<void> => {
        await apiClient.delete(`/members/${id}`);
    },

    /**
     * Get biometric enrollment status.
     */
    getBiometricStatus: async (id: string): Promise<BiometricStatus> => {
        const response = await apiClient.get<BiometricStatus>(`/members/${id}/biometric-status`);
        return response.data;
    },

    /**
     * Upload face image for biometric enrollment.
     */
    enrollBiometric: async (id: string, file: File): Promise<any> => {
        const formData = new FormData();
        formData.append('image', file);
        const response = await apiClient.post(`/enrollment/${id}/enroll`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        });
        return response.data;
    },

    /**
     * Enroll face from connected camera.
     */
    enrollBiometricFromCamera: async (id: string, cameraId: string): Promise<any> => {
        const response = await apiClient.post(`/enrollment/${id}/enroll/camera`, { camera_id: cameraId });
        return response.data;
    },

    /**
     * Create a tablet enrollment request.
     */
    createEnrollmentRequest: async (memberId: string): Promise<EnrollmentRequest> => {
        const response = await apiClient.post<EnrollmentRequest>('/enrollment-requests', {
            member_id: memberId,
            device_id: 'kiosk-android',
        });
        return response.data;
    },

    /**
     * Get enrollment request status by ID.
     */
    getEnrollmentRequest: async (requestId: string): Promise<EnrollmentRequest> => {
        const response = await apiClient.get<EnrollmentRequest>(`/enrollment-requests/${requestId}`);
        return response.data;
    },

    /**
     * Cancel an enrollment request.
     */
    cancelEnrollmentRequest: async (requestId: string): Promise<void> => {
        await apiClient.post(`/enrollment-requests/${requestId}/cancel`);
    },
};
