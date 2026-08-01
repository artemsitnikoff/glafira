import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';

// openapi протух (модуль «Тесты» ещё не в сгенерированном контракте) → локальные типы
// + as-cast (§3 CLAUDE.md). Формы 1:1 из backend/app/schemas/tests.py.

/** Строка справочника тестов (GET /tests). */
export type TestListItem = {
  id: string;
  key: string;
  name: string;
  kind: string;
  status: string; // 'active' | 'draft'
  item_count: number;
  assigned_count: number;
};

/** Блок теста (для blocked-тестов) — редактируется время на блок. */
export type TestBlockDetail = {
  id: string;
  key: string;
  title: string;
  order_index: number;
  duration_sec: number;
  item_count: number;
};

/** Бэнд порога категории (category_thresholds[]). */
export type TestCategoryBand = {
  min: number;
  max: number;
  key: string;
  label: string;
  marker?: string | null; // emoji-«светофор» 🟢/🟡/🟠/🔴
};

/** Полный конфиг теста (GET /tests/{id}). */
export type TestDetail = {
  id: string;
  key: string;
  name: string;
  kind: string;
  duration_sec: number | null;
  randomize_options: boolean;
  allow_back: boolean;
  category_thresholds: TestCategoryBand[] | null;
  auto_reject_below: number | null;
  status: string;
  item_count: number;
  assigned_count: number;
  blocks: TestBlockDetail[];
};

/** Строка ответа кандидата (рекрутёру верность видна). */
export type TestAnswerRow = {
  index: number;
  item_id: string;
  chosen_option_id: string | null;
  is_correct: boolean;
  time_ms: number | null;
};

/** Результат пройденного теста. */
export type TestResultOut = {
  raw_score: number;
  max_score: number;
  block_scores: Record<string, number>;
  category: string | null;
  category_label: string | null;
  percentile: number | null; // null при базе компании < 30 — НЕ показывать
  validity_flags: string[];
  validity_messages: string[];
  duration_sec: number | null;
  completed_at: string;
  answers: TestAnswerRow[];
};

/** Назначение теста по заявке (+результат для completed). */
export type TestAssignmentOut = {
  id: string;
  test_id: string;
  test_name: string;
  test_kind: string;
  status: string; // 'sent' | 'started' | 'completed' | 'cancelled' | 'expired'
  channel: string | null;
  url: string | null;
  expires_at: string | null;
  created_at: string;
  result: TestResultOut | null;
};

/** Справочник тестов компании (GET /tests) — admin/recruiter (manager → 403). */
export function useTests(enabled = true) {
  return useQuery({
    queryKey: ['tests'],
    queryFn: async () => (await api.get<TestListItem[]>('/tests')).data,
    enabled,
  });
}

/** Полный конфиг теста (GET /tests/{id}) — admin/recruiter. */
export function useTestDetail(testId: string | null) {
  return useQuery({
    queryKey: ['tests', testId],
    queryFn: async () => (await api.get<TestDetail>(`/tests/${testId}`)).data,
    enabled: !!testId,
  });
}

/** Назначения теста по заявке (GET /applications/{id}/tests). */
export function useApplicationTests(applicationId: string | null) {
  return useQuery({
    queryKey: ['applications', applicationId, 'tests'],
    queryFn: async () =>
      (await api.get<TestAssignmentOut[]>(`/applications/${applicationId}/tests`)).data,
    enabled: !!applicationId,
  });
}
