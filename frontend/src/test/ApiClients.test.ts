import { describe, it, expect } from 'vitest';

// Test that API client modules export correctly
describe('API Client Modules', () => {
  it('membersApi exports expected methods', async () => {
    const { membersApi } = await import('../api/members');
    expect(typeof membersApi.getMembers).toBe('function');
    expect(typeof membersApi.getMember).toBe('function');
    expect(typeof membersApi.createMember).toBe('function');
    expect(typeof membersApi.updateMember).toBe('function');
    expect(typeof membersApi.deleteMember).toBe('function');
  });

  it('eventsApi exports expected methods', async () => {
    const { eventsApi } = await import('../api/events');
    expect(typeof eventsApi.getEvents).toBe('function');
    expect(typeof eventsApi.getRecentEvents).toBe('function');
  });

  it('salesApi exports expected methods', async () => {
    const { salesApi } = await import('../api/sales');
    expect(typeof salesApi.getTransactions).toBe('function');
    expect(typeof salesApi.createTransaction).toBe('function');
    expect(typeof salesApi.getReportSummary).toBe('function');
  });

  it('membershipPlansApi exports expected methods', async () => {
    const { membershipPlansApi } = await import('../api/membershipPlans');
    expect(typeof membershipPlansApi.getPlans).toBe('function');
    expect(typeof membershipPlansApi.createPlan).toBe('function');
    expect(typeof membershipPlansApi.updatePlan).toBe('function');
    expect(typeof membershipPlansApi.deletePlan).toBe('function');
  });
});
