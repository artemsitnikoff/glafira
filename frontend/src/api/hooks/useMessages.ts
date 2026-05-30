import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { MessageOut } from '@/api/aliases';

export function useMessages(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'messages'],
    // Эндпоинт отдаёт Paginated{items,...} — берём items (список сообщений)
    queryFn: async () => (await api.get<{ items: MessageOut[] }>(`/candidates/${candidateId}/messages`)).data.items,
    enabled: !!candidateId,
  });
}