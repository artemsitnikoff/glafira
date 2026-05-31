import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// Форма ответа бэка GET /settings/default-funnel = CompanyDefaultStageOut
// (1:1 как VacancyStageCount: stage_key/label/order_index/is_terminal/color).
// Тип этапа (start/system/middle/finalOk/finalBad) НЕ хранится — выводится на фронте
// той же логикой, что в форме вакансии (см. deriveDefaultStageType ниже).
export type DefaultFunnelStage = {
  stage_key: string;
  label: string;
  order_index: number;
  is_terminal: boolean;
  color?: string | null;
};

export function useDefaultFunnel() {
  return useQuery({
    queryKey: ['settings', 'default-funnel'],
    queryFn: async () => {
      const response = await api.get('/settings/default-funnel');
      return response.data as DefaultFunnelStage[];
    },
    staleTime: 60_000,
  });
}
