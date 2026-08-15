import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// ⚠️ openapi.json протух (§3 CLAUDE.md) — новое поле CommentOut.source ещё не в
// сгенерённых типах (CommentOut из aliases его НЕ содержит). Описываем строку
// комментария локально + as-cast по месту. Контракт сверен с бэкендом (Фаза 1):
// GET /candidates/{id}/comments → { id, author_name, author_role, body, mentions,
// created_at, source }.
export type CommentRow = {
  id: string;
  author_name: string | null;
  author_role: string | null;
  body: string;
  mentions?: unknown;
  created_at: string;
  // 'hh' — заметка с hh; 'talantix' — заметка рекрутёра из ATS Talantix;
  // 'manual' — наш комментарий. Старый кэш без поля → трактуем как 'manual'.
  source?: 'manual' | 'hh' | 'talantix';
};

// Не поллим, когда вкладка скрыта: false → интервал приостановлен; возврат фокуса
// (refetchOnWindowFocus) дёрнет refetch и возобновит интервал. Идиом из useChats.
const interval = (ms: number) => () => (document.hidden ? false : ms);

export function useComments(candidateId: string | null) {
  return useQuery({
    queryKey: ['candidates', candidateId, 'comments'],
    queryFn: async () =>
      (await api.get<CommentRow[]>(`/candidates/${candidateId}/comments`)).data,
    enabled: !!candidateId,
    // Поллинг ~20с (гейт document.hidden) — импортированные с hh заметки
    // подтягиваются без перезагрузки, зеркалит поведение чата.
    refetchInterval: interval(20_000),
  });
}

/**
 * Дёрнуть заметки кандидата с hh по запросу (зеркало messages/hh/sync).
 * graceful на беке: нет hh-резюме/токена → { imported: 0 }. onSuccess при
 * imported>0 инвалидирует список комментариев → импортированные заметки подтянутся.
 */
export function useSyncHhComments(candidateId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<{ imported: number }> =>
      (await api.post<{ imported: number }>(`/candidates/${candidateId}/comments/hh/sync`)).data,
    onSuccess: (result) => {
      if (result.imported > 0) {
        qc.invalidateQueries({ queryKey: ['candidates', candidateId, 'comments'] });
      }
    },
  });
}
