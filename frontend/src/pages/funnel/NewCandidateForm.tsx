// CSS импортируем В КОМПОНЕНТЕ (а не в страницах-рендерерах), иначе при открытии формы
// из «Кандидаты» (CandidatesPoolPage, без смены URL) lazy-чанки с этими стилями ещё не
// загружены → форма «голая». Базовые .nv-* — из VacancyForm.css, .nc-*/.nv-dd — из своего.
// Порядок: база (VacancyForm) → специфика (NewCandidateForm), чтобы переопределения работали.
import '@/pages/vacancies/VacancyForm.css';
import './NewCandidateForm.css';
import { useState, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCreateCandidate } from '@/api/mutations/candidates';
import { useEvaluate, useUpdateCandidate } from '@/api/mutations/candidateDetail';
import { useVacancies } from '@/api/hooks/useVacancies';
import { useParseResume } from '@/api/hooks/useParseResume';
import { api } from '@/api/client';
import { useQueryClient } from '@tanstack/react-query';
import type { components } from '@/api/types';
import type { ApiError } from '@/api/aliases';

// Local type to include fields not yet in generated types (openapi отстаёт)
type CandidateCreateLocal = components['schemas']['CandidateCreate'] & {
  messengers?: { type: string; url: string }[];
  source_url?: string | null;
  experience?: { position: string; company: string; period: string; description?: string }[];
  skills?: string[];
  education?: { institution: string; specialty: string; years: string }[];
  last_position?: string;
  last_company?: string;
  last_period?: string;
  region?: string;
};
// CandidateUpdate в types.ts отстаёт (нет source/messengers/source_url) — локальное расширение.
type CandidateUpdateLocal = components['schemas']['CandidateUpdate'] & {
  source?: string | null;
  messengers?: { type: string; url: string }[];
  source_url?: string | null;
};
type CandidateDetailT = components['schemas']['CandidateDetail'];

type Props = {
  // Создание: vacancyId — целевая вакансия. Правка: передаётся candidate (vacancyId не нужен).
  vacancyId?: string;
  candidate?: CandidateDetailT;
  onClose: () => void;
  onSaved?: () => void;
};

