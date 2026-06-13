import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// Локальные типы (openapi не регенерён)
export interface Call {
  id: string;
  direction: 'out' | 'in' | 'missed';
  from_number: string | null;
  to_number: string | null;
  duration_sec: number;
  started_at: string | null;
  has_recording: boolean;
  recruiter_name: string | null;
  transcribe_status: 'none' | 'running' | 'done' | 'error';
  transcript: string | null;
  transcript_segments: any[] | null;
  summary: string | null;
  ai_hint: string | null;
  ai_hint_tone: 'warn' | 'good' | null;
  transcribe_error: string | null;
}

export function useCalls(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'calls'],
    queryFn: async (): Promise<Call[]> => {
      const response = await api.get(`/candidates/${candidateId}/calls`);
      return response.data as Call[];
    },
    enabled: !!candidateId,
    refetchInterval: (query) => {
      // Поллинг если есть звонок в процессе расшифровки
      const data = query.state.data as Call[] | undefined;
      const hasTranscribing = data?.some((call: Call) => call.transcribe_status === 'running');
      return hasTranscribing ? 2500 : false;
    },
  });
}