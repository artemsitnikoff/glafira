import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
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
      {
        body: commentText.trim(),
      },
      {
        onSuccess: () => {
          setCommentText('');
        },
      }
    );
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleAddComment();
    }
  }

  if (isLoading) {
    return (
      <div className="tab-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загружаются комментарии...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="tab-content">
      <h2 style={{ margin: '0 0 var(--space-4) 0', fontSize: '18px', fontWeight: '600' }}>
        Комментарии
      </h2>

      {/* Add Comment Form */}
      <div style={{ marginBottom: 'var(--space-4)', padding: 'var(--space-4)', border: '1px solid var(--border-1)', borderRadius: 'var(--radius-md)' }}>
        <textarea
          value={commentText}
          onChange={(e) => setCommentText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Добавить комментарий... (Ctrl+Enter для отправки)"
          rows={4}
          style={{
            width: '100%',
            padding: 'var(--space-2) var(--space-3)',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-md)',
            resize: 'vertical',
            fontFamily: 'inherit',
            fontSize: '14px',
            marginBottom: 'var(--space-3)',
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleAddComment}
            disabled={!commentText.trim() || addCommentMutation.isPending}
          >
            <Icon name={addCommentMutation.isPending ? "loader" : "message-square"} size={16} />
            Добавить комментарий
          </button>
        </div>
        {addCommentMutation.isError && (
          <div style={{ marginTop: 'var(--space-2)', color: 'var(--stage-rejected)', fontSize: '14px' }}>
            Ошибка добавления: {addCommentMutation.error?.message}
          </div>
        )}
      </div>

      {/* Comments List */}
      {comments && comments.length > 0 ? (
        <div className="list-container">
          {comments.map((comment) => (
            <div key={comment.id} className="list-item">
              <div className="list-item__header">
                <h4 className="list-item__title">
                  <Icon name="user" size={16} style={{ marginRight: 'var(--space-2)' }} />
                  {comment.author_name || 'Пользователь'}
                </h4>
                <span className="list-item__meta">
                  {new Date(comment.created_at).toLocaleDateString('ru', {
                    day: 'numeric',
                    month: 'short',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
              <div className="list-item__content">
                <p style={{ margin: 0, lineHeight: '1.5', whiteSpace: 'pre-wrap' }}>
                  {comment.body}
                </p>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="message-square" size={48} className="empty-state__icon" />
          <p className="empty-state__text">Комментариев пока нет</p>
        </div>
      )}
    </div>
  );
}