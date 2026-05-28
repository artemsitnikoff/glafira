import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { components } from '@/api/types';

type SurveyTemplateOut = components['schemas']['SurveyTemplateOut'];

export function useSurveyTemplates() {
  return useQuery({
    queryKey: ['settings', 'survey-templates'],
    queryFn: async () => {
      const response = await api.get('/settings/survey-templates');
      return response.data as SurveyTemplateOut[];
    },
    staleTime: 60_000,
  });
}