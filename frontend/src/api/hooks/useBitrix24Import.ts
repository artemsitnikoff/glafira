import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// Локальные типы для Битрикс24 импорта (openapi не регенерён)
export interface B24Department {
  id: string;
  name: string;
  parent?: string | null;
}

export interface B24ImportCandidate {
  b24_id: string;
  name: string;
  last_name: string;
  position?: string | null;
  email?: string | null;
  department_ids: string[];
  department_name: string;
  active: boolean;
}

export interface B24ImportRequest {
  b24_user_ids: string[];
  role: string;
  delivery: 'email';
}

export interface B24ImportResult {
  created: Array<{ email: string; full_name: string }>;
  emailed: string[];
  shown: Array<{ email: string; temp_password: string; full_name: string }>;
  skipped: Array<{ name: string; reason: string }>;
}

export function useB24Departments() {
  return useQuery({
    queryKey: ['integrations', 'bitrix24', 'departments'],
    queryFn: async (): Promise<B24Department[]> => {
      const response = await api.get('/integrations/bitrix24/departments');
      return response.data as B24Department[];
    },
  });
}

export function useB24ImportCandidates() {
  return useQuery({
    queryKey: ['integrations', 'bitrix24', 'import-candidates'],
    queryFn: async (): Promise<B24ImportCandidate[]> => {
      const response = await api.get('/integrations/bitrix24/import-candidates');
      return response.data as B24ImportCandidate[];
    },
  });
}

export function useB24ImportUsers() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: B24ImportRequest): Promise<B24ImportResult> => {
      const response = await api.post('/integrations/bitrix24/import', data);
      return response.data as B24ImportResult;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}