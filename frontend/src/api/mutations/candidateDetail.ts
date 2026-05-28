import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type CandidateUpdate = Partial<{
  preferred_channel: string;
}>;
type MessageCreate = {
  body: string;
  sender_type: string;
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
      return (await api.post(`/candidates/${candidateId}/consent`, data)).data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'verification'] });
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
    mutationFn: async (data: ScoreRequest) => {
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
      return (await api.post(`/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        params: { candidate_id: candidateId },
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