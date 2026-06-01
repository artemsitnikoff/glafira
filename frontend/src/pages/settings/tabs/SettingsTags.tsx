import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card } from '../components/FormComponents';
import { useTags, type TagManage } from '@/api/hooks/useTags';
import { useCreateTag, useUpdateTag, useDeleteTag } from '@/api/mutations/tags';
import type { ApiError } from '@/api/aliases';

const TAG_PALETTE = ['#2A8AF0', '#16A34A', '#E0A21A', '#DC4646', '#7E5CF0', '#E26B7E', '#3FA3B3', '#5B6573'];

function softBg(color: string | null): string {
  return color ? `${color}22` : 'var(--bg-3)';
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function ColorPalette({ value, onChange }: { value: string | null; onChange: (c: string) => void }) {
  return (
    <div className="tag-palette">
      {TAG_PALETTE.map((c) => (
        <button
          key={c}
          type="button"
          className={`tag-swatch ${value === c ? 'on' : ''}`}
          style={{ background: c }}
          onClick={() => onChange(c)}
          title={c}
        />
      ))}
    </div>
  );
}

export function SettingsTags() {
  const { data: tags, isLoading } = useTags();
  const createTag = useCreateTag();
  const updateTag = useUpdateTag();
  const deleteTag = useDeleteTag();

  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [search, setSearch] = useState('');

  // Создание
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState<string>(TAG_PALETTE[0]);

  // Редактирование (инлайн)
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editColor, setEditColor] = useState<string | null>(null);

  const filtered = (tags ?? []).filter((t) => t.name.toLowerCase().includes(search.toLowerCase()));

  const notifyErr = (e: unknown, fallback: string) => {
    const err = e as unknown as ApiError;
    setNotification({ type: 'error', message: err.error?.message || fallback });
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await createTag.mutateAsync({ name: newName.trim(), color: newColor });
      setNewName('');
      setNewColor(TAG_PALETTE[0]);
      setCreating(false);
      setNotification({ type: 'success', message: 'Тег создан' });
    } catch (e) {
      notifyErr(e, 'Не удалось создать тег');
    }
  };

  const startEdit = (t: TagManage) => {
    setEditId(t.id);
    setEditName(t.name);
    setEditColor(t.color);
  };

  const handleSaveEdit = async (id: string) => {
    if (!editName.trim()) return;
    try {
      await updateTag.mutateAsync({ id, name: editName.trim(), color: editColor });
      setEditId(null);
      setNotification({ type: 'success', message: 'Тег обновлён' });
    } catch (e) {
      notifyErr(e, 'Не удалось обновить тег');
    }
  };

  const handleDelete = async (t: TagManage) => {
    const msg =
      t.usage_count > 0
        ? `Удалить тег «${t.name}»? Он снимется с ${t.usage_count} кандидат(ов).`
        : `Удалить тег «${t.name}»?`;
    if (!window.confirm(msg)) return;
    try {
      await deleteTag.mutateAsync(t.id);
      if (editId === t.id) setEditId(null);
      setNotification({ type: 'success', message: 'Тег удалён' });
    } catch (e) {
      notifyErr(e, 'Не удалось удалить тег');
    }
  };

  return (
    <div className="set-content-inner">
      <PageHead
        title="Справочник тегов"
        subtitle="Теги для маркировки кандидатов. По ним можно фильтровать в воронке и в общей базе"
      />

      {notification && (
        <div
          className={notification.type === 'success' ? 'info-banner' : 'error-banner'}
          style={{
            background: notification.type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
            borderColor: notification.type === 'success' ? 'var(--success-border)' : 'var(--error-border)',
            color: notification.type === 'success' ? 'var(--success-fg)' : 'var(--error-fg)',
          }}
        >
          <Icon name={notification.type === 'success' ? 'check' : 'x'} size={16} />
          <div>{notification.message}</div>
        </div>
      )}

      <Card>
        <div className="tags-toolbar">
          <div className="users-search">
            <Icon name="search" size={14} />
            <input placeholder="Поиск тегов…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div style={{ flex: 1 }} />
          <button
            className="btn btn-primary btn-sm"
            onClick={() => {
              setNewName('');
              setNewColor(TAG_PALETTE[0]);
              setCreating((c) => !c);
            }}
          >
            <Icon name="plus" size={14} />
            Новый тег
          </button>
        </div>

        {creating && (
          <div className="tag-edit-row">
            <input
              className="tag-edit-input"
              placeholder="Название тега"
              value={newName}
              maxLength={80}
              autoFocus
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            />
            <ColorPalette value={newColor} onChange={setNewColor} />
            <button
              className="btn btn-primary btn-sm"
              onClick={handleCreate}
              disabled={createTag.isPending || !newName.trim()}
            >
              {createTag.isPending ? 'Создание…' : 'Создать'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setCreating(false)}>
              Отмена
            </button>
          </div>
        )}

        <div className="tags-table">
          <div className="tt-thead">
            <div>Тег</div>
            <div style={{ justifyContent: 'flex-end' }}>Кандидатов</div>
            <div>Создан</div>
            <div></div>
          </div>

          {isLoading ? (
            <div className="tt-empty">Загрузка…</div>
          ) : filtered.length === 0 ? (
            <div className="tt-empty">{search ? 'Ничего не найдено' : 'Тегов пока нет — создайте первый'}</div>
          ) : (
            filtered.map((t) =>
              editId === t.id ? (
                <div key={t.id} className="tag-edit-row">
                  <input
                    className="tag-edit-input"
                    value={editName}
                    maxLength={80}
                    autoFocus
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSaveEdit(t.id)}
                  />
                  <ColorPalette value={editColor} onChange={setEditColor} />
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleSaveEdit(t.id)}
                    disabled={updateTag.isPending || !editName.trim()}
                  >
                    {updateTag.isPending ? 'Сохранение…' : 'Сохранить'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setEditId(null)}>
                    Отмена
                  </button>
                </div>
              ) : (
                <div key={t.id} className="tt-row">
                  <div>
                    <span className="tag-chip" style={{ background: softBg(t.color), color: t.color || 'var(--fg-1)' }}>
                      <span className="tag-dot" style={{ background: t.color || 'var(--ark-gray-400)' }} />
                      {t.name}
                    </span>
                  </div>
                  <div className="t-mono tt-num">{t.usage_count}</div>
                  <div className="t-mono" style={{ fontSize: 12, color: 'var(--fg-2)' }}>
                    {formatDate(t.created_at)}
                  </div>
                  <div className="tt-actions">
                    <button className="row-icon-btn" title="Изменить" onClick={() => startEdit(t)}>
                      <Icon name="edit" size={15} />
                    </button>
                    <button className="row-icon-btn" title="Удалить" onClick={() => handleDelete(t)}>
                      <Icon name="trash" size={15} />
                    </button>
                  </div>
                </div>
              )
            )
          )}
        </div>
      </Card>
    </div>
  );
}
