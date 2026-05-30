import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { useMessages } from '@/api/hooks/useMessages';
import { useSendMessage } from '@/api/mutations/candidateDetail';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

// Channel options — color logos & labels (1:1 эталон)
// id = значение канала в БД (CHECK: telegram|hh|whatsapp|max|sms|email)
const CHANNELS = [
  { id: 'telegram', label: 'Telegram', short: 'TG', color: '#229ED9' },
  { id: 'hh', label: 'hh.ru', short: 'hh', color: '#D6001C' },
  { id: 'max', label: 'Max', short: 'MX', color: '#0077FF' },
  { id: 'whatsapp', label: 'WhatsApp', short: 'WA', color: '#25D366' },
  { id: 'sms', label: 'SMS', short: 'SMS', color: '#7A7F87' },
  { id: 'email', label: 'E-mail', short: '@', color: '#5B6573' },
];

export function ChatTab({ candidateId, candidate, fromPool = false }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const [activeChannel, setActiveChannel] = useState('telegram');
  const [draft, setDraft] = useState('');
  const [open, setOpen] = useState(false);
  const { data: messages, isLoading } = useMessages(actualCandidateId);
  const sendMutation = useSendMessage(actualCandidateId);

  const channelMeta = (id: string) => CHANNELS.find(x => x.id === id) || CHANNELS[0];
  const active = channelMeta(activeChannel);

  // Группировка сообщений по vacancy_id для fromPool режима (упрощённо - можно убрать)
  const messageGroups = fromPool && messages ? (() => {
    const groupMap = new Map<string | null, typeof messages>();
    for (const msg of messages) {
      const key = msg.vacancy_id ?? null;
      if (!groupMap.has(key)) groupMap.set(key, []);
      groupMap.get(key)!.push(msg);
    }
    const orderedGroups: Array<[string | null, typeof messages]> = [];
    for (const [key, group] of groupMap.entries()) {
      if (key !== null) orderedGroups.push([key, group]);
    }
    if (groupMap.has(null)) orderedGroups.push([null, groupMap.get(null)!]);
    return orderedGroups;
  })() : null;

  const send = () => {
    if (!draft.trim()) return;

    sendMutation.mutate(
      {
        body: draft.trim(),
        sender_type: 'user',
        channel: activeChannel,
      } as any, // Приведение типа, т.к. channel может ещё не быть в типе
      {
        onSuccess: () => {
          setDraft('');
        },
      }
    );
  };

  const today = new Date().toLocaleDateString('ru', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  });

  if (isLoading) {
    return (
      <div className="chat-tab">
        <div className="chat-stream" style={{ alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--fg-3)' }}>
            <Icon name="loader" size={16} />
            <span style={{ fontSize: '13px' }}>Загружаются сообщения...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-tab">
      <div className="chat-stream">
        <div className="chat-day-divider"><span>{today}</span></div>
        {messages && messages.length > 0 ? (
          fromPool && messageGroups ? (
            // Группированный режим (можно упростить до плоского)
            messageGroups.map(([vacancyId, group]) => (
              <div key={vacancyId || 'null-group'}>
                {/* Можно убрать разделитель групп для упрощения */}
                {group.map(m => {
                  const ch = channelMeta(m.channel || 'tg');
                  const isMe = m.sender_type === 'user';
                  const who = isMe ? 'Вы' : candidate?.full_name || 'Кандидат';
                  return (
                    <div key={m.id} className={`chat-row ${isMe ? 'chat-row-me' : 'chat-row-them'}`}>
                      {!isMe && <Avatar name={who} size="sm" />}
                      <div className="chat-bubble-wrap">
                        <div className="chat-meta">
                          <span className="chat-who">{who}</span>
                          <span className={`chat-ch chat-ch-${m.channel || 'tg'}`} style={{'--ch-color': ch.color} as any}>
                            <span className="chat-ch-dot" style={{background: ch.color}} />
                            {ch.label}
                          </span>
                        </div>
                        <div className={`chat-bubble ${isMe ? 'chat-bubble-me' : 'chat-bubble-them'}`}>
                          {m.body}
                        </div>
                        <div className="chat-time t-mono">
                          {new Date(m.sent_at).toLocaleTimeString('ru', {
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </div>
                      </div>
                      {isMe && <Avatar name="Вы" size="sm" />}
                    </div>
                  );
                })}
              </div>
            ))
          ) : (
            // Плоский список (основной режим)
            messages.map(m => {
              const ch = channelMeta(m.channel || 'tg');
              const isMe = m.sender_type === 'user';
              const who = isMe ? 'Вы' : candidate?.full_name || 'Кандидат';
              return (
                <div key={m.id} className={`chat-row ${isMe ? 'chat-row-me' : 'chat-row-them'}`}>
                  {!isMe && <Avatar name={who} size="sm" />}
                  <div className="chat-bubble-wrap">
                    <div className="chat-meta">
                      <span className="chat-who">{who}</span>
                      <span className={`chat-ch chat-ch-${m.channel || 'tg'}`} style={{'--ch-color': ch.color} as any}>
                        <span className="chat-ch-dot" style={{background: ch.color}} />
                        {ch.label}
                      </span>
                    </div>
                    <div className={`chat-bubble ${isMe ? 'chat-bubble-me' : 'chat-bubble-them'}`}>
                      {m.body}
                    </div>
                    <div className="chat-time t-mono">
                      {new Date(m.sent_at).toLocaleTimeString('ru', {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </div>
                  </div>
                  {isMe && <Avatar name="Вы" size="sm" />}
                </div>
              );
            })
          )
        ) : (
          <div style={{ textAlign: 'center', color: 'var(--fg-3)', fontSize: '13px', padding: '40px 20px' }}>
            Сообщений пока нет
          </div>
        )}
      </div>

      <div className="chat-compose">
        <div className="chat-compose-head">
          <span className="chat-compose-label">Канал ответа:</span>
          <div className={`chat-ch-select ${open ? 'open' : ''}`}>
            <button type="button" className="chat-ch-trigger" onClick={() => setOpen(!open)}>
              <span className="chat-ch-dot" style={{background: active.color}} />
              <span className="chat-ch-trigger-label">{active.label}</span>
              <Icon name="chevD" size={14} />
            </button>
            {open && (
              <div className="chat-ch-menu">
                {CHANNELS.map(ch => (
                  <button
                    type="button"
                    key={ch.id}
                    className={`chat-ch-opt ${ch.id === activeChannel ? 'active' : ''}`}
                    onClick={() => { setActiveChannel(ch.id); setOpen(false); }}
                  >
                    <span className="chat-ch-dot" style={{background: ch.color}} />
                    <span className="chat-ch-opt-label">{ch.label}</span>
                    {ch.id === activeChannel && <Icon name="check" size={14} />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        <div className="chat-compose-body">
          <div className="chat-input-wrap">
            <textarea
              className="chat-input"
              placeholder={`Сообщение в ${active.label}…`}
              rows={2}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) send(); }}
            />
            <button
              className="chat-send-btn"
              onClick={send}
              disabled={!draft.trim() || sendMutation.isPending}
              type="button"
              title="Отправить (Ctrl+Enter)"
              aria-label="Отправить"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2 11 13"/>
                <path d="M22 2 15 22l-4-9-9-4z"/>
              </svg>
            </button>
          </div>
        </div>
        <div className="chat-compose-hint">Ctrl + Enter — отправить · ответ уйдёт в <b>{active.label}</b></div>
      </div>

      {sendMutation.isError && (
        <div style={{ marginTop: '8px', color: 'var(--stage-rejected)', fontSize: '12px', padding: '0 16px' }}>
          Ошибка отправки: {sendMutation.error?.message}
        </div>
      )}
    </div>
  );
}