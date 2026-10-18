import { useQuery, useMutation, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import { api } from '../client';

export interface AiModelOption {
  value: string;
  label: string;
  /** Оценка стоимости анализа одного резюме в USD (null — цена недоступна) */
  cost_usd?: number | null;
  /** Та же оценка в рублях по ориентировочному курсу (null — цена недоступна) */
  cost_rub?: number | null;
  /** Размер контекстного окна модели в токенах (null — неизвестно) */
  context_length?: number | null;
}

export interface AiModelResponse {
  current: string;
  options: AiModelOption[];
  /** Задан ли per-company ключ OpenRouter (нужен для live-цен) */
  has_openrouter_key?: boolean;
}

export interface AiModelSearchResponse {
  options: AiModelOption[];
}

export interface UpdateAiModelRequest {
  model: string;
  /** Новый ключ OpenRouter; пустой/отсутствует — текущий ключ не трогаем */
  openrouter_api_key?: string;
}

// Получение текущей AI-модели и рекомендованного шорт-листа с live-ценами
export function useAiModel() {
  return useQuery({
    queryKey: ['settings', 'ai-model'],
    queryFn: async (): Promise<AiModelResponse> => {
      const response = await api.get('/settings/ai-model');
      return response.data as AiModelResponse;
    },
  });
}

// Поиск по всем моделям OpenRouter (для выбора «любой» модели).
// Запрос уходит только при длине строки >= 2 символов.
export function useAiModelSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: ['settings', 'ai-model-search', q],
    queryFn: async (): Promise<AiModelSearchResponse> => {
      const response = await api.get('/settings/ai-model/search', { params: { q } });
      return response.data as AiModelSearchResponse;
    },
    enabled: q.length >= 2,
    placeholderData: keepPreviousData,
  });
}

// Обновление AI-модели (и, опционально, ключа OpenRouter)
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
