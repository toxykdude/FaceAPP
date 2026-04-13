/**
 * Sales/Transactions API methods.
 */
import apiClient from './client';

export interface SalesTransaction {
    id: string;
    member_id: string;
    membership_id?: string;
    amount: number;
    payment_method: string;
    invoice_number: string;
    notes?: string;
    transaction_date: string;
    created_at: string;
}

export interface SalesReport {
    total_revenue: number;
    total_transactions: number;
    transactions_by_method: Record<string, number>;
    revenue_by_method: Record<string, number>;
}

export interface SalesListResponse {
    total: number;
    transactions: SalesTransaction[];
}

export interface SalesCreate {
    member_id: string;
    membership_id?: string;
    amount: number;
    payment_method: string;
    notes?: string;
}

export const salesApi = {
    /**
     * List all sales transactions with filters.
     */
    getTransactions: async (params?: {
        skip?: number;
        limit?: number;
        member_id?: string;
        payment_method?: string;
        start_date?: string;
        end_date?: string;
    }): Promise<SalesListResponse> => {
        const response = await apiClient.get<SalesListResponse>('/sales', { params });
        return response.data;
    },

    /**
     * Create a new sales transaction.
     */
    createTransaction: async (data: SalesCreate): Promise<SalesTransaction> => {
        const response = await apiClient.post<SalesTransaction>('/sales', data);
        return response.data;
    },

    /**
     * Get transaction by ID.
     */
    getTransaction: async (id: string): Promise<SalesTransaction> => {
        const response = await apiClient.get<SalesTransaction>(`/sales/${id}`);
        return response.data;
    },

    /**
     * Get sales report summary.
     */
    getReportSummary: async (params?: {
        start_date?: string;
        end_date?: string;
    }): Promise<SalesReport> => {
        const response = await apiClient.get<SalesReport>('/sales/report/summary', { params });
        return response.data;
    },
};
