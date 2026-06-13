import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { api } from '../client';
import type { Call } from '../hooks/useCalls';

// Локальные типы (openapi не регенерён)
export interface CallSyncResponse {
  job_id: string;
  status: string;
}

export interface CallSyncJobStatus {
  id: string;
  status: 'running' | 'done' | 'error';
  total: number;
  matched: number;
  created: number;
  error: string | null;
}

export interface TranscribeResponse {
  transcribe_status: 'running';
}

export function useCallSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<CallSyncResponse> => {
      const response = await api.post('/calls/sync');
      return response.data as CallSyncResponse;
    },
    onSuccess: () => {
      // После запуска синхронизации обновим список звонков
      // префикс-инвалидация: ключ useCalls — ['candidates', candidateId, 'calls']
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
    },
  });
}

export function useCallSyncJobStatus(jobId: string | null) {
  return useQuery<CallSyncJobStatus>({
    queryKey: ['calls', 'sync', 'jobs', jobId],
    queryFn: async (): Promise<CallSyncJobStatus> => {
      const response = await api.get(`/calls/sync/jobs/${jobId}`);
      return response.data as CallSyncJobStatus;
    },
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data as CallSyncJobStatus | undefined;
      return data?.status === 'running' ? 2000 : false;
    },
  });
}

export function useTranscribeCall() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (callId: string): Promise<TranscribeResponse> => {
      const response = await api.post(`/calls/${callId}/transcribe`);
      return response.data as TranscribeResponse;
    },
    onSuccess: (_, callId) => {
      // Обновим звонок для поллинга расшифровки
      // префикс-инвалидация: ключ useCalls — ['candidates', candidateId, 'calls']
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      queryClient.invalidateQueries({ queryKey: ['calls', callId] });
    },
  });
}

export function useCall(callId: string | null) {
  return useQuery<Call>({
    queryKey: ['calls', callId],
    queryFn: async (): Promise<Call> => {
      const response = await api.get(`/calls/${callId}`);
      return response.data as Call;
    },
    enabled: !!callId,
    refetchInterval: (query) => {
      const data = query.state.data as Call | undefined;
      return data?.transcribe_status === 'running' ? 2500 : false;
    },
  });
}