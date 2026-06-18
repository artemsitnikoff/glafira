import { useMutation } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AxiosError } from 'axios';

interface ParseVacancyFields {
  name?: string | null;
  city?: string | null;
  department?: string | null;
  employment_type?: string | null;
  salary_from?: number | null;
  salary_to?: number | null;
  description?: string | null;
}

export interface ParseVacancyResponse {
  parsed: boolean;
  reason: string | null;
  fields: ParseVacancyFields;
}

export function useParseVacancyFile() {
  return useMutation({
    mutationFn: async (file: File): Promise<ParseVacancyResponse> => {
      const formData = new FormData();
      formData.append('file', file);

      try {
        const response = await api.post<ParseVacancyResponse>(
          '/vacancies/parse-file',
          formData,
          {
            headers: {
              'Content-Type': 'multipart/form-data',
            },
          }
        );
        return response.data;
      } catch (err) {
        const axiosErr = err as AxiosError<{ error?: { code?: string; message?: string } }>;
        // Пробрасываем message бэкенда для OPENROUTER_NOT_CONFIGURED (400)
        const apiMessage = axiosErr.response?.data?.error?.message;
        if (apiMessage) {
          throw new Error(apiMessage);
        }
        throw err;
      }
    },
  });
}
