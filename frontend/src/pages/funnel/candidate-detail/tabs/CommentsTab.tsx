import { useEffect, useRef, useState } from 'react';
import { useComments, useSyncHhComments, type CommentRow } from '@/api/hooks/useComments';
import { useAddComment } from '@/api/mutations/candidateDetail';
import { linkify } from '@/lib/linkify';
import type { ApiError } from '@/api/aliases';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

export function CommentsTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const [commentText, setCommentText] = useState('');
  const { data: comments, isLoading } = useComments(actualCandidateId);
  const addCommentMutation = useAddComment(actualCandidateId);

  // Фоновый импорт заметок с hh (зеркалит on-open sync + интервал чата, ChatTab).
  // Инвалидация кэша при imported>0 — внутри useSyncHhComments; здесь только
  // in-flight guard + гейт document.hidden, чтобы не долбить hh.
  const syncMutation = useSyncHhComments(actualCandidateId ?? null);
  const syncMutateRef = useRef(syncMutation.mutate);
  syncMutateRef.current = syncMutation.mutate;
  const syncInFlight = useRef(false);
  useEffect(() => {
    if (!actualCandidateId) return;
    const runSync = () => {
      if (syncInFlight.current) return;
      syncInFlight.current = true;
      syncMutateRef.current(undefined, {
        onSettled: () => {
          syncInFlight.current = false;
        },
      });
    };
    runSync(); // при открытии вкладки — сразу
    const timer = setInterval(() => {
      if (document.hidden) return; // не долбим hh, когда вкладка скрыта
      runSync();
    }, 90000);
    return () => clearInterval(timer);
  }, [actualCandidateId]);

  function handleAddComment() {
    if (!commentText.trim()) return;
    addCommentMutation.mutate(
      { body: commentText.trim() },
      { onSuccess: () => setCommentText('') }
    );
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleAddComment();
    }
  }

  const fmtTime = (iso: string) => {
    try {
      return new Date(iso).toLocaleString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return '';
    }
  };

  return (
    <div className="comments-tab">
      <div className="comments-list">
        {isLoading ? (
          <div className="cmt-empty">Загрузка…</div>
        ) : comments && comments.length > 0 ? (
          comments.map((comment: CommentRow) => {
            const who = comment.author_name || 'Пользователь';
            return (
              <div className="cmt-item" key={comment.id}>
                <div className="cmt-avatar">{who.charAt(0).toUpperCase()}</div>
                <div className="cmt-body">
                  <div className="cmt-head">
                    <span className="cmt-who">{who}</span>
                    {/* Заметка импортирована с hh (read-only) — чип на существующем
                        идиоме .src-pill.src-hh (скоуплен к .cand-detail, свои токены). */}
                    {comment.source === 'hh' && <span className="src-pill src-hh">с hh</span>}
                    {comment.created_at && (
                      <span className="cmt-time">{fmtTime(comment.created_at)}</span>
                    )}
                  </div>
                  <div className="cmt-text">{linkify(comment.body)}</div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="cmt-empty">Комментариев пока нет</div>
        )}
      </div>

      <div className="cmt-compose">
        <textarea
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Напишите комментарий…"
          rows={3}
        />
        <div className="cmt-compose-actions">
          <span className="cmt-hint">Ctrl+Enter — отправить</span>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleAddComment}
            disabled={!commentText.trim() || addCommentMutation.isPending}
          >
            Отправить
          </button>
        </div>
        {addCommentMutation.isError && (
          <div className="cmt-hint" style={{ color: 'var(--ark-red-600)' }} role="alert">
            {(addCommentMutation.error as unknown as ApiError)?.error?.message || 'Не удалось добавить комментарий'}
          </div>
        )}
      </div>
    </div>
  );
}
