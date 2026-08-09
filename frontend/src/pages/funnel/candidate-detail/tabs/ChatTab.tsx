import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/ui/Icon';
import { ChatThread } from '@/components/chat/ChatThread';
import { useSyncTelegramInbound } from '@/api/hooks/useMessages';
import { useMessageTemplates } from '@/api/hooks/useMessageTemplates';
import { useChatMeta } from '@/api/hooks/useChats';
import { channelMeta } from '@/lib/chat-channels';

type Props = {
  candidateId?: string;
  candidate?: { id?: string; full_name?: string; source?: string } | null;
  fromPool?: boolean;
};

/**
 * Вкладка «Чат» карточки кандидата. Лента+композер — из ОБЩЕГО ChatThread (тот же
 * рендер и тот же источник данных, что попап сайдбара: useMessagesInfinite +
 * useSendMessage, queryKey-префикс ['candidates',id,'messages']) → отправка из
 * вкладки сразу видна в попапе и наоборот.
 *
 * Своё у вкладки (передаётся в ChatThread пропсами): селектор канала ответа НАД
 * композером (ТОЛЬКО реально доступные каналы из useChatMeta().available_channels —
 * подмножество telegram/hh; email/sms/max/whatsapp НЕ рисуем), быстрые шаблоны
 * (вставка в черновик через insertText), точка канала в мете каждого сообщения
 * (showChannel). Нет канала → composer честно выключен.
 */
export function ChatTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const queryClient = useQueryClient();

  const { data: meta } = useChatMeta(actualCandidateId ?? null);
  const { data: templates } = useMessageTemplates();

  const available = meta?.available_channels ?? [];
  const availKey = available.join(',');

  const [activeChannel, setActiveChannel] = useState<string | null>(null);
  const [chOpen, setChOpen] = useState(false);
  const [tplOpen, setTplOpen] = useState(false);

  // Дефолт = meta.default_channel; держим выбор валидным при смене набора каналов
  // (кандидат без отклика hh → hh пропадает из available_channels).
  useEffect(() => {
    if (!meta) return;
    setActiveChannel((cur) => {
      if (cur && available.includes(cur)) return cur;
      if (meta.default_channel && available.includes(meta.default_channel)) return meta.default_channel;
      return available[0] ?? null;
    });
    // available — производное от meta; ключ available.join(',') покрывает смену набора.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, availKey]);

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

  const noChannel = available.length === 0;
  const sendChannel = activeChannel ?? meta?.default_channel ?? 'telegram';
  const activeMeta = channelMeta(sendChannel);

  return (
    <div className="chat-tab">
      <ChatThread
        candidateId={actualCandidateId}
        sendChannel={sendChannel}
        variant="tab"
        showChannel
        disabledReason={
          noChannel
            ? 'Нет подключённого канала — написать кандидату пока некуда. Подключите Telegram в настройках или дождитесь отклика с hh.'
            : null
        }
        composerHint={
          noChannel ? null : (
            <>
              Enter — отправить · ответ уйдёт в <b>{activeMeta.label}</b>
            </>
          )
        }
        renderComposerExtra={
          noChannel
            ? undefined
            : ({ insertText }) => (
                <div className="chat-compose-head">
                  <span className="chat-compose-label">Канал ответа:</span>
                  <div className={`chat-ch-select ${chOpen ? 'open' : ''}`}>
                    <button type="button" className="chat-ch-trigger" onClick={() => setChOpen((o) => !o)}>
                      <span className="chat-ch-dot" style={{ background: activeMeta.color }} />
                      <span className="chat-ch-trigger-label">{activeMeta.label}</span>
                      <Icon name="chevD" size={14} />
                    </button>
                    {chOpen && (
                      <div className="chat-ch-menu">
                        {available.map((id) => {
                          const cm = channelMeta(id);
                          return (
                            <button
                              type="button"
                              key={id}
                              className={`chat-ch-opt ${id === sendChannel ? 'active' : ''}`}
                              onClick={() => {
                                setActiveChannel(id);
                                setChOpen(false);
                              }}
                            >
                              <span className="chat-ch-dot" style={{ background: cm.color }} />
                              <span className="chat-ch-opt-label">{cm.label}</span>
                              {id === sendChannel && <Icon name="check" size={14} />}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                  {templates && templates.length > 0 && (
                    <div className={`chat-ch-select ${tplOpen ? 'open' : ''}`}>
                      <button type="button" className="chat-ch-trigger" onClick={() => setTplOpen((o) => !o)}>
                        <Icon name="file-text" size={14} />
                        <span className="chat-ch-trigger-label">Шаблон</span>
                        <Icon name="chevD" size={14} />
                      </button>
                      {tplOpen && (
                        <div className="chat-ch-menu">
                          {templates.map((tpl) => (
                            <button
                              type="button"
                              key={tpl.id}
                              className="chat-ch-opt"
                              onClick={() => {
                                insertText(tpl.body);
                                setTplOpen(false);
                              }}
                            >
                              <span className="chat-ch-opt-label">{tpl.name}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
        }
      />
    </div>
  );
}
