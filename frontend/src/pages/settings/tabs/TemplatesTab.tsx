import { useState, useEffect } from 'react';
import { useEmailTemplates } from '@/api/hooks/useEmailTemplates';
import { useSurveyTemplates } from '@/api/hooks/useSurveyTemplates';
import {
  useCreateEmailTemplate,
  useUpdateEmailTemplate,
  useCreateSurveyTemplate,
  useUpdateSurveyTemplate
} from '@/api/mutations/settings';
import { Icon } from '@/components/ui/Icon';
import type { EmailTemplateOut, SurveyTemplateOut } from '@/api/aliases';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

type TemplateSubTab = 'emails' | 'surveys';

type QuestionType = 'scale_5' | 'scale_10' | 'text' | 'multi';

interface Question {
  id: string;        // uuid v4 на клиенте при создании
  type: QuestionType;
  text: string;
  options?: string[]; // только для type='multi'
}

// Available variables for email templates (static examples as allowed in TZ)
const EMAIL_VARIABLES = [
  '{{candidate_name}}',
  '{{vacancy}}',
  '{{recruiter_name}}',
  '{{interview_link}}',
  '{{salary}}',
  '{{company_name}}',
];

// Static values for preview (as allowed in TZ)
const PREVIEW_VALUES = {
  candidate_name: 'Иван Иванов',
  vacancy: 'Курьер',
  recruiter_name: 'Анна Седова',
  interview_link: 'https://meet.google.com/abc-defg-hij',
  salary: '50 000 рублей',
  company_name: 'ООО "Пример"',
};

// Question type labels
const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  scale_5: 'Шкала 1-5',
  scale_10: 'Шкала 1-10',
  text: 'Свободный текст',
  multi: 'Множественный выбор',
};

// Helpers for questions
const parseQuestions = (questions: { [key: string]: unknown } | undefined): Question[] => {
  if (!questions) return [];

  // Новый формат {items: Question[]}
  if (questions.items && Array.isArray(questions.items)) {
    return questions.items as Question[];
  }

  // Legacy или другой формат - показать пустой список
  if (process.env.NODE_ENV === 'development') {
    console.warn('Unknown questions format, showing empty list:', questions);
  }
  return [];
};

const formatQuestions = (questions: Question[]): { items: Question[] } => {
  return { items: questions };
};

