import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ChatConversation } from '@/components/chat/ChatConversation';
import { useSyncTelegramInbound } from '@/api/hooks/useMessages';

type Props = {
  candidateId?: string;
  candidate?: { id?: string; full_name?: string; source?: string } | null;
  fromPool?: boolean;
};

/**
 * Вкладка «Чат» карточки кандидата. Переписка + композер с селектором канала ответа
 * и шаблонами — из ОБЩЕГО ChatConversation (тот же компонент и тот же источник
 * данных, что попап сайдбара: useMessagesInfinite + useSendMessage, queryKey-префикс
 * ['candidates',id,'messages']) → отправка из вкладки сразу видна в попапе и наоборот.
 *
 * Своё у вкладки — только фоновый синк входящих Telegram каждые 90с (hh — cron-only).
 */
export function ChatTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const queryClient = useQueryClient();

  // Синхронизация входящих Telegram каждые 90с (зеркалит попап). hh — cron-only.
  const syncMutation = useSyncTelegramInbound(actualCandidateId ?? null);
  const syncMutateRef = useRef(syncMutation.mutate);
  syncMutateRef.current = syncMutation.mutate;
  const syncInFlight = useRef(false);
  useEffect(() => {
    if (!actualCandidateId) return;
    const runSync = () => {
      if (syncInFlight.current) return;
      syncInFlight.current = true;
      syncMutateRef.current(undefined, {
        onSuccess: (result) => {
          if (result.imported > 0) {
            queryClient.invalidateQueries({ queryKey: ['candidates', actualCandidateId, 'messages'] });
          }
        },
        onSettled: () => {
          syncInFlight.current = false;
        },
      });
    };
    runSync();
    const timer = setInterval(runSync, 90000);
    return () => clearInterval(timer);
  }, [actualCandidateId, queryClient]);

  if (!actualCandidateId) return <div className="chat-tab" />;

  return (
    <div className="chat-tab">
      <ChatConversation candidateId={actualCandidateId} variant="tab" showTemplates />
    </div>
  );
}
