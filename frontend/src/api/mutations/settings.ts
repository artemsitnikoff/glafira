import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type ProfileUpdate = components['schemas']['ProfileUpdate'];
type PasswordChange = components['schemas']['PasswordChange'];
type GlafiraSettingsUpdate = components['schemas']['GlafiraSettingsUpdate'];
type RejectReasonCreate = components['schemas']['RejectReasonCreate'];
type RejectReasonUpdate = components['schemas']['RejectReasonUpdate'];
type EmailTemplateCreate = components['schemas']['EmailTemplateCreate'];
type EmailTemplateUpdate = components['schemas']['EmailTemplateUpdate'];
type SurveyTemplateCreate = components['schemas']['SurveyTemplateCreate'];
type SurveyTemplateUpdate = components['schemas']['SurveyTemplateUpdate'];
type IntegrationUpdate = components['schemas']['IntegrationUpdate'];
type UserCreate = components['schemas']['UserCreate'];
type UserUpdate = components['schemas']['UserUpdate'];
type MessageResult = components['schemas']['MessageResult'];

// Profile mutations
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: ProfileUpdate) => {
      const response = await api.patch('/settings/profile', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'profile'] });
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (data: PasswordChange) => {
      const response = await api.post('/settings/profile/password', data);
      return response.data as MessageResult;
    },
  });
}

// Glafira settings mutations
export function useUpdateGlafiraSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: GlafiraSettingsUpdate) => {
      const response = await api.patch('/settings/glafira', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'glafira'] });
    },
  });
}

// Reject reasons mutations
export function useCreateRejectReason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: RejectReasonCreate) => {
      const response = await api.post('/settings/reject-reasons', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'reject-reasons'] });
    },
  });
}

export function useUpdateRejectReason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: RejectReasonUpdate }) => {
      const response = await api.patch(`/settings/reject-reasons/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'reject-reasons'] });
    },
  });
}

export function useDeleteRejectReason() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const response = await api.delete(`/settings/reject-reasons/${id}`);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'reject-reasons'] });
    },
  });
}

// Email templates mutations
export function useCreateEmailTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: EmailTemplateCreate) => {
      const response = await api.post('/settings/email-templates', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'email-templates'] });
    },
  });
}

export function useUpdateEmailTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: EmailTemplateUpdate }) => {
      const response = await api.patch(`/settings/email-templates/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'email-templates'] });
    },
  });
}

// Survey templates mutations
export function useCreateSurveyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: SurveyTemplateCreate) => {
      const response = await api.post('/settings/survey-templates', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'survey-templates'] });
    },
  });
}

export function useUpdateSurveyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: SurveyTemplateUpdate }) => {
      const response = await api.patch(`/settings/survey-templates/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'survey-templates'] });
    },
  });
}

// Integration mutations
export function useUpdateIntegration() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ provider, data }: { provider: string; data: IntegrationUpdate }) => {
      const response = await api.patch(`/settings/integrations/${provider}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'integrations'] });
    },
  });
}

// Team mutations
export function useInviteUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: UserCreate) => {
      const response = await api.post('/users', data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: UserUpdate }) => {
      const response = await api.patch(`/users/${id}`, data);
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}