// Значения синхронизированы с CHECK-констрейнтом source на беке (вкл. import/manual —
// иначе при правке импортированного/ручного кандидата дропдаун показывал бы пусто).
const SOURCES = [
  { id: 'hh', name: 'HeadHunter' },
  { id: 'avito', name: 'Avito Работа' },
  { id: 'superjob', name: 'SuperJob' },
  { id: 'linkedin', name: 'LinkedIn' },
  { id: 'telegram', name: 'Telegram-канал' },
  { id: 'referral', name: 'Реферальная программа' },
  { id: 'direct', name: 'Прямой контакт' },
  { id: 'agency', name: 'Кадровое агентство' },
  { id: 'manual', name: 'Ручное добавление' },
  { id: 'import', name: 'Импорт' },
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
  const parseMutation = useParseResume();

  const [openDD, setOpenDD] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isDragging, setIsDragging] = useState(false);

  // State for new sections (only used in create mode)
  const [experience, setExperience] = useState<Array<{
    position: string;
    company: string;
    start: string;
    end: string;
    description: string;
  }>>([]);

  const [skills, setSkills] = useState<string[]>([]);
  const [newSkill, setNewSkill] = useState('');

  const [education, setEducation] = useState<Array<{
    institution: string;
    specialty: string;
    years: string;
  }>>([]);

  // Initialize empty experience and education blocks for create mode
  useEffect(() => {
    if (!isEdit && experience.length === 0) {
      setExperience([{ position: '', company: '', start: '', end: '', description: '' }]);
    }
    if (!isEdit && education.length === 0) {
      setEducation([{ institution: '', specialty: '', years: '' }]);
    }
  }, [isEdit, experience.length, education.length]);

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
    source_url: (candidate as { source_url?: string | null } | undefined)?.source_url ?? '',
    add_type: 'manual',
    social_type: initialSocial.type,
    social_url: initialSocial.url,
    target_vacancy: vacancyId ?? '',
    comment: '',
  });

  const updateFormData = (updates: Partial<typeof formData>) => {
    setFormData(prev => ({ ...prev, ...updates }));
    // Clear related errors and parse error
    const clearErrors: Record<string, string> = {};
    Object.keys(updates).forEach(key => {
      if (errors[key]) {
        clearErrors[key] = '';
      }
    });
    if (errors.parse) {
      clearErrors.parse = '';
    }
    if (Object.keys(clearErrors).length > 0) {
      setErrors(prev => ({ ...prev, ...clearErrors }));
    }
  };

  const vacancies = vacanciesData?.items || [];
  const targetVacancy = vacancies.find(v => v.id === formData.target_vacancy);
  // Без выбранной вакансии кандидат уходит «в базу» (привязать можно позже из карточки пула)
  const targetName = formData.target_vacancy ? (targetVacancy?.name || '—') : 'в базу (без вакансии)';

  const isValid = formData.last_name.trim() && formData.first_name.trim() && formData.source;

  // Parse period string into start/end components for experience
  const parsePeriod = (period: string): { start: string; end: string } => {
    const separators = ['—', '–', ' - ', ' по ', ' до '];
    for (const sep of separators) {
      if (period.includes(sep)) {
        const [start, end] = period.split(sep, 2);
        return { start: start.trim(), end: end.trim() };
      }
    }
    return { start: period.trim(), end: '' };
  };

  // Handle file drop/selection and trigger parsing
  const handleResumeFile = async (file: File) => {
    setSelectedFile(file);

    // Don't parse in edit mode - just attach the file
    if (isEdit) return;

    try {
      const result = await parseMutation.mutateAsync(file);

      if (result.parsed && result.fields) {
        const fields = result.fields;

        // Auto-fill form data - only empty fields to avoid overwriting user input
        const updates: Partial<typeof formData> = {};
        if (!formData.last_name.trim() && fields.last_name) updates.last_name = fields.last_name;
        if (!formData.first_name.trim() && fields.first_name) updates.first_name = fields.first_name;
        if (!formData.middle_name.trim() && fields.middle_name) updates.middle_name = fields.middle_name;
        if (!formData.phone.trim() && fields.phone) updates.phone = fields.phone;
        if (!formData.email.trim() && fields.email) updates.email = fields.email;
        if (!formData.city.trim() && fields.city) updates.city = fields.city;
        if (!formData.salary_expectation.trim() && fields.salary_expectation != null) {
          updates.salary_expectation = String(fields.salary_expectation);
        }
        if (!formData.source_url.trim() && fields.last_position && fields.last_company) {
          // Auto-populate source URL placeholder if we have position/company info
        }

        if (Object.keys(updates).length > 0) {
          updateFormData(updates);
        }

        // Auto-fill experience if current state is empty
        if (experience.length === 0 && fields.experience && fields.experience.length > 0) {
          const parsedExperience = fields.experience.map(exp => ({
            position: exp.position || '',
            company: exp.company || '',
            ...parsePeriod(exp.period || ''),
            description: exp.description || ''
          }));
          setExperience(parsedExperience);
        }

        // Auto-fill skills if current state is empty
        if (skills.length === 0 && fields.skills && fields.skills.length > 0) {
          setSkills(fields.skills.filter(Boolean));
        }

        // Auto-fill education if current state is empty
        if (education.length === 0 && fields.education && fields.education.length > 0) {
          setEducation(fields.education.map(edu => ({
            institution: edu.institution || '',
            specialty: edu.specialty || '',
            years: edu.years || ''
          })));
        }
      } else if (!result.parsed && result.reason) {
        // Show honest error message without alerting
        setErrors({ parse: `Не удалось распознать файл (${result.reason}) — заполните поля вручную` });
      }
    } catch (error) {
      // Graceful fallback - file will still be attached on creation
      setErrors({ parse: 'Ошибка при распознавании файла — заполните поля вручную' });
    }
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      handleResumeFile(file);
    }
  };

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set false if leaving the drop zone itself, not child elements
    if (e.currentTarget === e.target) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleResumeFile(file);
    }
  };

  // Experience management
  const addExperience = () => {
    setExperience(prev => [...prev, { position: '', company: '', start: '', end: '', description: '' }]);
  };

  const updateExperience = (index: number, field: keyof typeof experience[0], value: string) => {
    setExperience(prev => prev.map((exp, i) =>
      i === index ? { ...exp, [field]: value } : exp
    ));
  };

  const removeExperience = (index: number) => {
    setExperience(prev => prev.filter((_, i) => i !== index));
  };

  // Skills management
  const addSkill = () => {
    const skill = newSkill.trim();
    if (skill && !skills.includes(skill)) {
      setSkills(prev => [...prev, skill]);
      setNewSkill('');
    }
  };

  const removeSkill = (skillToRemove: string) => {
    setSkills(prev => prev.filter(skill => skill !== skillToRemove));
  };

  const handleSkillKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addSkill();
    }
  };

  // Education management
  const addEducation = () => {
    setEducation(prev => [...prev, { institution: '', specialty: '', years: '' }]);
  };

  const updateEducation = (index: number, field: keyof typeof education[0], value: string) => {
    setEducation(prev => prev.map((edu, i) =>
      i === index ? { ...edu, [field]: value } : edu
    ));
  };

  const removeEducation = (index: number) => {
    setEducation(prev => prev.filter((_, i) => i !== index));
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
          source_url: formData.source_url.trim() || null,
          // messengers шлём ТОЛЬКО если поле меняли — иначе не трогаем (сохраняем как есть,
          // в т.ч. несколько/легаси). Изменили → заменяем (или [] при очистке).
          ...(socialChanged
            ? { messengers: formData.social_url.trim() ? [{ type: formData.social_type, url: formData.social_url.trim() }] : [] }
            : {}),
        };
        await updateMutation.mutateAsync(updatePayload);
        // Освежаем карточку, воронку, пул и Главную (имя/город/ЗП могли измениться)
        queryClient.invalidateQueries({ queryKey: ['candidates'] });
        queryClient.invalidateQueries({ queryKey: ['vacancies'] });
        queryClient.invalidateQueries({ queryKey: ['home'] });
        onSaved?.();
        onClose();
        return;
      }

      // Prepare experience for payload - combine start/end into period, only include non-empty positions
      const experiencePayload = experience
        .filter(exp => exp.position.trim())
        .map(exp => ({
          position: exp.position.trim(),
          company: exp.company.trim(),
          period: [exp.start.trim(), exp.end.trim()].filter(Boolean).join(' — '),
          description: exp.description.trim() || undefined
        }));

      // Education payload - only include entries with at least one non-empty field
      const educationPayload = education.filter(edu =>
        edu.institution.trim() || edu.specialty.trim() || edu.years.trim()
      );

      // Skills payload - filter out empty skills
      const skillsPayload = skills.filter(Boolean);

      // Extract last position info from first experience entry or manual fields
      const lastPosition = experiencePayload[0]?.position || '';
      const lastCompany = experiencePayload[0]?.company || '';
      const lastPeriod = experiencePayload[0]?.period || '';

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
        // Пусто → null (НЕ '': '' не пройдёт UUID-валидацию → 422). Кандидат уйдёт «в базу».
        vacancy_id: formData.target_vacancy || null,
        comment: formData.comment.trim() || null,
        source_url: formData.source_url.trim() || null,
        messengers: formData.social_url.trim()
          ? [{ type: formData.social_type, url: formData.social_url.trim() }]
          : undefined,
        // New fields
        experience: experiencePayload.length > 0 ? experiencePayload : undefined,
        skills: skillsPayload.length > 0 ? skillsPayload : undefined,
        education: educationPayload.length > 0 ? educationPayload : undefined,
        last_position: lastPosition || undefined,
        last_company: lastCompany || undefined,
        last_period: lastPeriod || undefined,
      };

      // Create candidate
      const newCandidate = await createMutation.mutateAsync(payload);

      // Upload resume if file selected. Авто-разбор резюме на бэке работает только для PDF —
      // только тогда профиль (опыт/навыки/«Обо мне») реально заполняется.
      let resumeParsed = false;
      if (selectedFile && newCandidate.id) {
        const isPdf = selectedFile.name.toLowerCase().endsWith('.pdf');
        try {
          const formDataUpload = new FormData();
          formDataUpload.append('file', selectedFile);
          formDataUpload.append('kind', 'resume');
          formDataUpload.append('parse', 'false'); // Don't re-parse since we already parsed on drop

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
      // Авто-оценка возможна только если кандидат привязан к вакансии (оценка идёт против неё)
      if (newCandidate.id && resumeParsed && formData.target_vacancy) {
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

            {/* Parse error */}
            {errors.parse && (
              <div className="nc-parse-error" style={{ marginBottom: '20px' }}>
                {errors.parse}
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

              <label
                className={`nc-drop ${isDragging ? 'is-drag' : ''}`}
                onDragOver={handleDragOver}
                onDragEnter={handleDragEnter}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {parseMutation.isPending ? (
                  <>
                    <div className="nc-parse-spinner">💃</div>
                    <div className="nc-drop-text">
                      <span className="nc-drop-title">Глафира читает резюме…</span>
                      <span className="nc-drop-fmt">Заполним поля автоматически</span>
                    </div>
                  </>
                ) : (
                  <>
                    <Icon name="open" size={20} className="nc-drop-icon" />
                    <div className="nc-drop-text">
                      <span className="nc-drop-title">
                        {selectedFile ? selectedFile.name : (
                          <>Перетащите резюме или <span className="nc-drop-link">загрузите файл</span></>
                        )}
                      </span>
                      <span className="nc-drop-fmt">
                        PDF · DOCX · TXT — до 10 МБ
                      </span>
                    </div>
                  </>
                )}
                <input
                  type="file"
                  accept=".pdf,.docx,.txt"
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

            {/* Vacancy selection — только при создании (правка не меняет привязку к воронке).
                Вакансия НЕОБЯЗАТЕЛЬНА: можно добавить кандидата «в базу» и привязать позже. */}
            {!isEdit && (
            <div className="nv-field">
              <label className="nv-label">
                Добавить в вакансию
                <span className="nv-mute" style={{ fontWeight: 400, marginLeft: 6 }}>
                  · необязательно — можно оставить в базе
                </span>
              </label>
              <NCDropdown
                id="vac"
                value={formData.target_vacancy}
                onChange={v => updateFormData({ target_vacancy: v })}
                options={[
                  { id: '', name: '— Без привязки (в базу) —' },
                  ...vacancies.map(v => ({ id: v.id, name: v.name })),
                ]}
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

            {/* Ссылка на резюме/профиль у источника (страница резюме на hh.ru и т.п.).
                Для кандидатов с hh заполняется автоматически при импорте. */}
            <div className="nv-field">
              <label className="nv-label">
                Ссылка на резюме
                <span className="nv-mute" style={{ fontWeight: 400, marginLeft: 6 }}>
                  · профиль/резюме на hh.ru и т.п.
                </span>
              </label>
              <input
                className="nv-input"
                type="url"
                placeholder="https://hh.ru/resume/…"
                value={formData.source_url}
                onChange={e => updateFormData({ source_url: e.target.value })}
              />
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

            {/* Salary / Add type. В правке add_type скрыт — убираем grid, чтобы ЗП не была узкой */}
            <div className={isEdit ? '' : 'nv-grid-2'}>
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

            {/* Experience section — только при создании */}
            {!isEdit && (
            <div className="nv-field">
              <label className="nv-label">Опыт работы</label>
              <div className="nc-experience">
                {experience.map((exp, index) => (
                  <div key={index} className="nc-exp-block">
                    <div className="nc-exp-fields">
                      <div className="nv-field">
                        <label className="nv-label">
                          Должность <span className="nv-req">*</span>
                        </label>
                        <input
                          className="nv-input"
                          placeholder="Frontend разработчик"
                          value={exp.position}
                          onChange={e => updateExperience(index, 'position', e.target.value)}
                        />
                      </div>
                      <div className="nv-field">
                        <label className="nv-label">Компания</label>
                        <input
                          className="nv-input"
                          placeholder="ООО «Рога и копыта»"
                          value={exp.company}
                          onChange={e => updateExperience(index, 'company', e.target.value)}
                        />
                      </div>
                      <div className="nv-grid-2">
                        <div className="nv-field">
                          <label className="nv-label">Начало работы</label>
                          <input
                            className="nv-input"
                            placeholder="Январь 2022"
                            value={exp.start}
                            onChange={e => updateExperience(index, 'start', e.target.value)}
                          />
                        </div>
                        <div className="nv-field">
                          <label className="nv-label">Конец работы</label>
                          <input
                            className="nv-input"
                            placeholder="настоящее время"
                            value={exp.end}
                            onChange={e => updateExperience(index, 'end', e.target.value)}
                          />
                        </div>
                      </div>
                      <div className="nv-field">
                        <label className="nv-label">Описание</label>
                        <textarea
                          className="nv-textarea"
                          rows={2}
                          placeholder="Обязанности, достижения, стек технологий…"
                          value={exp.description}
                          onChange={e => updateExperience(index, 'description', e.target.value)}
                        />
                      </div>
                    </div>
                    {experience.length > 1 && (
                      <button
                        type="button"
                        className="nc-exp-remove"
                        onClick={() => removeExperience(index)}
                        title="Удалить место работы"
                      >
                        <Icon name="x" size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="fn-add" onClick={addExperience}>
                  <Icon name="plus" size={14} />
                  Добавить место работы
                </button>
              </div>
            </div>
            )}

            {/* Skills section — только при создании */}
            {!isEdit && (
            <div className="nv-field">
              <label className="nv-label">Навыки</label>
              <div className="nc-skills">
                <div className="nc-skills-input">
                  <input
                    className="nv-input"
                    placeholder="Введите навык и нажмите Enter"
                    value={newSkill}
                    onChange={e => setNewSkill(e.target.value)}
                    onKeyPress={handleSkillKeyPress}
                  />
                </div>
                {skills.length > 0 && (
                  <div className="nc-skills-list">
                    {skills.map((skill, index) => (
                      <div key={index} className="skill-chip">
                        <span>{skill}</span>
                        <button
                          type="button"
                          onClick={() => removeSkill(skill)}
                          className="skill-chip-remove"
                        >
                          <Icon name="x" size={10} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            )}

            {/* Education section — только при создании */}
            {!isEdit && (
            <div className="nv-field">
              <label className="nv-label">Образование</label>
              <div className="nc-education">
                {education.map((edu, index) => (
                  <div key={index} className="nc-edu-block">
                    <div className="nc-edu-fields">
                      <div className="nv-field">
                        <label className="nv-label">Учебное заведение</label>
                        <input
                          className="nv-input"
                          placeholder="МГУ им. М.В. Ломоносова"
                          value={edu.institution}
                          onChange={e => updateEducation(index, 'institution', e.target.value)}
                        />
                      </div>
                      <div className="nv-field">
                        <label className="nv-label">Специальность</label>
                        <input
                          className="nv-input"
                          placeholder="Программная инженерия"
                          value={edu.specialty}
                          onChange={e => updateEducation(index, 'specialty', e.target.value)}
                        />
                      </div>
                      <div className="nv-field">
                        <label className="nv-label">Годы</label>
                        <input
                          className="nv-input"
                          placeholder="2018-2022"
                          value={edu.years}
                          onChange={e => updateEducation(index, 'years', e.target.value)}
                        />
                      </div>
                    </div>
                    {education.length > 1 && (
                      <button
                        type="button"
                        className="nc-edu-remove"
                        onClick={() => removeEducation(index)}
                        title="Удалить образование"
                      >
                        <Icon name="x" size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <button type="button" className="fn-add" onClick={addEducation}>
                  <Icon name="plus" size={14} />
                  Добавить образование
                </button>
              </div>
            </div>
            )}

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