import { useEffect, useLayoutEffect, useMemo, useRef, useState, Fragment } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useMessagesInfinite } from '@/api/hooks/useMessages';
import { useSendMessage } from '@/api/mutations/candidateDetail';
import { channelMeta } from '@/lib/chat-channels';
import type { MessageOut } from '@/api/aliases';
import '@/styles/chat.css';

// ── Форматирование даты/времени ──────────────────────────────────────────────
function dayKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}
function dayLabel(iso: string): string {
  const now = new Date();
  const yest = new Date(now);
  yest.setDate(now.getDate() - 1);
  if (dayKey(iso) === dayKey(now.toISOString())) return 'Сегодня';
  if (dayKey(iso) === dayKey(yest.toISOString())) return 'Вчера';
  return new Date(iso).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: '2-digit' });
}
function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString('ru', { hour: '2-digit', minute: '2-digit' });
}

// Оптимистичное «в отправке» сообщение (до подтверждения сервером).
type Pending = { tempId: string; body: string; sentAt: string; status: 'sending' | 'error' };

type Props = {
  /** Кандидат-владелец диалога (единый источник: GET/POST /candidates/{id}/messages). */
  candidateId: string;
  /** Канал отправки (в попапе — meta.default_channel; во вкладке — выбранный в селекторе). */
  sendChannel: string;
  /** Косметика композера: popup | tab. */
  variant?: 'popup' | 'tab';
  /** tab: рисовать точку+название канала в мете КАЖДОГО сообщения (в попапе не нужно). */
  showChannel?: boolean;
  /** tab: контролы НАД композером (селектор канала + «Шаблон»). insertText — вставка в черновик. */
  renderComposerExtra?: (api: { insertText: (text: string) => void }) => ReactNode;
  /** tab: подсказка ПОД композером. */
  composerHint?: ReactNode;
  /** Нет доступного канала → композер выключен, показываем причину (честно, не мокаем). */
  disabledReason?: string | null;
};

/**
 * Общая лента переписки + композер. Классы chp-* из эталона (project/styles/chat.css,
 * реализованы в src/styles/chat.css). ЕДИНЫЙ источник данных с вкладкой «Чат»
 * карточки и попапом сайдбара: useMessagesInfinite (лента, queryKey-префикс
 * ['candidates',id,'messages'], поллинг 12с + подгрузка старых по скроллу вверх) +
 * useSendMessage (инвалидирует тот же префикс). Отправка из попапа сразу видна во
 * вкладке и наоборот.
 */
