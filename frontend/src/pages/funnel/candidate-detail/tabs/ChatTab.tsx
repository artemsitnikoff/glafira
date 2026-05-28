import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useMessages } from '@/api/hooks/useMessages';
import { useSendMessage } from '@/api/mutations/candidateDetail';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

export function ChatTab({ candidateId, candidate, fromPool = false }: Props) {
  // Use candidateId from props or extract from candidate
  const actualCandidateId = candidateId || candidate?.id;
  const [messageText, setMessageText] = useState('');
  const { data: messages, isLoading } = useMessages(actualCandidateId);
  const sendMutation = useSendMessage(actualCandidateId);

  // Группировка сообщений по vacancy_id для fromPool режима
  const messageGroups = fromPool && messages ? (() => {
    const groupMap = new Map<string | null, typeof messages>();
    for (const msg of messages) {
      const key = msg.vacancy_id ?? null;
      if (!groupMap.has(key)) groupMap.set(key, []);
      groupMap.get(key)!.push(msg);
    }

    // Вынести null-группу в конец, остальные — в порядке Map (insertion)
    const orderedGroups: Array<[string | null, typeof messages]> = [];
    for (const [key, group] of groupMap.entries()) {
      if (key !== null) orderedGroups.push([key, group]);
    }
    if (groupMap.has(null)) orderedGroups.push([null, groupMap.get(null)!]);

    return orderedGroups;
  })() : null;

  // Функция для определения заголовка группы
  function getGroupTitle(group: NonNullable<typeof messages>, vacancyId: string | null): string {
    if (vacancyId === null) return 'Общие сообщения';
    const ctx = group.find(m => m.application_context && m.application_context.trim());
    return ctx?.application_context || 'Вакансия';
  }

  function handleSendMessage() {
    if (!messageText.trim()) return;

    sendMutation.mutate(
      {
        body: messageText.trim(),
        sender_type: 'user',
      },
      {
        onSuccess: () => {
          setMessageText('');
        },
      }
    );
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }

  if (isLoading) {
    return (
      <div className="tab-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загружаются сообщения...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="tab-content">
      <h2 style={{ margin: '0 0 var(--space-4) 0', fontSize: '18px', fontWeight: '600' }}>
        Чат с кандидатом
      </h2>

      <div className="chat-container">
        <div className="chat-messages">
          {messages && messages.length > 0 ? (
            fromPool && messageGroups ? (
              messageGroups.map(([vacancyId, group], groupIndex) => (
                <div key={vacancyId || 'null-group'}>
                  {/* Разделитель группы */}
                  <div style={{
                    padding: 'var(--space-3) 0',
                    margin: groupIndex > 0 ? 'var(--space-4) 0 var(--space-3) 0' : '0 0 var(--space-3) 0',
                    borderTop: groupIndex > 0 ? '1px solid var(--border-1)' : 'none',
                    textAlign: 'center'
                  }}>
                    <span style={{
                      fontSize: '12px',
                      color: 'var(--fg-3)',
                      fontWeight: 500,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em'
                    }}>
                      {getGroupTitle(group, vacancyId)}
                    </span>
                  </div>

                  {/* Сообщения группы */}
                  {group.map((message) => (
                    <div
                      key={message.id}
                      className={`chat-message chat-message--${message.sender_type === 'user' ? 'user' : 'assistant'}`}
                    >
                      <div style={{ marginBottom: 'var(--space-1)' }}>
                        <strong>
                          {message.sender_type === 'user' ? 'Рекрутер' : 'Кандидат'}
                        </strong>
                        <span style={{ color: 'var(--fg-3)', fontSize: '12px', marginLeft: 'var(--space-2)' }}>
                          {new Date(message.sent_at).toLocaleString('ru')}
                        </span>
                      </div>
                      <div>{message.body}</div>
                    </div>
                  ))}
                </div>
              ))
            ) : (
              // Стандартный режим - плоский список
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`chat-message chat-message--${message.sender_type === 'user' ? 'user' : 'assistant'}`}
                >
                  <div style={{ marginBottom: 'var(--space-1)' }}>
                    <strong>
                      {message.sender_type === 'user' ? 'Рекрутер' : 'Кандидат'}
                    </strong>
                    <span style={{ color: 'var(--fg-3)', fontSize: '12px', marginLeft: 'var(--space-2)' }}>
                      {new Date(message.sent_at).toLocaleString('ru')}
                    </span>
                  </div>
                  <div>{message.body}</div>
                </div>
              ))
            )
          ) : (
            <div className="empty-state">
              <Icon name="message-circle" size={32} className="empty-state__icon" />
              <p className="empty-state__text">Сообщений пока нет</p>
            </div>
          )}
        </div>

        <div className="chat-input-container">
          <textarea
            className="chat-input"
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Напишите сообщение... (Enter для отправки, Shift+Enter для новой строки)"
            rows={2}
          />
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleSendMessage}
            disabled={!messageText.trim() || sendMutation.isPending}
          >
            <Icon name={sendMutation.isPending ? "loader" : "send"} size={16} />
          </button>
        </div>
      </div>

      {sendMutation.isError && (
        <div style={{ marginTop: 'var(--space-2)', color: 'var(--stage-rejected)', fontSize: '14px' }}>
          Ошибка отправки: {sendMutation.error?.message}
        </div>
      )}
    </div>
  );
}