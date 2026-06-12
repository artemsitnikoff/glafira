import { api } from '@/api/client';

// Local types for duplicate check (openapi отстаёт)
type DuplicateMatch = {
  id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  created_at: string;
  match_level: 'exact' | 'possible';
  matched_by: 'phone' | 'email';
  vacancies: { vacancy_name: string; stage_label: string }[];
};

type DuplicateCheckResult = {
  found: boolean;
  match_count: number;
  matches: DuplicateMatch[];
};

type CheckDuplicateParams = {
  phone?: string;
  email?: string;
  first_name?: string;
  last_name?: string;
  middle_name?: string;
};

export async function checkDuplicate(params: CheckDuplicateParams): Promise<DuplicateCheckResult> {
  const cleanParams = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value?.trim())
  );

  if (Object.keys(cleanParams).length === 0) {
    return { found: false, match_count: 0, matches: [] };
  }

  const response = await api.get('/candidates/check-duplicate', { params: cleanParams });
  return response.data as DuplicateCheckResult;
}

export type { DuplicateCheckResult, DuplicateMatch };