export function TemplatesTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: emailTemplates, isLoading: isLoadingEmails } = useEmailTemplates();
  const { data: surveyTemplates, isLoading: isLoadingSurveys } = useSurveyTemplates();

  const createEmailTemplate = useCreateEmailTemplate();
  const updateEmailTemplate = useUpdateEmailTemplate();
  const createSurveyTemplate = useCreateSurveyTemplate();
  const updateSurveyTemplate = useUpdateSurveyTemplate();

  const [activeSubTab, setActiveSubTab] = useState<TemplateSubTab>('emails');
  const [editingEmailTemplate, setEditingEmailTemplate] = useState<EmailTemplateOut | null>(null);
  const [editingSurveyTemplate, setEditingSurveyTemplate] = useState<SurveyTemplateOut | null>(null);
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [showSurveyModal, setShowSurveyModal] = useState(false);

  // TemplatesTab doesn't have persistent dirty state
  useEffect(() => {
    onDirtyChange(false);
    onSaveHandler(null);
    onDiscardHandler(null);
  }, [onDirtyChange, onSaveHandler, onDiscardHandler]);

  const insertVariable = (variable: string, textareaId: string) => {
    const textarea = document.getElementById(textareaId) as HTMLTextAreaElement;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const text = textarea.value;
      const newText = text.substring(0, start) + variable + text.substring(end);
      textarea.value = newText;

      // Trigger change event
      const event = new Event('input', { bubbles: true });
      textarea.dispatchEvent(event);

      // Set cursor position
      textarea.selectionStart = textarea.selectionEnd = start + variable.length;
      textarea.focus();
    }
  };

  // Moved to component scope for reuse

  const renderEmailsList = () => {
    if (isLoadingEmails) {
      return <div className="settings-loading">Загрузка...</div>;
    }

    return (
      <div className="templates-section">
        <div className="templates-header">
          <h3>Шаблоны писем</h3>
          <button
            className="btn btn-primary"
            onClick={() => setShowEmailModal(true)}
          >
            <Icon name="plus" size={16} />
            Создать шаблон
          </button>
        </div>

        <div className="templates-grid">
          {emailTemplates?.map((template) => (
            <div key={template.id} className="template-card">
              <div className="template-header">
                <div className="template-info">
                  <h4 className="template-name">{template.name}</h4>
                  <span className="template-event-type">{template.event_type}</span>
                </div>
                <div className="template-actions">
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={template.is_enabled}
                      onChange={(e) => updateEmailTemplate.mutate({
                        id: template.id,
                        data: { is_enabled: e.target.checked }
                      })}
                    />
                    <span className="switch-slider"></span>
                  </label>
                </div>
              </div>
              <div className="template-body">
                <p className="template-subject">{template.subject}</p>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setEditingEmailTemplate(template);
                    setShowEmailModal(true);
                  }}
                >
                  <Icon name="settings" size={14} />
                  Редактировать
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  const renderSurveysList = () => {
    if (isLoadingSurveys) {
      return <div className="settings-loading">Загрузка...</div>;
    }

    return (
      <div className="templates-section">
        <div className="templates-header">
          <h3>Опросы Пульса</h3>
          <button
            className="btn btn-primary"
            onClick={() => setShowSurveyModal(true)}
          >
            <Icon name="plus" size={16} />
            Создать опрос
          </button>
        </div>

        <div className="templates-grid">
          {surveyTemplates?.map((template) => (
            <div key={template.id} className="template-card">
              <div className="template-header">
                <div className="template-info">
                  <h4 className="template-name">{template.name}</h4>
                  {template.trigger_day && (
                    <span className="template-trigger">День {template.trigger_day}</span>
                  )}
                </div>
                <div className="template-actions">
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={template.is_enabled}
                      onChange={(e) => updateSurveyTemplate.mutate({
                        id: template.id,
                        data: { is_enabled: e.target.checked }
                      })}
                    />
                    <span className="switch-slider"></span>
                  </label>
                </div>
              </div>
              <div className="template-body">
                <p className="template-questions">
                  {parseQuestions(template.questions).length} вопросов
                </p>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    setEditingSurveyTemplate(template);
                    setShowSurveyModal(true);
                  }}
                >
                  <Icon name="settings" size={14} />
                  Редактировать
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="settings-content-inner">
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Шаблоны</h2>
          <p className="settings-card-desc">Шаблоны писем и опросов для автоматизации коммуникации</p>
        </div>

        {/* Sub-tabs */}
        <div className="sub-tabs">
          <button
            className={`sub-tab ${activeSubTab === 'emails' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('emails')}
          >
            <Icon name="mail" size={16} />
            Письма
          </button>
          <button
            className={`sub-tab ${activeSubTab === 'surveys' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('surveys')}
          >
            <Icon name="activity" size={16} />
            Опросы
          </button>
        </div>

        <div className="sub-tab-content">
          {activeSubTab === 'emails' ? renderEmailsList() : renderSurveysList()}
        </div>
      </div>

      {/* Email Template Modal */}
      {showEmailModal && (
        <EmailTemplateModal
          template={editingEmailTemplate}
          onSave={async (data) => {
            if (editingEmailTemplate) {
              await updateEmailTemplate.mutateAsync({ id: editingEmailTemplate.id, data });
            } else {
              await createEmailTemplate.mutateAsync(data);
            }
            setShowEmailModal(false);
            setEditingEmailTemplate(null);
          }}
          onCancel={() => {
            setShowEmailModal(false);
            setEditingEmailTemplate(null);
          }}
          variables={EMAIL_VARIABLES}
          previewValues={PREVIEW_VALUES}
          onInsertVariable={insertVariable}
        />
      )}

      {/* Survey Template Modal */}
      {showSurveyModal && (
        <SurveyTemplateModal
          template={editingSurveyTemplate}
          onSave={async (data) => {
            if (editingSurveyTemplate) {
              await updateSurveyTemplate.mutateAsync({ id: editingSurveyTemplate.id, data });
            } else {
              await createSurveyTemplate.mutateAsync(data);
            }
            setShowSurveyModal(false);
            setEditingSurveyTemplate(null);
          }}
          onCancel={() => {
            setShowSurveyModal(false);
            setEditingSurveyTemplate(null);
          }}
        />
      )}
    </div>
  );
}

// Email Template Modal Component
type EmailTemplateModalProps = {
  template: EmailTemplateOut | null;
  onSave: (data: any) => Promise<void>;
  onCancel: () => void;
  variables: string[];
  previewValues: Record<string, string>;
  onInsertVariable: (variable: string, textareaId: string) => void;
};

function EmailTemplateModal({ template, onSave, onCancel, variables, previewValues, onInsertVariable }: EmailTemplateModalProps) {
  const [formData, setFormData] = useState({
    name: template?.name || '',
    event_type: template?.event_type || 'screening',
    subject: template?.subject || '',
    body: template?.body || '',
    is_enabled: template?.is_enabled ?? true,
  });
  const [showPreview, setShowPreview] = useState(false);

  const handleSave = async () => {
    await onSave(formData);
  };

  const renderPreview = () => {
    let preview = formData.body;
    Object.entries(previewValues).forEach(([key, value]) => {
      const regex = new RegExp(`{{${key}}}`, 'g');
      preview = preview.replace(regex, value);
    });
    return preview;
  };

  return (
    <div className="modal-overlay">
      <div className="modal modal-large">
        <div className="modal-header">
          <h3 className="modal-title">
            {template ? 'Редактировать шаблон' : 'Новый шаблон письма'}
          </h3>
          <button className="modal-close" onClick={onCancel}>
            <Icon name="x" size={20} />
          </button>
        </div>

        <div className="modal-body">
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label">Название шаблона</label>
              <input
                type="text"
                className="form-input"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="Приглашение на интервью"
              />
            </div>

            <div className="form-field">
              <label className="form-label">Тип события</label>
              <select
                className="form-select"
                value={formData.event_type}
                onChange={(e) => setFormData(prev => ({ ...prev, event_type: e.target.value }))}
              >
                <option value="screening">Скрининг</option>
                <option value="interview">Интервью</option>
                <option value="offer">Оффер</option>
                <option value="rejection">Отказ</option>
              </select>
            </div>

            <div className="form-field form-field-full">
              <label className="form-label">Тема письма</label>
              <input
                type="text"
                className="form-input"
                value={formData.subject}
                onChange={(e) => setFormData(prev => ({ ...prev, subject: e.target.value }))}
                placeholder="Приглашение на собеседование в {{company_name}}"
              />
            </div>

            <div className="form-field form-field-full">
              <div className="textarea-header">
                <label className="form-label">Тело письма</label>
                <div className="textarea-actions">
                  <button
                    type="button"
                    className={`btn btn-ghost btn-sm ${showPreview ? 'active' : ''}`}
                    onClick={() => setShowPreview(!showPreview)}
                  >
                    <Icon name="activity" size={14} />
                    {showPreview ? 'Скрыть превью' : 'Показать превью'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled
                    title="Скоро"
                  >
                    <Icon name="mail" size={14} />
                    Тестовая отправка
                  </button>
                </div>
              </div>

              <div className="template-editor">
                <div className="editor-sidebar">
                  <h4>Переменные:</h4>
                  <div className="variables-list">
                    {variables.map(variable => (
                      <button
                        key={variable}
                        type="button"
                        className="variable-chip"
                        onClick={() => onInsertVariable(variable, 'email-body')}
                      >
                        {variable}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="editor-content">
                  <textarea
                    id="email-body"
                    className="form-textarea"
                    rows={8}
                    value={formData.body}
                    onChange={(e) => setFormData(prev => ({ ...prev, body: e.target.value }))}
                    placeholder="Добрый день, {{candidate_name}}!..."
                  />

                  {showPreview && (
                    <div className="email-preview">
                      <h4>Превью:</h4>
                      <div className="preview-content">
                        {renderPreview()}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>
            Отмена
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!formData.name || !formData.subject || !formData.body}
          >
            {template ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Survey Template Modal Component
type SurveyTemplateModalProps = {
  template: SurveyTemplateOut | null;
  onSave: (data: any) => Promise<void>;
  onCancel: () => void;
};

function SurveyTemplateModal({ template, onSave, onCancel }: SurveyTemplateModalProps) {
  const [formData, setFormData] = useState({
    name: template?.name || '',
    trigger_day: template?.trigger_day || 1,
    interval_days: template?.interval_days || null,
    channels: template?.channels || { email: true },
    questions: template?.questions || {},
    is_enabled: template?.is_enabled ?? true,
  });

  const [questions, setQuestions] = useState<Question[]>(() => {
    return parseQuestions(template?.questions);
  });

  const handleSave = async () => {
    const payload = {
      ...formData,
      questions: formatQuestions(questions),
    };
    await onSave(payload);
  };

  const addQuestion = () => {
    const newQuestion: Question = {
      id: crypto.randomUUID(),
      type: 'scale_5',
      text: '',
    };
    setQuestions(prev => [...prev, newQuestion]);
  };

  const updateQuestion = (id: string, updates: Partial<Question>) => {
    setQuestions(prev => prev.map(q =>
      q.id === id ? { ...q, ...updates } : q
    ));
  };

  const removeQuestion = (id: string) => {
    setQuestions(prev => prev.filter(q => q.id !== id));
  };

  const addOption = (questionId: string) => {
    setQuestions(prev => prev.map(q =>
      q.id === questionId
        ? { ...q, options: [...(q.options || []), ''] }
        : q
    ));
  };

  const updateOption = (questionId: string, optionIndex: number, value: string) => {
    setQuestions(prev => prev.map(q =>
      q.id === questionId
        ? {
            ...q,
            options: q.options?.map((opt, idx) => idx === optionIndex ? value : opt)
          }
        : q
    ));
  };

  const removeOption = (questionId: string, optionIndex: number) => {
    setQuestions(prev => prev.map(q =>
      q.id === questionId
        ? {
            ...q,
            options: q.options?.filter((_, idx) => idx !== optionIndex)
          }
        : q
    ));
  };

  return (
    <div className="modal-overlay">
      <div className="modal modal-large">
        <div className="modal-header">
          <h3 className="modal-title">
            {template ? 'Редактировать опрос' : 'Новый опрос'}
          </h3>
          <button className="modal-close" onClick={onCancel}>
            <Icon name="x" size={20} />
          </button>
        </div>

        <div className="modal-body">
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label">Название опроса</label>
              <input
                type="text"
                className="form-input"
                value={formData.name}
                onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                placeholder="Welcome день 7"
              />
            </div>

            <div className="form-field">
              <label className="form-label">День отправки</label>
              <input
                type="number"
                className="form-input"
                value={formData.trigger_day || ''}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  trigger_day: e.target.value ? parseInt(e.target.value) : 1
                }))}
                placeholder="7"
                min="1"
              />
            </div>

            <div className="form-field">
              <label className="form-label">Интервал (дни)</label>
              <input
                type="number"
                className="form-input"
                value={formData.interval_days || ''}
                onChange={(e) => setFormData(prev => ({
                  ...prev,
                  interval_days: e.target.value ? parseInt(e.target.value) : null
                }))}
                placeholder="30"
                min="1"
              />
            </div>

            <div className="form-field form-field-full">
              <label className="form-label">Каналы отправки</label>
              <div className="checkbox-group">
                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={Boolean(formData.channels?.email)}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      channels: { ...prev.channels, email: e.target.checked }
                    }))}
                  />
                  <span>Email</span>
                </label>
                <label className="checkbox-item">
                  <input
                    type="checkbox"
                    checked={Boolean(formData.channels?.telegram)}
                    onChange={(e) => setFormData(prev => ({
                      ...prev,
                      channels: { ...prev.channels, telegram: e.target.checked }
                    }))}
                  />
                  <span>Telegram</span>
                </label>
              </div>
            </div>

            <div className="form-field form-field-full">
              <label className="form-label">Вопросы</label>
              <div className="survey-questions">
                {questions.map((question) => (
                  <div key={question.id} className="question-card">
                    <div className="question-header">
                      <select
                        className="form-select question-type-select"
                        value={question.type}
                        onChange={(e) => {
                          const newType = e.target.value as QuestionType;
                          const updates: Partial<Question> = { type: newType };
                          if (newType !== 'multi') {
                            updates.options = undefined;
                          } else if (newType === 'multi' && !question.options) {
                            updates.options = [''];
                          }
                          updateQuestion(question.id, updates);
                        }}
                      >
                        {Object.entries(QUESTION_TYPE_LABELS).map(([value, label]) => (
                          <option key={value} value={value}>{label}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="btn btn-ghost btn-sm question-remove"
                        onClick={() => removeQuestion(question.id)}
                        title="Удалить вопрос"
                      >
                        <Icon name="x" size={16} />
                      </button>
                    </div>

                    <div className="question-body">
                      <input
                        type="text"
                        className="form-input"
                        placeholder="Текст вопроса"
                        value={question.text}
                        onChange={(e) => updateQuestion(question.id, { text: e.target.value })}
                      />

                      {question.type === 'multi' && (
                        <div className="question-options">
                          <label className="form-label-sm">Варианты ответов:</label>
                          {question.options?.map((option, index) => (
                            <div key={index} className="option-row">
                              <input
                                type="text"
                                className="form-input"
                                placeholder="Вариант ответа"
                                value={option}
                                onChange={(e) => updateOption(question.id, index, e.target.value)}
                              />
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={() => removeOption(question.id, index)}
                                title="Удалить вариант"
                              >
                                <Icon name="x" size={14} />
                              </button>
                            </div>
                          ))}
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm add-option-btn"
                            onClick={() => addOption(question.id)}
                          >
                            <Icon name="plus" size={14} />
                            Добавить вариант
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                <button
                  type="button"
                  className="btn btn-ghost add-question-btn"
                  onClick={addQuestion}
                >
                  <Icon name="plus" size={16} />
                  Добавить вопрос
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>
            Отмена
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!formData.name}
          >
            {template ? 'Сохранить' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  );
}