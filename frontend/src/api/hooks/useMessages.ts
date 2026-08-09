import { useInfiniteQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { MessageOut } from '@/api/aliases';

// ── Пагинация ленты (общий ChatThread: попап + вкладка «Чат») ────────────────

/** Размер страницы ленты. Бек: page_size ge=1 le=100 (core/pagination.py). */
export const MSG_PAGE_SIZE = 30;

export type MessagePage = {
  items: MessageOut[];
  total: number;
  page: number;
  pages: number;
  page_size: number;
};

/**
 * Постраничная лента сообщений кандидата для «чат»-скролла: новые снизу,
 * подгрузка СТАРЫХ при скролле ВВЕРХ. Бек отдаёт сообщения в ХРОНОЛОГИЧЕСКОМ
 * порядке (sent_at ASC, offset-пагинация) и не умеет курсоры/DESC — поэтому:
 *   • «самая новая» страница = последняя (номер = pages). initialPageParam='newest'
 *     резолвится в её номер лёгким пробингом (page=1&page_size=1 → total).
 *   • getNextPageParam возвращает БОЛЕЕ СТАРУЮ страницу (номер − 1) — её тянет
 *     скролл вверх. Старые страницы стабильны по offset (новые сообщения
 *     дописываются в новый конец), поэтому догрузка старого безопасна.
 *
 * queryKey ['candidates',id,'messages','list'] — сегмент 'list' ПОСЛЕ 'messages',
 * чтобы префиксная инвалидация ['candidates',id,'messages'] (useSendMessage,
 * telegram/hh-sync) продолжала попадать в этот кэш → отправка из попапа сразу
 * видна во вкладке и наоборот (единый источник).
 *
 * ⚠️ Известный редкий край offset-пагинации (без правок бека не устраним): если
 * ПОКА подгружены старые страницы, поток новых сообщений ПЕРЕСЕЧЁТ границу
 * page_size, «newest» перескочит на новый номер и между ним и старыми страницами
 * возможен разрыв до переоткрытия диалога. При page_size=30 и медленном потоке —
 * практически не встречается; это честное ограничение, а не фейк.
 */
export function useMessagesInfinite(candidateId: string | null) {
  return useInfiniteQuery({
    queryKey: ['candidates', candidateId, 'messages', 'list'],
    queryFn: async ({ pageParam }): Promise<MessagePage> => {
      let page: number;
      if (pageParam === 'newest') {
        const probe = (
          await api.get<{ total: number }>(`/candidates/${candidateId}/messages`, {
            params: { page: 1, page_size: 1 },
          })
        ).data;
        page = Math.max(1, Math.ceil((probe.total || 0) / MSG_PAGE_SIZE));
      } else {
        page = pageParam as number;
      }
      return (
        await api.get<MessagePage>(`/candidates/${candidateId}/messages`, {
          params: { page, page_size: MSG_PAGE_SIZE },
        })
      ).data;
    },
    initialPageParam: 'newest' as 'newest' | number,
    // «next» в нашей модели = более СТАРАЯ страница (скролл вверх): номер самой
    // старой уже загруженной страницы минус 1. Дошли до 1 — старее нет.
    getNextPageParam: (_last, allPages) => {
      const minPage = Math.min(...allPages.map((p) => p.page));
      return minPage > 1 ? minPage - 1 : undefined;
    },
    enabled: !!candidateId,
    // Не поллить при скрытой вкладке (как в useChats) — единообразно.
    refetchInterval: () => (document.hidden ? false : 12000),
  });
}

type TelegramSyncResult = { imported: number; connected: boolean };

export function useSyncTelegramInbound(candidateId: string | null) {
  return useMutation({
    mutationFn: async (): Promise<TelegramSyncResult> => {
      const res = await api.post<TelegramSyncResult>(
        `/candidates/${candidateId}/messages/telegram/sync`
      );
      return res.data;
    },
  });
}