import { useState } from 'react';
import { useComments } from '@/api/hooks/useComments';
import { useAddComment } from '@/api/mutations/candidateDetail';

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
          comments.map((comment: any) => {
            const who = comment.author_name || 'Пользователь';
            return (
              <div className="cmt-item" key={comment.id}>
                <div className="cmt-avatar">{who.charAt(0).toUpperCase()}</div>
                <div className="cmt-body">
                  <div className="cmt-head">
                    <span className="cmt-who">{who}</span>
                    {comment.created_at && (
                      <span className="cmt-time">{fmtTime(comment.created_at)}</span>
                    )}
                  </div>
                  <div className="cmt-text">{comment.body}</div>
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
      </div>
    </div>
  );
}
