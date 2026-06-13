import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// Локальный тип для диалогов (openapi не регенерён)
interface HomeDialog {
  candidate_id: string;
  candidate_name: string;
  vacancy_id: string | null;
  vacancy_name: string | null;
  channel: string;
  preview: string;
  sent_at: string;
  last_sender_type: 'candidate' | 'recruiter' | 'ai';
  waiting: boolean;
}

async function fetchHomeDialogs(): Promise<HomeDialog[]> {
  const response = await api.get('/home/dialogs');
  return response.data;
}

export function useHomeDialogs() {
  return useQuery({
    queryKey: ['home', 'dialogs'],
    queryFn: fetchHomeDialogs,
    refetchInterval: 15_000, // синхронно с «живой» лентой событий рядом
  });
}