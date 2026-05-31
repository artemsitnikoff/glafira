import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// Тела запросов — 1:1 с бэком (CompanyDefaultStageCreate/Update/Reorder),
// тот же контракт, что и у этапов живой вакансии (/vacancies/{id}/stages).
type StageCreate = {
  stage_key: string;
  label: string;
  order_index: number;
  is_terminal: boolean;
};

type StageUpdate = {
  label: string;
};

type StageReorder = {
  order: string[]; // список stage_key в новом порядке
};

const DEFAULT_FUNNEL_KEY = ['settings', 'default-funnel'];

export function useAddDefaultFunnelStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: StageCreate) => {
      const response = await api.post('/settings/default-funnel', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEFAULT_FUNNEL_KEY });
    },
  });
}

export function useRenameDefaultFunnelStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ stageKey, data }: { stageKey: string; data: StageUpdate }) => {
      const response = await api.patch(`/settings/default-funnel/${stageKey}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEFAULT_FUNNEL_KEY });
    },
  });
}

export function useDeleteDefaultFunnelStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (stageKey: string) => {
      const response = await api.delete(`/settings/default-funnel/${stageKey}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEFAULT_FUNNEL_KEY });
    },
  });
}

export function useReorderDefaultFunnelStages() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: StageReorder) => {
      const response = await api.put('/settings/default-funnel/reorder', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DEFAULT_FUNNEL_KEY });
    },
  });
}
