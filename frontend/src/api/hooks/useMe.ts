import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { UserMe } from '../aliases';
import { useAuthStore } from '@/store/authStore';

export function useMe() {
  const token = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const response = await api.get<UserMe>('/auth/me');
      return response.data;
    },
    enabled: !!token,
  });
}