import { useMutation } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AxiosError } from 'axios';

export interface GenerateRubricRequest {
  name?: string | null;
  description?: string | null;
  city?: string | null;
  department?: string | null;
  employment_type?: string | null;
  salary_from?: number | null;
  salary_to?: number | null;
}

export interface GenerateRubricResponse {
  generated: boolean;
  reason: string | null;
  rubric: string | null;
}

export function useGenerateRubric() {
  return useMutation({
    mutationFn: async (body: GenerateRubricRequest): Promise<GenerateRubricResponse> => {
      try {
        const response = await api.post<GenerateRubricResponse>(
          '/vacancies/generate-rubric',
          body
        );
        return response.data;
      } catch (err) {
        const axiosErr = err as AxiosError<{ error?: { code?: string; message?: string } }>;
        const apiMessage = axiosErr.response?.data?.error?.message;
        if (apiMessage) {
          throw new Error(apiMessage);
        }
        throw err;
      }
    },
  });
}
