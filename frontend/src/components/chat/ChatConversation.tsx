import { useEffect, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { ChatThread } from '@/components/chat/ChatThread';
import { useChatMeta } from '@/api/hooks/useChats';
import { useMessageTemplates } from '@/api/hooks/useMessageTemplates';
import { channelMeta } from '@/lib/chat-channels';

type Props = {
  /** Кандидат-владелец диалога (единый источник: GET/POST /candidates/{id}/messages). */
  candidateId: string;
  /** Косметика композера/ленты: попап сайдбара или вкладка «Чат» карточки. */
  variant: 'popup' | 'tab';
  /** Показывать выпадашку «Шаблон» (только вкладка). В попапе false → запрос шаблонов не идёт. */
  showTemplates?: boolean;
};

/**
 * ОБЩИЙ контейнер переписки: лента + композер С СЕЛЕКТОРОМ КАНАЛА ОТВЕТА. Один и тот
 * же в попапе сайдбара (variant='popup') и во вкладке «Чат» карточки (variant='tab',
 * showTemplates). Единый источник данных — ChatThread (useMessagesInfinite +
 * useSendMessage, queryKey-префикс ['candidates',id,'messages']): отправка из попапа
 * сразу видна во вкладке и наоборот.
 *
 * Селектор «Канал ответа» виден ВСЕГДА при непустом available_channels — даже если
 * канал ОДИН, чтобы рекрутёр ВИДЕЛ, куда уйдёт ответ («Канал ответа: hh»), и не слал
 * вслепую. Точка+название канала в мете КАЖДОГО сообщения (showChannel) — в обоих
 * вариантах, чтобы было видно, откуда пришло сообщение. Каналы — ТОЛЬКО реально
 * доступные из useChatMeta().available_channels (подмножество telegram/hh); нет
 * канала → композер честно выключен (§0, не шлём «в никуда»/на email из истории).
 */
export function ChatConversation({ candidateId, variant, showTemplates = false }: Props) {
  const { data: meta } = useChatMeta(candidateId);
  const { data: templates } = useMessageTemplates(showTemplates);

  const available = meta?.available_channels ?? [];
  const availKey = available.join(',');

  const [activeChannel, setActiveChannel] = useState<string | null>(null);
  const [chOpen, setChOpen] = useState(false);
  const [tplOpen, setTplOpen] = useState(false);

  // Дефолт = meta.default_channel (бек: канал ПОСЛЕДНЕГО входящего → preferred →
  // первый) — так в селекторе сразу верный канал (hh для hh-кандидата). Держим
  // выбор валидным при смене набора каналов (кандидат без отклика hh → hh пропадает
  // из available_channels).
  useEffect(() => {
    if (!meta) return;
    setActiveChannel((cur) => {
      if (cur && available.includes(cur)) return cur;
      if (meta.default_channel && available.includes(meta.default_channel)) return meta.default_channel;
      return available[0] ?? null;
    });
    // available — производное от meta; ключ availKey покрывает смену набора.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta, availKey]);

  const metaLoading = !meta;
  const noChannel = !metaLoading && available.length === 0;
  const sendChannel = activeChannel ?? meta?.default_channel ?? available[0] ?? '';
  const activeMeta = channelMeta(sendChannel);

  // Честная причина выключенного композера (§0): загрузка каналов vs. канала нет вовсе.
  const disabledReason = metaLoading
    ? 'Загрузка каналов…'
    : noChannel
      ? 'Нет подключённого канала — написать кандидату пока некуда. Подключите Telegram в настройках или дождитесь отклика с hh.'
      : null;

  return (
    <ChatThread
      candidateId={candidateId}
      variant={variant}
      sendChannel={sendChannel}
      showChannel
      disabledReason={disabledReason}
      composerHint={
        disabledReason ? null : (
          <>
            Ctrl+Enter — отправить · Enter — новая строка · ответ уйдёт в <b>{activeMeta.label}</b>
          </>
        )
      }
      renderComposerExtra={
        disabledReason
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
                {showTemplates && templates && templates.length > 0 && (
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
  );
}
