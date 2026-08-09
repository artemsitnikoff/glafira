import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { Avatar } from '@/components/ui/Avatar';
import { Icon } from '@/components/ui/Icon';
import { useChatStore } from '@/store/chatStore';
import { useSyncTelegramInbound } from '@/api/hooks/useMessages';
import {
  useDialogs,
  useUnreadTotal,
  useChatMeta,
  useMarkRead,
  useSyncHhInbound,
  type ChatDialog,
} from '@/api/hooks/useChats';
import { ChatThread } from './ChatThread';
import '@/styles/chat.css';

// Время в строке диалога: сегодня → часы, вчера → «вчера», иначе краткая дата.
function dialogTime(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  const key = (x: Date) => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
  if (key(d) === key(now)) return d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
  if (key(d) === key(yest)) return 'вчера';
  return d.toLocaleDateString('ru', { day: '2-digit', month: '2-digit' });
}

// «Был на связи …» — честная замена фейкового presence-индикатора.
function lastSeenLabel(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  const now = new Date();
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  const key = (x: Date) => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
  const t = d.toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
  if (key(d) === key(now)) return `был на связи сегодня в ${t}`;
  if (key(d) === key(yest)) return `был на связи вчера в ${t}`;
  return `был на связи ${d.toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: '2-digit' })}`;
}

