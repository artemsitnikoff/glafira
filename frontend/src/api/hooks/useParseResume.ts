import { useMutation } from '@tanstack/react-query';
import { api } from '@/api/client';

interface ParseResumeFields {
  first_name?: string;
  last_name?: string;
  middle_name?: string;
  phone?: string;
  email?: string;
  city?: string;
  salary_expectation?: number | null;
  last_position?: string;
  last_company?: string;
  last_period?: string;
  about?: string;
  experience?: Array<{
    position: string;
    company: string;
    period: string;
    description?: string;
  }>;
  skills?: string[];
  education?: Array<{
    institution: string;
    specialty: string;
    years: string;
  }>;
  languages?: string[];
}

interface ParseResumeResponse {
  parsed: boolean;
  reason: string | null;
  fields: ParseResumeFields | null;
}

export function useParseResume() {
  return useMutation({
    mutationFn: async (file: File): Promise<ParseResumeResponse> => {
      const formData = new FormData();
      formData.append('file', file);

      const response = await api.post<ParseResumeResponse>('/candidates/parse-resume', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      return response.data;
    },
  });
}