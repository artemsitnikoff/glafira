import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// Локальные типы для списка пользователей (openapi не регенерён)
export interface UserListItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  position?: string | null;
  avatar_url?: string | null;
  is_active: boolean;
  source?: string; // 'manual' | 'b24'
  created_at: string;
}

export interface PaginatedUserList {
  items: UserListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

interface UseUsersParams {
  search?: string;
  role?: string;
  is_active?: boolean;
  page?: number;
  page_size?: number;
}

/**
 * Список пользователей компании. `options.enabled` — чтобы не дёргать /users,
 * пока список не нужен (закрытый пикер), и не бить в него ролями, которым
 * эндпоинт запрещён (hiring_manager).
 */
export function useUsers(params: UseUsersParams = {}, options: { enabled?: boolean } = {}) {
  return useQuery({
    enabled: options.enabled ?? true,
    queryKey: ['users', params],
    queryFn: async (): Promise<PaginatedUserList> => {
      const searchParams = new URLSearchParams();

      if (params.search) searchParams.append('search', params.search);
      if (params.role) searchParams.append('role', params.role);
      if (params.is_active !== undefined) searchParams.append('is_active', params.is_active.toString());
      if (params.page) searchParams.append('page', params.page.toString());
      if (params.page_size) searchParams.append('page_size', params.page_size.toString());

      const response = await api.get(`/users?${searchParams.toString()}`);
      return response.data as PaginatedUserList;
    },
  });
}