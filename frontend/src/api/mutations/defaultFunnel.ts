import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

type StageCreate = {
  name: string;
  type: 'middle';
  description?: string;
};

type StageUpdate = {
  name: string;
};

type StageReorder = {
  stage_keys: string[];
};

export function useAddDefaultFunnelStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: StageCreate) => {
      const response = await api.post('/settings/default-funnel', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'default-funnel'] });
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
      queryClient.invalidateQueries({ queryKey: ['settings', 'default-funnel'] });
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
      queryClient.invalidateQueries({ queryKey: ['settings', 'default-funnel'] });
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
      queryClient.invalidateQueries({ queryKey: ['settings', 'default-funnel'] });
    },
  });
}