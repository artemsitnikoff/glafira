import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useHomeDialogs } from '@/api/hooks/useHomeDialogs';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { formatRelativeTime } from '@/lib/time';
import { Icon } from '@/components/ui/Icon';

// Метаданные каналов как в эталоне + дополнительные
const channelMeta = {
  telegram: { abbr: 'TG', color: '#2A8AF0', name: 'Telegram' },
  whatsapp: { abbr: 'WA', color: '#1FA855', name: 'WhatsApp' },
  hh: { abbr: 'HH', color: '#DC4646', name: 'hh.ru' },
  avito: { abbr: 'AV', color: '#0AB1C7', name: 'Авито' },
  max: { abbr: 'MAX', color: '#0077FF', name: 'MAX' },
  sms: { abbr: 'СМС', color: '#5B6573', name: 'СМС' },
  email: { abbr: 'Mail', color: '#9AA3AE', name: 'Почта' },
};

export function MessagesBlock() {
  const { data, isLoading } = useHomeDialogs();
  const navigate = useNavigate();
  const [mode, setMode] = useState<'all' | 'waiting'>('all');

  if (isLoading) return <Skeleton height={380} />;

  const dialogs = data ?? [];
  const waitingCount = dialogs.filter(d => d.waiting).length;
  const total = dialogs.length;
  const shown = mode === 'waiting' ? dialogs.filter(d => d.waiting) : dialogs;

  return (
    <div className="card-block msg-card">
      <div className="card-block-head">
        <div className="title">
          Последние сообщения
          <span className="ad-sub-title">· все каналы в одном чате</span>
        </div>
      </div>

      <div className="msg-seg">
        <button
          className={`msg-seg-btn${mode === 'waiting' ? ' active' : ''}`}
          onClick={() => setMode('waiting')}
        >
          Ждут ответа <span className="msg-seg-num t-mono">{waitingCount}</span>
        </button>
        <button
          className={`msg-seg-btn${mode === 'all' ? ' active' : ''}`}
          onClick={() => setMode('all')}
        >
          Все <span className="msg-seg-num t-mono">{total}</span>
        </button>
      </div>

      {shown.length === 0 ? (
        <div className="msg-empty">
          <EmptyState title={mode === 'waiting' ? 'Все диалоги отвечены' : 'Нет активных диалогов'} />
        </div>
      ) : (
        <div className="msg-list">
          {shown.map((dialog) => {
            const ch = channelMeta[dialog.channel as keyof typeof channelMeta] || {
              abbr: dialog.channel.slice(0, 3).toUpperCase(),
              color: '#9AA3AE',
              name: dialog.channel
            };
            const initials = dialog.candidate_name.split(' ').filter(Boolean).map(s => s[0]).join('').slice(0, 2);

            let previewText = dialog.preview;
            if (dialog.last_sender_type === 'recruiter') {
              previewText = `Вы: ${dialog.preview}`;
            } else if (dialog.last_sender_type === 'ai') {
              previewText = `Глафира: ${dialog.preview}`;
            }

            return (
              <div key={`${dialog.candidate_id}-${dialog.channel}`} className={`msg-row${dialog.waiting ? ' unread' : ''}`}>
                <div className="msg-ava-wrap">
                  <div className="msg-ava">{initials}</div>
                  <span className="msg-ch-badge t-mono" style={{ background: ch.color }}>{ch.abbr}</span>
                </div>
                <div className="msg-body">
                  <div className="msg-top">
                    <span className="msg-name">{dialog.candidate_name}</span>
                    {dialog.vacancy_name && (
                      <span className="msg-vac">{dialog.vacancy_name}</span>
                    )}
                    <span className="msg-ch-name" style={{ color: ch.color }}>
                      <span className="msg-ch-dot" style={{ background: ch.color }}/>
                      {ch.name}
                    </span>
                  </div>
                  <div className="msg-text">{previewText}</div>
                  <div className="msg-actions">
                    <button
                      className="msg-goto"
                      onClick={() => navigate(`/candidates/${dialog.candidate_id}?tab=chat`)}
                    >
                      Перейти к кандидату <Icon name="chevR" size={13}/>
                    </button>
                  </div>
                </div>
                <div className="msg-meta">
                  {dialog.waiting && <span className="msg-unread-dot"/>}
                  <span className="msg-time t-mono">{formatRelativeTime(dialog.sent_at)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}