import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

// Полный набор редактируемых полей (форма правки шлёт ФИО/контакты/город/ЗП/источник/…).
// source/messengers ещё нет в сгенерённом CandidateUpdate (openapi отстаёт) — добавляем локально.
type CandidateUpdate = Partial<components['schemas']['CandidateUpdate']> & {
  source?: string | null;
  messengers?: { type: string; url: string }[];
};
type MessageCreate = {
  body: string;
  sender_type: string;
  channel?: string;
};
type CommentCreate = {
  body: string;
};
type ConsentRequest = {
  channel: string;
};
type ScoreRequest = components['schemas']['ScoreRequest'];

export function useUpdateCandidate(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CandidateUpdate) => {
      return (await api.patch(`/candidates/${candidateId}`, data)).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId] });
    },
  });
}

export function useRequestConsent(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: ConsentRequest) => {
      return (await api.post(`/candidates/${candidateId}/consent/request`, data)).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'verification'] });
    },
  });
}

/**
 * Рекрутёр под свою ответственность отмечает согласие подписанным (бумага и т.п.)
 * и СРАЗУ запускает верификацию. Если верификация не пройдёт — согласие всё равно
 * подписано, верификацию можно запустить кнопкой позже.
 */
export function useConfirmConsentSigned(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      await api.post(`/candidates/${candidateId}/consent/confirm-signed`);
      try {
        return (await api.post(`/candidates/${candidateId}/verify`)).data;
      } catch {
        // Согласие подписано; верификация может не пройти (DaData/AI) — не валим действие.
        return null;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'verification'] });
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}

export function useRunVerification(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      return (await api.post(`/candidates/${candidateId}/verify`)).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'verification'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}

export function useEvaluate() {
  const queryClient = useQueryClient();

  return useMutation({
    // force — переоценить заново (openapi ещё без него → локальное расширение типа)
    mutationFn: async (data: ScoreRequest & { force?: boolean }) => {
      return (await api.post('/glafira/score', data)).data;
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['candidates', variables.candidate_id, 'evaluation'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}

export function useSendMessage(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: MessageCreate) => {
      return (await api.post(`/candidates/${candidateId}/messages`, data)).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'messages'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}

export function useUploadDocument(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (params: [File, string?]) => {
      const [file, kind] = params;
      const formData = new FormData();
      formData.append('file', file);
      if (kind) {
        formData.append('kind', kind);
      }
      return (await api.post(`/candidates/${candidateId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'documents'] });
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId] }); // Resume upload updates candidate
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (documentId: string) => {
      return (await api.delete(`/documents/${documentId}`)).data;
    },
    onSuccess: () => {
      // Invalidate all candidates documents since we don't know which candidate it belongs to
      queryClient.invalidateQueries({ queryKey: ['candidates'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}

export function useDownloadDocument() {
  return useMutation({
    mutationFn: async (documentId: string) => {
      const response = await api.get(`/documents/${documentId}/download`, {
        responseType: 'blob',
      });
      return { blob: response.data, filename: response.headers['content-disposition']?.split('filename=')[1] };
    },
  });
}

export function useAddComment(candidateId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CommentCreate) => {
      return (await api.post(`/candidates/${candidateId}/comments`, data)).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'comments'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}