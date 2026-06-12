import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';

export interface AiModelOption {
  value: string;
  label: string;
}

export interface AiModelResponse {
  current: string;
  options: AiModelOption[];
}

export interface UpdateAiModelRequest {
  model: string;
}

// Получение текущей AI-модели и доступных опций
export function useAiModel() {
  return useQuery({
    queryKey: ['settings', 'ai-model'],
    queryFn: async (): Promise<AiModelResponse> => {
      const response = await api.get('/settings/ai-model');
      return response.data as AiModelResponse;
    },
  });
}

// Обновление AI-модели
export function useUpdateAiModel() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (request: UpdateAiModelRequest): Promise<AiModelResponse> => {
      const response = await api.patch('/settings/ai-model', request);
      return response.data as AiModelResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai-model'] });
    },
  });
}