import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// Доп. шаблоны воронок (пресеты) компании — без «По умолчанию» (его форма добавляет сама).
export type FunnelTemplate = {
  id: string;
  name: string;
  order_index: number;
};

export function useFunnelTemplates() {
  return useQuery({
    queryKey: ['settings', 'funnel-templates'],
    queryFn: async () => {
      const response = await api.get('/settings/funnel-templates');
      return response.data as FunnelTemplate[];
    },
    staleTime: 60_000,
  });
}
