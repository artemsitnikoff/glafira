import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// Локальный тип (openapi не регенерён): архивная вакансия с агрегатами.
export interface ArchivedVacancyItem {
  id: string;
  name: string;
  client_name: string | null;
  recruiter_name: string | null;
  archive_result: string | null; // 'hired' | 'cancelled' | 'frozen'
  closed_at: string | null;      // ISO date
  created_at: string;            // ISO datetime
  candidates: number;            // всего заявок прошло
  hired: number;                 // заявок в этапе hired
}

export function useArchivedVacancies() {
  return useQuery({
    queryKey: ['vacancies', 'archived'],
    queryFn: async (): Promise<ArchivedVacancyItem[]> => {
      const response = await api.get('/vacancies/archived');
      return response.data as ArchivedVacancyItem[];
    },
  });
}
