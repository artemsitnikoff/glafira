// CSS импортируем В КОМПОНЕНТЕ (а не в страницах-рендерерах), иначе при открытии формы
// из «Кандидаты» (CandidatesPoolPage, без смены URL) lazy-чанки с этими стилями ещё не
// загружены → форма «голая». Базовые .nv-* — из VacancyForm.css, .nc-*/.nv-dd — из своего.
// Порядок: база (VacancyForm) → специфика (NewCandidateForm), чтобы переопределения работали.
import '@/pages/vacancies/VacancyForm.css';
import './NewCandidateForm.css';
import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCreateCandidate } from '@/api/mutations/candidates';
import { useEvaluate, useUpdateCandidate } from '@/api/mutations/candidateDetail';
import { useVacancies } from '@/api/hooks/useVacancies';
import { api } from '@/api/client';
import { useQueryClient } from '@tanstack/react-query';
import type { components } from '@/api/types';
import type { ApiError } from '@/api/aliases';

// Local type to include messengers field not yet in generated types
type CandidateCreateLocal = components['schemas']['CandidateCreate'] & {
  messengers?: { type: string; url: string }[];
};
// CandidateUpdate в types.ts отстаёт (нет source/messengers) — локальное расширение + cast.
type CandidateUpdateLocal = components['schemas']['CandidateUpdate'] & {
  source?: string | null;
  messengers?: { type: string; url: string }[];
};
type CandidateDetailT = components['schemas']['CandidateDetail'];

type Props = {
  // Создание: vacancyId — целевая вакансия. Правка: передаётся candidate (vacancyId не нужен).
  vacancyId?: string;
  candidate?: CandidateDetailT;
  onClose: () => void;
  onSaved?: () => void;
};

const SOURCES = [
  { id: 'hh', name: 'HeadHunter' },
  { id: 'avito', name: 'Avito Работа' },
  { id: 'superjob', name: 'SuperJob' },
  { id: 'telegram', name: 'Telegram-канал' },
  { id: 'referral', name: 'Реферальная программа' },
  { id: 'direct', name: 'Прямой контакт' },
  { id: 'agency', name: 'Кадровое агентство' },
  { id: 'other', name: 'Другое' },
];

const ADD_TYPES = [
  { id: 'manual', name: 'Ручное добавление', disabled: false },
  { id: 'resume', name: 'Из резюме', disabled: false },
  { id: 'pool', name: 'Из общей базы', disabled: true },
  { id: 'hh_link', name: 'По ссылке HH', disabled: true },
];

const SOCIAL_TYPES = [
  { id: 'tg', name: 'Telegram', icon: 'send', prefix: 'https://t.me/' },
  { id: 'wa', name: 'WhatsApp', icon: 'phone', prefix: 'https://wa.me/' },
  { id: 'max', name: 'Max', icon: 'send', prefix: 'https://max.ru/' },
  { id: 'vk', name: 'VK', icon: 'users', prefix: 'https://vk.com/' },
  { id: 'linkedin', name: 'LinkedIn', icon: 'open', prefix: 'https://linkedin.com/in/' },
];

const CURRENCIES = [
  { id: 'RUB', name: 'руб.' },
  { id: 'USD', name: '$' },
  { id: 'EUR', name: '€' },
];

interface DropdownOption {
  id: string;
  name: string;
  disabled?: boolean;
}

