import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type EmailTemplateOut = components['schemas']['EmailTemplateOut'];

export function useEmailTemplates() {
  return useQuery({
    queryKey: ['settings', 'email-templates'],
    queryFn: async () => {
      const response = await api.get('/api/v1/settings/email-templates');
      return response.data as EmailTemplateOut[];
    },
    staleTime: 60_000,
  });
}