export function ChatThread({
  candidateId,
  sendChannel,
  variant = 'popup',
  showChannel = false,
  renderComposerExtra,
  composerHint,
  disabledReason = null,
}: Props) {
  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } =
    useMessagesInfinite(candidateId);
  const sendMutation = useSendMessage(candidateId);

  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState<Pending[]>([]);
  const tempIdRef = useRef(0);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const prependRef = useRef(false); // текущее обновление ленты — догрузка старых (сохранить позицию)
  const prevHeightRef = useRef(0); // scrollHeight ДО догрузки старых
  const nearBottomRef = useRef(true); // пользователь у нижнего края (можно автоскроллить)
  const didInitScrollRef = useRef(false); // первичный скролл к низу выполнен

  // Загруженные страницы приходят [самая новая, старее, …] → рендерим по возрастанию
  // номера страницы (хронология: старые сверху, новые снизу).
  const serverMsgs = useMemo<MessageOut[]>(() => {
    if (!data) return [];
    return [...data.pages].sort((a, b) => a.page - b.page).flatMap((p) => p.items);
  }, [data]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  // Догрузка старых при приближении к верху (IntersectionObserver, root = сам скролл-контейнер).
  useEffect(() => {
    const root = scrollRef.current;
    const target = topSentinelRef.current;
    if (!root || !target) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          prependRef.current = true;
          prevHeightRef.current = root.scrollHeight;
          fetchNextPage();
        }
      },
      { root, rootMargin: '140px 0px 0px 0px', threshold: 0 }
    );
    io.observe(target);
    return () => io.disconnect();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage, candidateId]);

  // Скролл-менеджмент: догрузка старых — сохранить позицию; новые/первичный рендер — к низу.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (prependRef.current) {
      el.scrollTop = el.scrollHeight - prevHeightRef.current;
      prependRef.current = false;
      return;
    }
    if (!didInitScrollRef.current && serverMsgs.length > 0) {
      el.scrollTop = el.scrollHeight;
      didInitScrollRef.current = true;
      return;
    }
    if (nearBottomRef.current) el.scrollTop = el.scrollHeight;
  }, [serverMsgs]);

  // Своя отправка / оптимистичные сообщения — всегда к низу.
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el && pending.length > 0) el.scrollTop = el.scrollHeight;
  }, [pending]);

  // Смена кандидата — сбрасываем черновик, «висящие» отправки и флаг первичного скролла.
  useEffect(() => {
    setDraft('');
    setPending([]);
    didInitScrollRef.current = false;
    nearBottomRef.current = true;
  }, [candidateId]);

  // Авто-высота многострочного композера: растёт с текстом до 140px (дальше — скролл),
  // схлопывается обратно в одну строку после отправки (draft='') и корректно
  // растёт при вставке шаблона.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [draft]);

  const insertText = (text: string) =>
    setDraft((prev) => (prev.trim() ? `${prev.trimEnd()}\n${text}` : text));

  const doSend = (body: string, tempId: string) => {
    // ⚠️ hh-ответ уходит в ТОТ ЖЕ отклик/negotiation, что и последнее hh-сообщение диалога
    // (кандидат с 2 откликами hh = 2 треда — иначе бек выбрал бы отклик произвольно).
    // MessageOut из протухшего openapi не типизирует application_id → доступ через cast (§3).
    let application_id: string | undefined;
    if (sendChannel === 'hh') {
      for (let i = serverMsgs.length - 1; i >= 0; i--) {
        const appId = (serverMsgs[i] as { application_id?: string | null }).application_id;
        if (serverMsgs[i].channel === 'hh' && appId) {
          application_id = appId;
          break;
        }
      }
    }
    sendMutation.mutate(
      { body, sender_type: 'user', channel: sendChannel, ...(application_id ? { application_id } : {}) },
      {
        onSuccess: () => setPending((p) => p.filter((x) => x.tempId !== tempId)),
        onError: () =>
          setPending((p) => p.map((x) => (x.tempId === tempId ? { ...x, status: 'error' } : x))),
      }
    );
  };

  const send = () => {
    const body = draft.trim();
    if (!body || disabledReason) return;
    const tempId = `tmp-${++tempIdRef.current}`;
    setPending((p) => [...p, { tempId, body, sentAt: new Date().toISOString(), status: 'sending' }]);
    setDraft('');
    doSend(body, tempId);
  };

  const retry = (tempId: string) => {
    const item = pending.find((x) => x.tempId === tempId);
    if (!item) return;
    setPending((p) => p.map((x) => (x.tempId === tempId ? { ...x, status: 'sending' } : x)));
    doSend(item.body, tempId);
  };

  const lastServer = serverMsgs.length ? serverMsgs[serverMsgs.length - 1] : null;
  const pendingNewRun =
    !lastServer || lastServer.direction !== 'out' || dayKey(lastServer.sent_at) !== dayKey(new Date().toISOString());
  const pendingNeedsDay = !lastServer || dayKey(lastServer.sent_at) !== dayKey(new Date().toISOString());

  const isEmpty = serverMsgs.length === 0 && pending.length === 0;

  return (
    <div className="chat-thread">
      <div className="chp-msgs" ref={scrollRef} onScroll={onScroll}>
        <div ref={topSentinelRef} className="chp-top-sentinel" aria-hidden />

        {isFetchingNextPage && (
          <div className="chp-load-older" aria-hidden>
            <span className="chp-skel-line" />
            <span className="chp-skel-line short" />
          </div>
        )}

        {isLoading && isEmpty && <div className="chp-thread-empty">Загрузка…</div>}
        {!isLoading && isEmpty && <div className="chp-thread-empty">Сообщений пока нет</div>}

        {serverMsgs.map((m, i) => {
          const prev = i > 0 ? serverMsgs[i - 1] : null;
          const isMe = m.direction === 'out';
          const dayChanged = !prev || dayKey(prev.sent_at) !== dayKey(m.sent_at);
          const newRun = !prev || prev.direction !== m.direction || dayChanged;
          // hh-контекст: пилюля при смене вакансии между соседними сообщениями.
          // TG (application_id NULL → vacancy_id null) контекст не показывает.
          const prevVac = prev?.vacancy_id ?? null;
          const showContext = !!m.vacancy_id && m.vacancy_id !== prevVac;
          const who = isMe ? m.sender_name || 'Вы' : m.sender_name || 'Кандидат';
          const cm = showChannel ? channelMeta(m.channel) : null;
          return (
            <Fragment key={m.id}>
              {dayChanged && <div className="chp-day">{dayLabel(m.sent_at)}</div>}
              {showContext && (
                <div className="chp-context">
                  {/* application_context уже содержит «Контекст: вакансия {name}» (бэк). */}
                  {m.application_context || 'Контекст: другая вакансия'}
                </div>
              )}
              <div className={`chp-msg ${isMe ? 'out' : 'in'}`}>
                {newRun && <div className="chp-msg-who">{who}</div>}
                {m.body}
                <div className="chp-msg-meta">
                  {cm && (
                    <span className="chp-msg-ch" style={{ '--ch-color': cm.color } as CSSProperties}>
                      <span className="chp-msg-ch-dot" />
                      {cm.label}
                    </span>
                  )}
                  <span>{timeLabel(m.sent_at)}</span>
                  {isMe && (
                    <span className="chp-ticks one" title="Отправлено" aria-label="Отправлено">
                      ✓
                    </span>
                  )}
                </div>
              </div>
            </Fragment>
          );
        })}

        {pending.length > 0 && pendingNeedsDay && <div className="chp-day">Сегодня</div>}
        {pending.map((p, i) => (
          <div key={p.tempId} className={`chp-msg out ${p.status === 'error' ? 'chp-msg-failed' : ''}`}>
            {i === 0 && pendingNewRun && <div className="chp-msg-who">Вы</div>}
            {p.body}
            <div className="chp-msg-meta">
              <span>{timeLabel(p.sentAt)}</span>
              {p.status === 'sending' ? (
                <Icon name="loader" size={11} className="chp-spin" />
              ) : (
                <button type="button" className="chp-retry" onClick={() => retry(p.tempId)}>
                  <Icon name="alert-circle" size={11} /> Не отправлено · Повторить
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {renderComposerExtra && (
        <div className="chp-composer-extra">{renderComposerExtra({ insertText })}</div>
      )}

      {disabledReason ? (
        <div className="chp-composer-disabled">{disabledReason}</div>
      ) : (
        <div className={`chp-composer${variant === 'tab' ? ' chp-composer-tab' : ''}`}>
          <div className="chp-input">
            <textarea
              ref={inputRef}
              rows={1}
              placeholder="Напишите сообщение…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // Enter в одиночку (и Shift+Enter) → новая строка (дефолт textarea).
                // Отправка — только Ctrl+Enter / Cmd+Enter.
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              type="button"
              className="chp-emoji-btn"
              aria-label="Эмодзи"
              onClick={() => setDraft((d) => `${d} 🙂`)}
            >
              🙂
            </button>
          </div>
          <button
            type="button"
            className="chp-send"
            aria-label="Отправить"
            disabled={!draft.trim()}
            onClick={send}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 19V5" />
              <path d="M5 12l7-7 7 7" />
            </svg>
          </button>
        </div>
      )}

      {!disabledReason && composerHint && <div className="chp-composer-hint">{composerHint}</div>}
    </div>
  );
}
