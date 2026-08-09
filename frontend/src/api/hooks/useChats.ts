import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// ⚠️ openapi.json протух (§3 CLAUDE.md) — эндпоинты модуля «Чаты» ещё не в
// сгенерённых типах. Описываем контракт локально + as-cast по месту. Контракт
// сверен с бэкендом (Фазы 1-2): GET /chats/dialogs, /chats/unread-total,
// /chats/candidate/{id}/meta, POST /candidates/{id}/messages/read | .../hh/sync.

export type ChatDialog = {
  candidate_id: string;
  name: string;
  avatar_url: string | null;
  vacancy_id: string | null;
  vacancy_name: string | null;
  channel: string;
  preview: string;
  sent_at: string;
  last_sender_type: 'candidate' | 'recruiter' | 'ai' | string;
  unread_count: number;
  last_inbound_at: string | null;
};

export type ChatMeta = {
  candidate_id: string;
  hh_available: boolean;
  telegram_available: boolean;
  last_inbound_at: string | null;
  last_inbound_channel: string | null;
  default_channel: string | null;
  available_channels: string[];
};

// Не поллим, когда вкладка скрыта: возвращаем false → интервал приостановлен;
// при возврате фокуса refetchOnWindowFocus дёргает refetch, интервал возобновляется.
const interval = (ms: number) => () => (document.hidden ? false : ms);

/** Список диалогов для попапа. Поиск по имени и вавкансии → ?q. Поллинг 15с. */
export function useDialogs(q: string, enabled = true) {
  const query = q.trim();
  return useQuery({
    queryKey: ['chats', 'dialogs', query],
    queryFn: async () =>
      (await api.get<ChatDialog[]>('/chats/dialogs', query ? { params: { q: query } } : undefined)).data,
    enabled,
    refetchInterval: interval(15_000),
  });
}

/** Сумма непрочитанных для бейджа в сайдбаре. Поллинг 12с. */
export function useUnreadTotal(enabled = true) {
  return useQuery({
    queryKey: ['chats', 'unread'],
    queryFn: async () => (await api.get<{ total: number }>('/chats/unread-total')).data.total,
    enabled,
    refetchInterval: interval(12_000),
  });
}

/** Метаданные диалога кандидата: доступные каналы + канал отправки по умолчанию. */
export function useChatMeta(candidateId: string | null) {
  return useQuery({
    queryKey: ['chats', 'meta', candidateId],
    queryFn: async () =>
      (await api.get<ChatMeta>(`/chats/candidate/${candidateId}/meta`)).data,
    enabled: !!candidateId,
    staleTime: 30_000,
  });
}

/**
 * Отметить диалог прочитанным. Оптимистично гасит бейдж диалога, затем
 * инвалидирует список диалогов и сумму непрочитанных (сервер — источник правды).
 */
export function useMarkRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (candidateId: string) =>
      (await api.post<{ ok: boolean; unread: number }>(`/candidates/${candidateId}/messages/read`)).data,
    onMutate: async (candidateId) => {
      await qc.cancelQueries({ queryKey: ['chats', 'dialogs'] });
      qc.setQueriesData<ChatDialog[]>({ queryKey: ['chats', 'dialogs'] }, (old) =>
        old ? old.map((d) => (d.candidate_id === candidateId ? { ...d, unread_count: 0 } : d)) : old
      );
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['chats', 'dialogs'] });
      qc.invalidateQueries({ queryKey: ['chats', 'unread'] });
    },
  });
}

/**
 * Дёрнуть входящие hh-сообщения по запросу (зеркало telegram/sync).
 * Используется при открытии диалога hh-кандидата.
 */
export function useSyncHhInbound(candidateId: string | null) {
  return useMutation({
    mutationFn: async (): Promise<{ imported: number }> =>
      (await api.post<{ imported: number }>(`/candidates/${candidateId}/messages/hh/sync`)).data,
  });
}
