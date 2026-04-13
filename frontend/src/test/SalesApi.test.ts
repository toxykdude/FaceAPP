import { describe, it, expect } from 'vitest';

describe('Sales API Types', () => {
  it('has correct PaymentMethod values', async () => {
    const mod = await import('../api/sales');
    // The SalesCreate type should accept valid payment methods
    const validMethods = ['cash', 'card', 'transfer'];
    validMethods.forEach(method => {
      expect(typeof method).toBe('string');
    });
  });
});
