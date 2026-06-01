import './CandidateTagPicker.css';
import { useState, useRef, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useTags } from '@/api/hooks/useTags';
import { useAddCandidateTag, useRemoveCandidateTag } from '@/api/mutations/candidateTags';

type AssignedTag = { id: string; name: string; color?: string | null };

/**
 * Назначение/снятие тегов кандидату. Только из существующих тегов
 * (создаются/правятся в Настройки → Теги). Рендерит чипы назначенных тегов
 * (с ×) + кнопку «+ Тег» с попапом-списком (галочка = назначен).
 */
export function CandidateTagPicker({
  candidateId,
  assigned,
}: {
  candidateId: string;
  assigned: AssignedTag[];
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data: allTags } = useTags();
  const addTag = useAddCandidateTag();
  const removeTag = useRemoveCandidateTag();

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const assignedIds = new Set(assigned.map((t) => t.id));
  const busy = addTag.isPending || removeTag.isPending;

  const toggle = (tagId: string) => {
    if (busy) return;
    if (assignedIds.has(tagId)) removeTag.mutate({ candidateId, tagId });
    else addTag.mutate({ candidateId, tagId });
  };

  return (
    <>
      {assigned.map((tag) => (
        <span key={tag.id} className="ctp-chip">
          <span className="ctp-dot" style={{ background: tag.color || 'var(--ark-gray-400)' }} />
          {tag.name}
          <button
            className="ctp-chip-x"
            title="Снять тег"
            disabled={busy}
            onClick={() => {
              if (!busy) removeTag.mutate({ candidateId, tagId: tag.id });
            }}
          >
            <Icon name="x" size={11} />
          </button>
        </span>
      ))}

      <div className="ctp-wrap" ref={ref}>
        <button className="ctp-add" onClick={() => setOpen((o) => !o)}>
          + Тег
        </button>
        {open && (
          <div className="ctp-menu">
            {!allTags || allTags.length === 0 ? (
              <div className="ctp-empty">
                Тегов пока нет.
                <br />
                Создайте их в Настройки → Теги.
              </div>
            ) : (
              allTags.map((t) => (
                <button
                  key={t.id}
                  className={`ctp-item ${assignedIds.has(t.id) ? 'on' : ''}`}
                  onClick={() => toggle(t.id)}
                  disabled={busy}
                >
                  <span className="ctp-dot" style={{ background: t.color || 'var(--ark-gray-400)' }} />
                  <span className="ctp-item-name">{t.name}</span>
                  {assignedIds.has(t.id) && <Icon name="check" size={14} />}
                </button>
              ))
            )}
          </div>
        )}
      </div>
    </>
  );
}
