import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card, Textarea } from '../components/FormComponents';
import { useMessageTemplates, type MessageTemplateOut } from '@/api/hooks/useMessageTemplates';
import { useCreateMessageTemplate, useUpdateMessageTemplate, useDeleteMessageTemplate } from '@/api/mutations/messageTemplates';
import { useGlafiraSettings } from '@/api/hooks/useGlafiraSettings';
import { useUpdateGlafiraSettings } from '@/api/mutations/settings';
import { POLITE_REJECTION_FALLBACK } from '@/lib/rejection';
import { useAuthStore } from '@/store/authStore';
import type { ApiError } from '@/api/aliases';

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function truncateText(text: string, maxLength: number = 80): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '…';
}

interface SettingsMessageTemplatesProps {
  readOnly?: boolean;
}

export function SettingsMessageTemplates({ readOnly = false }: SettingsMessageTemplatesProps) {
  const { data: templates, isLoading } = useMessageTemplates();
  const createTemplate = useCreateMessageTemplate();
  const updateTemplate = useUpdateMessageTemplate();
  const deleteTemplate = useDeleteMessageTemplate();

  // Текст отказа по умолчанию (GlafiraSettings). Читать может админ+рекрутёр, но
  // PATCH /settings/glafira — только admin, поэтому редактирование гейтим isAdmin
  // (рекрутёр видит текущее значение read-only, иначе словил бы 403 на сохранении).
  const isAdmin = useAuthStore((s) => s.user?.role) === 'admin';
  const { data: glafira, isLoading: glafiraLoading } = useGlafiraSettings();
  const updateGlafira = useUpdateGlafiraSettings();
  const [rejectionDraft, setRejectionDraft] = useState<string | null>(null);
  // Приветствие/подпись письма с оффером (GlafiraSettings). Гейтим редактирование
  // isAdmin — как «Текст отказа по умолчанию» (PATCH /settings/glafira admin-only).
  const [offerHeaderDraft, setOfferHeaderDraft] = useState<string | null>(null);
  const [offerFooterDraft, setOfferFooterDraft] = useState<string | null>(null);

  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [search, setSearch] = useState('');

  // Создание
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [newBody, setNewBody] = useState('');

  // Редактирование (инлайн)
  const [editId, setEditId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editBody, setEditBody] = useState('');

  const filtered = (templates ?? []).filter((t) =>
    t.name.toLowerCase().includes(search.toLowerCase()) ||
    t.body.toLowerCase().includes(search.toLowerCase())
  );

  const notifyErr = (e: unknown, fallback: string) => {
    const err = e as unknown as ApiError;
    setNotification({ type: 'error', message: err.error?.message || fallback });
  };

  const handleCreate = async () => {
    if (!newName.trim() || !newBody.trim()) return;
    try {
      await createTemplate.mutateAsync({
        name: newName.trim(),
        body: newBody.trim(),
        order_index: (templates?.length ?? 0) + 1
      });
      setNewName('');
      setNewBody('');
      setCreating(false);
      setNotification({ type: 'success', message: 'Шаблон создан' });
    } catch (e) {
      notifyErr(e, 'Не удалось создать шаблон');
    }
  };

  const startEdit = (t: MessageTemplateOut) => {
    setEditId(t.id);
    setEditName(t.name);
    setEditBody(t.body);
  };

  const handleSaveEdit = async (id: string) => {
    if (!editName.trim() || !editBody.trim()) return;
    try {
      await updateTemplate.mutateAsync({ id, name: editName.trim(), body: editBody.trim() });
      setEditId(null);
      setNotification({ type: 'success', message: 'Шаблон обновлён' });
    } catch (e) {
      notifyErr(e, 'Не удалось обновить шаблон');
    }
  };

  const handleDelete = async (t: MessageTemplateOut) => {
    const msg = `Удалить шаблон «${t.name}»?`;
    if (!window.confirm(msg)) return;
    try {
      await deleteTemplate.mutateAsync(t.id);
      if (editId === t.id) setEditId(null);
      setNotification({ type: 'success', message: 'Шаблон удалён' });
    } catch (e) {
      notifyErr(e, 'Не удалось удалить шаблон');
    }
  };

  const rejectionValue = rejectionDraft ?? (((glafira as any)?.default_rejection_text as string | null) ?? '');
  const saveRejection = () => {
    if (!isAdmin) return;
    updateGlafira.mutate(
      // Cast: default_rejection_text ещё не в сгенерированном GlafiraSettingsUpdate.
      { default_rejection_text: rejectionValue.trim() || null } as any,
      {
        onSuccess: () => setNotification({ type: 'success', message: 'Текст отказа по умолчанию сохранён' }),
        onError: (e) => notifyErr(e, 'Не удалось сохранить текст отказа'),
      },
    );
  };

  const offerHeaderValue = offerHeaderDraft ?? (glafira?.offer_email_header ?? '');
  const offerFooterValue = offerFooterDraft ?? (glafira?.offer_email_footer ?? '');
  const saveOfferHeader = () => {
    if (!isAdmin) return;
    updateGlafira.mutate(
      // Cast: offer_email_header ещё не в сгенерированном GlafiraSettingsUpdate.
      // Пустое поле шлём ПУСТОЙ СТРОКОЙ, а не null: бек применяет значение через
      // `is not None`, поэтому null молча игнорируется (поле не очищается), а ''
      // сохраняется и на сборке письма трактуется как «вернуть встроенный дефолт».
      { offer_email_header: offerHeaderValue.trim() } as any,
      {
        onSuccess: () => setNotification({ type: 'success', message: 'Приветствие в оффере сохранено' }),
        onError: (e) => notifyErr(e, 'Не удалось сохранить приветствие'),
      },
    );
  };
  const saveOfferFooter = () => {
    if (!isAdmin) return;
    updateGlafira.mutate(
      // Cast: offer_email_footer ещё не в сгенерированном GlafiraSettingsUpdate.
      // Пустую строку (а не null) — по той же причине, что и у приветствия: null
      // бек игнорит (is not None), '' сохраняется и означает «вернуть дефолт».
      { offer_email_footer: offerFooterValue.trim() } as any,
      {
        onSuccess: () => setNotification({ type: 'success', message: 'Подпись в оффере сохранена' }),
        onError: (e) => notifyErr(e, 'Не удалось сохранить подпись'),
      },
    );
  };

  return (
    <div className="set-content-inner">
      <PageHead
        title="Шаблоны сообщений"
        subtitle="Готовые текстовые шаблоны для быстрой отправки сообщений кандидатам в чате"
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
            <input placeholder="Поиск шаблонов…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <div style={{ flex: 1 }} />
          <button
            className="btn btn-primary btn-sm"
            onClick={readOnly ? undefined : () => {
              setNewName('');
              setNewBody('');
              setCreating((c) => !c);
            }}
            disabled={readOnly}
          >
            <Icon name="plus" size={14} />
            Новый шаблон
          </button>
        </div>

        {creating && !readOnly && (
          <div className="tag-edit-row">
            <input
              className="tag-edit-input"
              placeholder="Название шаблона"
              value={newName}
              maxLength={200}
              autoFocus
              onChange={(e) => setNewName(e.target.value)}
            />
            <Textarea
              placeholder="Текст шаблона"
              value={newBody}
              rows={3}
              onChange={setNewBody}
            />
            <button
              className="btn btn-primary btn-sm"
              onClick={handleCreate}
              disabled={createTemplate.isPending || !newName.trim() || !newBody.trim()}
            >
              {createTemplate.isPending ? 'Создание…' : 'Создать'}
            </button>
            <button className="btn btn-secondary btn-sm" onClick={() => setCreating(false)}>
              Отмена
            </button>
          </div>
        )}

        <div className="tags-table mt-table">
          <div className="tt-thead">
            <div>Название</div>
            <div>Текст</div>
            <div>Создан</div>
            <div></div>
          </div>

          {isLoading ? (
            <div className="tt-empty">Загрузка…</div>
          ) : filtered.length === 0 ? (
            <div className="tt-empty">{search ? 'Ничего не найдено' : 'Шаблонов пока нет'}</div>
          ) : (
            filtered.map((t) =>
              editId === t.id ? (
                <div key={t.id} className="tag-edit-row">
                  <input
                    className="tag-edit-input"
                    value={editName}
                    maxLength={200}
                    autoFocus
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSaveEdit(t.id)}
                  />
                  <Textarea
                    value={editBody}
                    rows={3}
                    onChange={setEditBody}
                  />
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleSaveEdit(t.id)}
                    disabled={updateTemplate.isPending || !editName.trim() || !editBody.trim()}
                  >
                    {updateTemplate.isPending ? 'Сохранение…' : 'Сохранить'}
                  </button>
                  <button className="btn btn-secondary btn-sm" onClick={() => setEditId(null)}>
                    Отмена
                  </button>
                </div>
              ) : (
                <div key={t.id} className="tt-row">
                  <div className="tt-name">
                    <span>{t.name}</span>
                  </div>
                  <div className="tt-text" style={{ color: 'var(--fg-2)' }}>
                    {truncateText(t.body)}
                  </div>
                  <div className="t-mono" style={{ fontSize: 12, color: 'var(--fg-2)' }}>
                    {formatDate(t.created_at)}
                  </div>
                  <div className="tt-actions">
                    {!readOnly && (
                      <>
                        <button className="row-icon-btn" title="Изменить" onClick={() => startEdit(t)}>
                          <Icon name="edit" size={15} />
                        </button>
                        <button className="row-icon-btn" title="Удалить" onClick={() => handleDelete(t)}>
                          <Icon name="trash" size={15} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            )
          )}
        </div>
      </Card>

      {/* ── Текст отказа по умолчанию (перенесён из «Общие → Настройки Глафиры») ── */}
      <Card
        title="Текст отказа по умолчанию"
        desc="Отправляется кандидату при отказе, если у вакансии не задан свой текст. Если оставить пустым — используется встроенный вежливый текст (показан подсказкой). Изменять может только администратор."
      >
        {glafiraLoading ? (
          <div className="tt-empty">Загрузка…</div>
        ) : (
          <textarea
            className="nv-textarea"
            placeholder={POLITE_REJECTION_FALLBACK}
            value={rejectionValue}
            onChange={(e) => { if (isAdmin) setRejectionDraft(e.target.value); }}
            onBlur={saveRejection}
            disabled={!isAdmin || updateGlafira.isPending}
            rows={5}
            style={{ width: '100%', resize: 'vertical', minHeight: '110px' }}
          />
        )}
      </Card>

      {/* ── Приветствие в оффере (обрамляет письмо сверху) ── */}
      <Card
        title="Приветствие в оффере"
        desc="Показывается в начале письма с оффером, над телом. Если оставить пустым — используется встроенный текст. Изменять может только администратор."
      >
        {glafiraLoading ? (
          <div className="tt-empty">Загрузка…</div>
        ) : (
          <textarea
            className="nv-textarea"
            placeholder={'Здравствуйте!\n\nРады сообщить, что готовы предложить вам работу в нашей компании.'}
            value={offerHeaderValue}
            onChange={(e) => { if (isAdmin) setOfferHeaderDraft(e.target.value); }}
            onBlur={saveOfferHeader}
            disabled={!isAdmin || updateGlafira.isPending}
            rows={4}
            style={{ width: '100%', resize: 'vertical', minHeight: '90px' }}
          />
        )}
      </Card>

      {/* ── Подпись в оффере (обрамляет письмо снизу) ── */}
      <Card
        title="Подпись в оффере"
        desc="Показывается в конце письма с оффером, под телом. Если оставить пустым — используется встроенный текст. Изменять может только администратор."
      >
        {glafiraLoading ? (
          <div className="tt-empty">Загрузка…</div>
        ) : (
          <textarea
            className="nv-textarea"
            placeholder={'С уважением,\nкоманда подбора'}
            value={offerFooterValue}
            onChange={(e) => { if (isAdmin) setOfferFooterDraft(e.target.value); }}
            onBlur={saveOfferFooter}
            disabled={!isAdmin || updateGlafira.isPending}
            rows={4}
            style={{ width: '100%', resize: 'vertical', minHeight: '90px' }}
          />
        )}
      </Card>
    </div>
  );
}