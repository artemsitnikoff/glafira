import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useSurveyTemplates } from '@/api/hooks/usePulse';
import { useRunSurvey } from '@/api/mutations/pulse';
import './survey-launch-modal.css';

type Template = {
  id: string;
  name: string;
  trigger_day: number | null;
  is_enabled: boolean;
  questions: unknown;
};

type Props = {
  employeeId: string;
  onClose: () => void;
};

function buildLink(token: string): string {
  return `${window.location.origin}/pulse/survey/#${token}`;
}

function questionsCount(q: unknown): number {
  if (Array.isArray(q)) return q.length;
  if (q && typeof q === 'object') return Object.keys(q).length;
  return 0;
}

export function SurveyLaunchModal({ employeeId, onClose }: Props) {
  const { data: templates, isLoading } = useSurveyTemplates();
  const runSurvey = useRunSurvey();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enabled: Template[] = ((templates as Template[]) || []).filter((t) => t.is_enabled);

  const handleLaunch = async () => {
    if (!selectedId) return;
    setError(null);
    try {
      const survey = await runSurvey.mutateAsync({ employeeId, templateId: selectedId });
      if (survey.public_token) {
        setLink(buildLink(survey.public_token));
      } else {
        setError('Опрос создан, но ссылка не сгенерирована.');
      }
    } catch (e: any) {
      setError(e?.error?.message || 'Не удалось запустить опрос.');
    }
  };

  const handleCopy = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="slm-backdrop" onClick={onClose}>
      <div className="slm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="slm-head">
          <h3>{link ? 'Ссылка на опрос' : 'Запустить опрос'}</h3>
          <button className="slm-close" onClick={onClose} aria-label="Закрыть">
            <Icon name="x" size={18} />
          </button>
        </div>

        {link ? (
          <div className="slm-body">
            <p className="slm-hint">
              Отправьте эту ссылку сотруднику любым удобным способом. Он откроет опрос
              и ответит — результаты появятся в карточке. Ссылка одноразовая.
            </p>
            <div className="slm-link-row">
              <input className="slm-link" readOnly value={link} onFocus={(e) => e.target.select()} />
              <button className="slm-btn slm-btn-primary" onClick={handleCopy}>
                {copied ? 'Скопировано' : 'Копировать'}
              </button>
            </div>
            <div className="slm-actions">
              <button className="slm-btn slm-btn-ghost" onClick={onClose}>Готово</button>
            </div>
          </div>
        ) : (
          <div className="slm-body">
            <p className="slm-hint">Выберите шаблон — вопросы зафиксируются в этом опросе.</p>

            {isLoading ? (
              <div className="slm-empty">Загрузка шаблонов…</div>
            ) : enabled.length === 0 ? (
              <div className="slm-empty">
                Нет включённых шаблонов опросов. Создайте их в разделе «Опросы».
              </div>
            ) : (
              <div className="slm-templates">
                {enabled.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    className={`slm-template ${selectedId === t.id ? 'active' : ''}`}
                    onClick={() => setSelectedId(t.id)}
                  >
                    <span className="slm-tpl-day">
                      {t.trigger_day != null ? `День ${t.trigger_day}` : '—'}
                    </span>
                    <span className="slm-tpl-main">
                      <span className="slm-tpl-name">{t.name}</span>
                      <span className="slm-tpl-meta">{questionsCount(t.questions)} вопросов</span>
                    </span>
                    {selectedId === t.id && <Icon name="check" size={16} />}
                  </button>
                ))}
              </div>
            )}

            {error && <div className="slm-error">{error}</div>}

            <div className="slm-actions">
              <button className="slm-btn slm-btn-ghost" onClick={onClose}>Отмена</button>
              <button
                className="slm-btn slm-btn-primary"
                onClick={handleLaunch}
                disabled={!selectedId || runSurvey.isPending}
              >
                {runSurvey.isPending ? 'Запуск…' : 'Запустить и получить ссылку'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