function NCDropdown({
  id,
  value,
  onChange,
  options,
  placeholder,
  openId,
  setOpenId,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: DropdownOption[];
  placeholder?: string;
  openId: string | null;
  setOpenId: (id: string | null) => void;
}) {
  const current = options.find(o => o.id === value);
  const isOpen = openId === id;

  return (
    <div className={`nv-dd ${isOpen ? 'open' : ''}`}>
      <button
        type="button"
        className="nv-dd-trigger"
        onClick={() => setOpenId(isOpen ? null : id)}
      >
        <span className={`nv-dd-name ${current ? '' : 'ph'}`}>
          {current ? current.name : (placeholder || 'Выберите значение')}
        </span>
        <Icon name="chevD" size={12} />
      </button>
      {isOpen && (
        <>
          <div className="nv-dd-backdrop" onClick={() => setOpenId(null)} />
          <div className="nv-dd-menu">
            {options.map(option => (
              <button
                key={option.id}
                type="button"
                className={`nv-dd-opt ${option.id === value ? 'sel' : ''} ${option.disabled ? 'disabled' : ''}`}
                onClick={() => {
                  if (!option.disabled) {
                    onChange(option.id);
                    setOpenId(null);
                  }
                }}
              >
                <span>{option.name}{option.disabled ? ' · скоро' : ''}</span>
                {option.id === value && <Icon name="check" size={12} className="nv-dd-check" />}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function parseDate(dateStr: string): string | null {
  if (!dateStr.trim()) return null;

  // Parse DD.MM.YYYY format
  const match = dateStr.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (!match) return null;

  const [, day, month, year] = match;
  const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day));

  // Validate date
  if (
    date.getFullYear() !== parseInt(year) ||
    date.getMonth() !== parseInt(month) - 1 ||
    date.getDate() !== parseInt(day)
  ) {
    return null;
  }

  // Return ISO YYYY-MM-DD из распарсенных частей.
  // НЕ toISOString(): он берёт локальную полночь и переводит в UTC,
  // из-за чего для UTC+ (Москва) дата рождения уезжает на день назад.
  return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
}

// ISO YYYY-MM-DD → ДД.ММ.ГГГГ для предзаполнения поля в режиме правки.
function isoToDisplayDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return '';
  const [, y, mo, d] = m;
  return `${d}.${mo}.${y}`;
}

// Первый мессенджер в объектной форме {type,url}. Форма поддерживает одну соц-сеть;
// старые строковые мессенджеры (["telegram"]) без url замапить нельзя — пропускаем.
function firstSocial(messengers: (Record<string, unknown> | string)[] | undefined): { type: string; url: string } {
  const known = new Set(SOCIAL_TYPES.map(s => s.id));
  for (const m of messengers || []) {
    if (m && typeof m === 'object') {
      const type = String((m as any).type || '');
      const url = String((m as any).url || '');
      if (known.has(type) && url) return { type, url };
    }
  }
  return { type: 'tg', url: '' };
}

export default function NewCandidateForm({ vacancyId, candidate, onClose, onSaved }: Props) {
  const isEdit = !!candidate;
  const createMutation = useCreateCandidate(vacancyId);
  const updateMutation = useUpdateCandidate(candidate?.id || '');
  const { data: vacanciesData } = useVacancies({ status: 'active' });
  const evaluateMutation = useEvaluate();
  const queryClient = useQueryClient();

  const [openDD, setOpenDD] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Соц-сеть на момент открытия правки — чтобы НЕ затирать messengers (в т.ч. несколько),
  // если пользователь поле не трогал.
  const initialSocial = isEdit ? firstSocial(candidate!.messengers as any) : { type: 'tg', url: '' };

  const [formData, setFormData] = useState({
    last_name: candidate?.last_name ?? '',
    first_name: candidate?.first_name ?? '',
    middle_name: candidate?.middle_name ?? '',
    phone: candidate?.phone ?? '',
    email: candidate?.email ?? '',
    gender: (candidate?.gender === 'male' || candidate?.gender === 'female'
      ? candidate.gender
      : 'unset') as 'female' | 'male' | 'unset',
    birth_date: isoToDisplayDate(candidate?.birth_date),
    city: candidate?.city ?? '',
    salary_expectation: candidate?.salary_expectation != null ? String(candidate.salary_expectation) : '',
    currency: candidate?.currency ?? 'RUB',
    source: candidate?.source ?? '',
    add_type: 'manual',
    social_type: initialSocial.type,
    social_url: initialSocial.url,
    target_vacancy: vacancyId ?? '',
    comment: '',
  });

  const updateFormData = (updates: Partial<typeof formData>) => {
    setFormData(prev => ({ ...prev, ...updates }));
    // Clear related errors
    Object.keys(updates).forEach(key => {
      if (errors[key]) {
        setErrors(prev => ({ ...prev, [key]: '' }));
      }
    });
  };

  const vacancies = vacanciesData?.items || [];
  const targetVacancy = vacancies.find(v => v.id === formData.target_vacancy);
  const targetName = targetVacancy?.name || '—';

  const isValid = formData.last_name.trim() && formData.first_name.trim() && formData.source;

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
    }
  };

  const handleSubmit = async () => {
    if (!isValid || isSubmitting) return;

    setIsSubmitting(true);
    setErrors({});

    try {
      // ===== Режим правки: PATCH /candidates/{id}, без вакансии/типа/резюме =====
      if (isEdit && candidate) {
        const socialChanged =
          formData.social_type !== initialSocial.type ||
          formData.social_url.trim() !== initialSocial.url;
        const updatePayload: CandidateUpdateLocal = {
          last_name: formData.last_name.trim(),
          first_name: formData.first_name.trim(),
          middle_name: formData.middle_name.trim() || null,
          source: formData.source,
          phone: formData.phone.trim() || null,
          email: formData.email.trim() || null,
          gender: formData.gender === 'unset' ? null : formData.gender,
          birth_date: parseDate(formData.birth_date),
          city: formData.city.trim() || null,
          salary_expectation: formData.salary_expectation ? parseInt(formData.salary_expectation) : null,
          currency: formData.currency,
          // messengers шлём ТОЛЬКО если поле меняли — иначе не трогаем (сохраняем как есть,
          // в т.ч. несколько/легаси). Изменили → заменяем (или [] при очистке).
          ...(socialChanged
            ? { messengers: formData.social_url.trim() ? [{ type: formData.social_type, url: formData.social_url.trim() }] : [] }
            : {}),
        };
        await updateMutation.mutateAsync(updatePayload as any);
        // Освежаем карточку, воронку, пул и Главную (имя/город/ЗП могли измениться)
        queryClient.invalidateQueries({ queryKey: ['candidates'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies'] });
        queryClient.invalidateQueries({ queryKey: ['home'] });
        onSaved?.();
        onClose();
        return;
      }

      // Prepare payload
      const payload: CandidateCreateLocal = {
        last_name: formData.last_name.trim(),
        first_name: formData.first_name.trim(),
        middle_name: formData.middle_name.trim() || null,
        source: formData.source,
        phone: formData.phone.trim() || null,
        email: formData.email.trim() || null,
        gender: formData.gender === 'unset' ? null : formData.gender,
        birth_date: parseDate(formData.birth_date),
        city: formData.city.trim() || null,
        salary_expectation: formData.salary_expectation ? parseInt(formData.salary_expectation) : null,
        currency: formData.currency,
        add_type: formData.add_type,
        vacancy_id: formData.target_vacancy,
        comment: formData.comment.trim() || null,
        messengers: formData.social_url.trim()
          ? [{ type: formData.social_type, url: formData.social_url.trim() }]
          : undefined,
      };

      // Create candidate
      const newCandidate = await createMutation.mutateAsync(payload as any);

      // Upload resume if file selected. Авто-разбор резюме на бэке работает только для PDF —
      // только тогда профиль (опыт/навыки/«Обо мне») реально заполняется.
      let resumeParsed = false;
      if (selectedFile && newCandidate.id) {
        const isPdf = selectedFile.name.toLowerCase().endsWith('.pdf');
        try {
          const formDataUpload = new FormData();
          formDataUpload.append('file', selectedFile);
          formDataUpload.append('kind', 'resume');

          await api.post(`/candidates/${newCandidate.id}/documents`, formDataUpload, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          resumeParsed = isPdf;
        } catch {
          // Кандидат уже создан — это главное действие. Загрузка резюме
          // вспомогательна: при сбое его можно приложить позже во вкладке
          // «Документы» карточки. Не роняем успешное создание.
        }
      }

      // Авто-оценка Глафиры — fire-and-forget, ТОЛЬКО если резюме реально распарсилось (PDF
      // загружен успешно). Иначе оценка посчиталась бы по пустому профилю и закэшировалась:
      // повторная /glafira/score дедупит, и переоценить после добавления резюме уже нельзя.
      if (newCandidate.id && resumeParsed) {
        try {
          evaluateMutation.mutate(
            { candidate_id: newCandidate.id, vacancy_id: formData.target_vacancy },
            {
              onSuccess: () => {
                // Invalidate evaluation queries to refresh AI tab when user visits it
                queryClient.invalidateQueries({
                  queryKey: ['candidates', newCandidate.id, 'evaluation']
                });
              },
              onError: () => {
                // Оценка некритична: не запустилась — пользователь увидит «не оценён»
                // и сможет запустить вручную из таба «Оценка AI». Создание кандидата не рушим.
              }
            }
          );
        } catch {
          // Оценка некритична — не мешаем созданию кандидата
        }
      }

      onClose();
    } catch (error: any) {
      const e = error as ApiError;
      if (e.error?.code === 'VALIDATION_ERROR') {
        const details = e.error?.details || [];
        const fieldErrors: Record<string, string> = {};
        details.forEach((detail: any) => {
          if (detail.field) {
            fieldErrors[detail.field] = detail.message;
          }
        });
        setErrors(fieldErrors);
      } else {
        setErrors({ general: e.error?.message || (isEdit ? 'Произошла ошибка при сохранении кандидата' : 'Произошла ошибка при создании кандидата') });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="nv-wrap">
      <div className="nv-topbar">
        <div className="nv-crumbs">
          <span className="nv-crumb-home" onClick={onClose}>
            <Icon name="chevL" size={14} /> Назад
          </span>
          <span className="nv-crumb-sep">/</span>
          <span className="nv-crumb-cur">{isEdit ? 'Редактировать кандидата' : 'Добавить кандидата'}</span>
        </div>
        <div className="nv-top-actions">
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <Icon name="x" size={13} /> Отмена
          </button>
        </div>
      </div>

      <div className="nv-grid">
        <div className="nv-card nv-card-full">
          <div className="nv-step-body">
            <div className="nv-h1">{isEdit ? 'Редактировать кандидата' : 'Новый кандидат'}</div>
            <div className="nv-h2">
              {isEdit
                ? 'Измените данные кандидата и сохраните. Резюме и документы — во вкладке «Документы» карточки.'
                : 'Заполните основное и приложите резюме. Глафира распарсит документ и подтянет недостающие поля автоматически.'}
            </div>

            {/* Error banner */}
            {errors.general && (
              <div className="error-banner" style={{ marginBottom: '20px' }}>
                {errors.general}
              </div>
            )}

            {/* Header: avatar + resume drop zone + Excel import — только при создании */}
            {!isEdit && (
            <div className="nc-head">
              <div className="nc-avatar">
                <Icon name="users" size={26} />
                <div className="nc-avatar-cam">
                  <Icon name="open" size={11} />
                </div>
              </div>

              <label className="nc-drop">
                <Icon name="open" size={20} className="nc-drop-icon" />
                <div className="nc-drop-text">
                  <span className="nc-drop-title">
                    {selectedFile ? selectedFile.name : (
                      <>Перетащите резюме или <span className="nc-drop-link">загрузите файл</span></>
                    )}
                  </span>
                  <span className="nc-drop-fmt">
                    PDF · DOC · DOCX · RTF — до 10 МБ
                    {!selectedFile?.name.endsWith('.pdf') && selectedFile && (
                      <span style={{ color: 'var(--ark-yellow-600)', marginLeft: '8px' }}>
                        · авто-разбор пока только PDF
                      </span>
                    )}
                  </span>
                </div>
                <input
                  type="file"
                  accept=".pdf,.doc,.docx,.rtf"
                  hidden
                  onChange={handleFileChange}
                />
              </label>

              <div className="nc-xls disabled" style={{ opacity: 0.5, pointerEvents: 'none' }}>
                <Icon name="chart" size={16} className="nc-xls-icon" />
                <span className="nc-xls-text">
                  <span className="nc-xls-title">Импорт из Excel</span>
                  <span className="nc-xls-sub">XLSX, до 500 строк · скоро</span>
                </span>
              </div>
            </div>
            )}

            {/* Vacancy selection — только при создании (правка не меняет привязку к воронке) */}
            {!isEdit && (
            <div className="nv-field">
              <label className="nv-label">
                Добавить в вакансию <span className="nv-req">*</span>
              </label>
              <NCDropdown
                id="vac"
                value={formData.target_vacancy}
                onChange={v => updateFormData({ target_vacancy: v })}
                options={vacancies.map(v => ({ id: v.id, name: v.name }))}
                openId={openDD}
                setOpenId={setOpenDD}
              />
            </div>
            )}

            {/* Source */}
            <div className="nv-field">
              <label className="nv-label">
                Источник <span className="nv-req">*</span>
                <span className="nv-mute" style={{ fontWeight: 400, marginLeft: 6 }}>
                  · откуда узнали о кандидате
                </span>
              </label>
              <NCDropdown
                id="src"
                value={formData.source}
                onChange={v => updateFormData({ source: v })}
                options={SOURCES}
                placeholder="Выберите источник…"
                openId={openDD}
                setOpenId={setOpenDD}
              />
              {errors.source && <div className="field-error">{errors.source}</div>}
            </div>

            {/* Full name */}
            <div className="nv-grid-3">
              <div className="nv-field">
                <label className="nv-label">
                  Фамилия <span className="nv-req">*</span>
                </label>
                <input
                  className={`nv-input ${errors.last_name ? 'error' : ''}`}
                  value={formData.last_name}
                  onChange={e => updateFormData({ last_name: e.target.value })}
                />
                {errors.last_name && <div className="field-error">{errors.last_name}</div>}
              </div>
              <div className="nv-field">
                <label className="nv-label">
                  Имя <span className="nv-req">*</span>
                </label>
                <input
                  className={`nv-input ${errors.first_name ? 'error' : ''}`}
                  value={formData.first_name}
                  onChange={e => updateFormData({ first_name: e.target.value })}
                />
                {errors.first_name && <div className="field-error">{errors.first_name}</div>}
              </div>
              <div className="nv-field">
                <label className="nv-label">Отчество</label>
                <input
                  className="nv-input"
                  value={formData.middle_name}
                  onChange={e => updateFormData({ middle_name: e.target.value })}
                />
              </div>
            </div>

            {/* Phone + email */}
            <div className="nv-grid-2">
              <div className="nv-field">
                <label className="nv-label">Телефон</label>
                <div className="nc-phone">
                  <span className="nc-phone-flag">🇷🇺</span>
                  <input
                    className="nv-input"
                    placeholder="+7 (___) ___-__-__"
                    value={formData.phone}
                    onChange={e => updateFormData({ phone: e.target.value })}
                  />
                </div>
              </div>
              <div className="nv-field">
                <label className="nv-label">E-mail</label>
                <input
                  className="nv-input"
                  type="email"
                  placeholder="name@example.com"
                  value={formData.email}
                  onChange={e => updateFormData({ email: e.target.value })}
                />
              </div>
            </div>

            {/* Gender / Birthday / City */}
            <div className="nv-grid-3">
              <div className="nv-field">
                <label className="nv-label">Пол</label>
                <div className="nv-segmented" style={{ display: 'flex' }}>
                  <button
                    type="button"
                    className={formData.gender === 'female' ? 'active' : ''}
                    onClick={() => updateFormData({ gender: 'female' })}
                  >
                    Жен.
                  </button>
                  <button
                    type="button"
                    className={formData.gender === 'male' ? 'active' : ''}
                    onClick={() => updateFormData({ gender: 'male' })}
                  >
                    Муж.
                  </button>
                  <button
                    type="button"
                    className={formData.gender === 'unset' ? 'active' : ''}
                    onClick={() => updateFormData({ gender: 'unset' })}
                  >
                    Не указан
                  </button>
                </div>
              </div>
              <div className="nv-field">
                <label className="nv-label">Дата рождения</label>
                <input
                  className="nv-input"
                  placeholder="ДД.ММ.ГГГГ"
                  value={formData.birth_date}
                  onChange={e => updateFormData({ birth_date: e.target.value })}
                />
              </div>
              <div className="nv-field">
                <label className="nv-label">Город проживания</label>
                <input
                  className="nv-input"
                  placeholder="Введите название"
                  value={formData.city}
                  onChange={e => updateFormData({ city: e.target.value })}
                />
              </div>
            </div>

            {/* Salary / Add type */}
            <div className="nv-grid-2">
              <div className="nv-field">
                <label className="nv-label">Ожидаемая ЗП</label>
                <div className="nc-salary">
                  <input
                    className="nv-input"
                    type="number"
                    placeholder="0"
                    value={formData.salary_expectation}
                    onChange={e => updateFormData({ salary_expectation: e.target.value })}
                  />
                  <NCDropdown
                    id="cur"
                    value={formData.currency}
                    onChange={v => updateFormData({ currency: v })}
                    options={CURRENCIES}
                    openId={openDD}
                    setOpenId={setOpenDD}
                  />
                </div>
              </div>
              {!isEdit && (
              <div className="nv-field">
                <label className="nv-label">Тип добавления</label>
                <NCDropdown
                  id="atp"
                  value={formData.add_type}
                  onChange={v => updateFormData({ add_type: v })}
                  options={ADD_TYPES}
                  openId={openDD}
                  setOpenId={setOpenDD}
                />
              </div>
              )}
            </div>

            {/* Social networks */}
            <div className="nv-field">
              <label className="nv-label">Социальные сети</label>
              <div className="nc-social">
                <NCDropdown
                  id="soc"
                  value={formData.social_type}
                  onChange={v => updateFormData({ social_type: v, social_url: '' })}
                  options={SOCIAL_TYPES}
                  openId={openDD}
                  setOpenId={setOpenDD}
                />
                <input
                  className="nv-input"
                  placeholder={SOCIAL_TYPES.find(s => s.id === formData.social_type)?.prefix || ''}
                  value={formData.social_url}
                  onChange={e => updateFormData({ social_url: e.target.value })}
                />
              </div>
            </div>

            {/* Comment — только при создании (правка комментарии не трогает) */}
            {!isEdit && (
            <div className="nv-field">
              <label className="nv-label">Комментарий</label>
              <textarea
                className="nv-textarea"
                rows={3}
                placeholder="Заметка для команды — что обсудили, какой стек, причина обращения…"
                value={formData.comment}
                onChange={e => updateFormData({ comment: e.target.value })}
              />
            </div>
            )}
          </div>

          <div className="nv-card-foot">
            <button className="btn btn-secondary btn-sm" onClick={onClose}>
              <Icon name="chevL" size={13} /> Отмена
            </button>
            <div className="nv-foot-progress">
              {isEdit
                ? <>Изменения кандидата</>
                : <>Кандидат → <b>{targetName}</b></>}
            </div>
            <button
              className={`btn btn-primary btn-sm ${!isValid || isSubmitting ? 'is-disabled' : ''}`}
              disabled={!isValid || isSubmitting}
              onClick={handleSubmit}
            >
              <Icon name={isEdit ? 'check' : 'plus'} size={14} />
              {isEdit
                ? (isSubmitting ? ' Сохранение...' : ' Сохранить')
                : (isSubmitting ? ' Добавление...' : ' Добавить кандидата')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}