export function ChatPopup() {
  const open = useChatStore((s) => s.open);
  const close = useChatStore((s) => s.close);
  const select = useChatStore((s) => s.select);
  const selectedCandidateId = useChatStore((s) => s.selectedCandidateId);

  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [snapshot, setSnapshot] = useState<ChatDialog | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const { data: dialogs, isLoading } = useDialogs(debouncedQ, open);
  const { data: unreadTotal = 0 } = useUnreadTotal(open);
  const { data: meta } = useChatMeta(open ? selectedCandidateId : null);
  const markRead = useMarkRead();

  // On-open синк входящих — TG всегда, hh при hh_available (зеркалит ленту карточки).
  const tgSync = useSyncTelegramInbound(selectedCandidateId);
  const hhSync = useSyncHhInbound(selectedCandidateId);
  const tgMutateRef = useRef(tgSync.mutate);
  tgMutateRef.current = tgSync.mutate;
  const hhMutateRef = useRef(hhSync.mutate);
  hhMutateRef.current = hhSync.mutate;
  const tgDoneRef = useRef<string | null>(null);
  const hhDoneRef = useRef<string | null>(null);

  const hhAvailable = meta?.hh_available ?? false;

  useEffect(() => {
    const id = selectedCandidateId;
    if (!open || !id || tgDoneRef.current === id) return;
    tgDoneRef.current = id;
    tgMutateRef.current(undefined, {
      onSuccess: (r) => {
        if (r.imported > 0) queryClient.invalidateQueries({ queryKey: ['candidates', id, 'messages'] });
      },
    });
  }, [open, selectedCandidateId, queryClient]);

  useEffect(() => {
    const id = selectedCandidateId;
    if (!open || !id || !hhAvailable || hhDoneRef.current === id) return;
    hhDoneRef.current = id;
    hhMutateRef.current(undefined, {
      onSuccess: (r) => {
        if (r.imported > 0) queryClient.invalidateQueries({ queryKey: ['candidates', id, 'messages'] });
      },
    });
  }, [open, selectedCandidateId, hhAvailable, queryClient]);

  // Esc — закрыть.
  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [open, close]);

  if (!open) return null;

  const openDialog = (d: ChatDialog) => {
    setSnapshot(d);
    select(d.candidate_id);
    markRead.mutate(d.candidate_id);
  };

  const activeDialog: ChatDialog | null =
    snapshot && snapshot.candidate_id === selectedCandidateId
      ? snapshot
      : dialogs?.find((d) => d.candidate_id === selectedCandidateId) ?? null;

  const goResume = () => {
    if (!activeDialog) return;
    const { candidate_id, vacancy_id } = activeDialog;
    close();
    navigate(vacancy_id ? `/vacancies/${vacancy_id}/candidates/${candidate_id}` : `/candidates/${candidate_id}`);
  };

  const list = dialogs ?? [];
  const seen = activeDialog ? lastSeenLabel(activeDialog.last_inbound_at) : null;
  // ⚠️ Канал отправки — ТОЛЬКО из meta.available_channels (telegram/hh). НЕ откатываться на
  // activeDialog.channel: в истории может быть email (письмо-оффер), а слать туда нельзя (§0/матрица).
  const available = meta?.available_channels ?? [];
  const sendChannel =
    meta?.default_channel && available.includes(meta.default_channel)
      ? meta.default_channel
      : available[0] ?? '';
  // Каналов нет (или meta ещё грузится) → композер честно выключен, а не шлёт «в никуда»/на email.
  const composerDisabled = !activeDialog
    ? null
    : !meta
      ? 'Загрузка каналов…'
      : available.length === 0
        ? 'Нет подключённого канала (Telegram или hh) — ответить нельзя.'
        : null;

  return (
    <>
      <div className="chp-overlay" onClick={close} />
      <div className="chp" role="dialog" aria-label="Чаты с кандидатами">
        {/* Слева — список диалогов */}
        <div className="chp-list">
          <div className="chp-list-head">
            <h3>Чаты</h3>
            {unreadTotal > 0 && <span className="chp-unread-chip">{unreadTotal}</span>}
            <button className="chp-icon-btn" aria-label="Закрыть" onClick={close}>
              <Icon name="x" size={16} />
            </button>
          </div>
          <div className="chp-search">
            <Icon name="search" size={13} style={{ color: 'var(--fg-3)', flex: 'none' }} />
            <input placeholder="Поиск по чатам…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="chp-dialogs">
            {isLoading && list.length === 0 ? (
              <div className="chp-empty-search">Загрузка…</div>
            ) : list.length === 0 ? (
              <div className="chp-empty-search">{debouncedQ ? 'Ничего не найдено' : 'Диалогов пока нет'}</div>
            ) : (
              list.map((d) => {
                const mine = d.last_sender_type === 'recruiter';
                return (
                  <div
                    key={d.candidate_id}
                    className={`chp-dlg ${selectedCandidateId === d.candidate_id ? 'chp-cur' : ''}`}
                    onClick={() => openDialog(d)}
                  >
                    <Avatar name={d.name} src={d.avatar_url} size="sm" />
                    <div className="chp-dlg-main">
                      <div className="chp-dlg-top">
                        <span className="chp-dlg-name">{d.name}</span>
                        <span className="chp-dlg-time">{dialogTime(d.sent_at)}</span>
                      </div>
                      {d.vacancy_name && <div className="chp-dlg-vac">{d.vacancy_name}</div>}
                      <div className="chp-dlg-prev">
                        <span className="chp-dlg-text">
                          {mine ? 'Вы: ' : ''}
                          {d.preview}
                        </span>
                        {d.unread_count > 0 && <span className="chp-dlg-badge">{d.unread_count}</span>}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Справа — переписка / пустое состояние */}
        <div className="chp-thread">
          {!activeDialog ? (
            <div className="chp-empty">
              <div className="chp-empty-art">
                <span className="chp-spark s1">✨</span>
                <span className="chp-spark s2">💬</span>
                <span className="chp-spark s3">💃</span>
                <div className="chp-bub chp-bub-1">👩🏻</div>
                <div className="chp-bub chp-bub-2">🙂</div>
              </div>
              <h4>Начните общаться с кандидатами</h4>
              <p>Выберите диалог слева — вся переписка сохранится в карточке кандидата</p>
            </div>
          ) : (
            <>
              <div className="chp-th">
                <Avatar name={activeDialog.name} src={activeDialog.avatar_url} size="sm" />
                <div className="chp-th-info">
                  <div className="chp-th-name">{activeDialog.name}</div>
                  <div className="chp-th-vac">
                    {activeDialog.vacancy_name}
                    {activeDialog.vacancy_name && seen ? ' · ' : ''}
                    {seen && <span className="chp-th-seen">{seen}</span>}
                  </div>
                </div>
                <button className="chp-resume-btn" onClick={goResume}>
                  <Icon name="open" size={13} /> Резюме
                </button>
              </div>
              <ChatThread
                key={activeDialog.candidate_id}
                candidateId={activeDialog.candidate_id}
                sendChannel={sendChannel}
                variant="popup"
                disabledReason={composerDisabled}
              />
            </>
          )}
        </div>
      </div>
    </>
  );
}
