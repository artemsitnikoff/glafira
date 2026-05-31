import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { DefaultFunnelStage } from './useDefaultFunnel';

// Этапы конкретного шаблона воронки. Форма ответа = как у default-funnel
// (stage_key/label/order_index/is_terminal/color). enabled только для реального id шаблона.
export function useFunnelTemplateStages(templateId: string | undefined) {
  return useQuery({
    queryKey: ['settings', 'funnel-templates', templateId, 'stages'],
    queryFn: async () => {
      const response = await api.get(`/settings/funnel-templates/${templateId}/stages`);
      return response.data as DefaultFunnelStage[];
    },
    enabled: !!templateId && templateId !== 'default',
    staleTime: 60_000,
  });
}
