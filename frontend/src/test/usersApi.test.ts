import { describe, it, expect, vi } from 'vitest';
import apiClient from '@/api/client';
import { usersApi } from '@/api/users';

vi.mock('@/api/client', () => ({
  default: {
    get: vi.fn(),
  },
}));

describe('usersApi.getUsers', () => {
  it('unwraps the paginated wrapper returned by GET /users', async () => {
    const fakeUsers = [
      { id: '1', username: 'alice', role: 'admin', is_active: true, created_at: '2026-01-01T00:00:00Z' },
      { id: '2', username: 'bob', role: 'staff', is_active: true, created_at: '2026-01-02T00:00:00Z' },
    ];
    vi.mocked(apiClient.get).mockResolvedValue({
      data: { total: 2, users: fakeUsers },
    } as any);

    const users = await usersApi.getUsers();

    expect(apiClient.get).toHaveBeenCalledWith('/users');
    expect(Array.isArray(users)).toBe(true);
    expect(users).toHaveLength(2);
    expect(users).toEqual(fakeUsers);
  });
});
