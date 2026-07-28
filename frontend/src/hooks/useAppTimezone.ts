/**
 * useAppTimezone — resolve the configured IANA timezone from public settings.
 *
 * The backend exposes `timezone` via GET /settings/public. This hook caches it
 * through TanStack Query (shared cache key `public-settings` so it dedupes
 * with Login/MainLayout) and returns the zone name, defaulting to
 * America/Bogota while loading or if unset.
 */
import { useQuery } from '@tanstack/react-query';
import { settingsApi } from '@/api/settings';

const DEFAULT_TIMEZONE = 'America/Bogota';

export function useAppTimezone(): string {
    const { data } = useQuery({
        queryKey: ['public-settings'],
        queryFn: settingsApi.getPublic,
        staleTime: 5 * 60 * 1000,
    });
    const tz = data?.timezone;
    return typeof tz === 'string' && tz.trim() ? tz : DEFAULT_TIMEZONE;
}
