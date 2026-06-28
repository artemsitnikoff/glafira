import { useMutation } from '@tanstack/react-query';
import { api } from '../client';

// Локальный тип ответа бэкфилла фото (openapi не регенерён — локальный тип + as-cast)
export type PhotoBackfillResult = {
  processed: number;
  updated: number;
  remaining: number;
  quota_exhausted: boolean;
};

export function useBackfillPhotos() {
  return useMutation<PhotoBackfillResult, Error, void>({
    mutationFn: async (): Promise<PhotoBackfillResult> => {
      const response = await api.post('/candidates/photos/backfill?limit=50');
      return response.data as PhotoBackfillResult;
    },
  });
}
