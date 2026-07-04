import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './vacancies/VacancyForm.css';
import { CityAutocomplete } from './vacancies/CityAutocomplete';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { POLITE_REJECTION_FALLBACK } from '@/lib/rejection';
import {
  useCreateVacancy,
  useUpdateVacancy,
  useAddVacancyStage,
  useRenameVacancyStage,
  useDeleteVacancyStage,
  useReorderVacancyStages
} from '@/api/mutations/vacancies';
import { useVacancy } from '@/api/hooks/useVacancy';
import { useVacancyStages } from '@/api/hooks/useVacancyStages';
import { useDefaultFunnel, type DefaultFunnelStage } from '@/api/hooks/useDefaultFunnel';
import { useRejectReasons, type RejectReasonOut } from '@/api/hooks/useRejectReasons';
import { useVacancyRejectReasons } from '@/api/hooks/useVacancyRejectReasons';
import { useFunnelTemplates } from '@/api/hooks/useFunnelTemplates';
import { useMessageTemplates } from '@/api/hooks/useMessageTemplates';
import { api } from '@/api/client';
import {
  useAddVacancyRejectReason,
  useUpdateVacancyRejectReason,
  useDeleteVacancyRejectReason
} from '@/api/mutations/vacancyRejectReasons';
import { useClients } from '@/api/hooks/useClients';
import { useUsers } from '@/api/hooks/useUsers';
import type { components } from '@/api/types';
import type { ApiError } from '@/api/aliases';
import { useHhStatus, useHhVacancies } from '@/api/hooks/useHhIntegration';
import { useHhLinkVacancy, useHhUnlinkVacancy, useHhPublishVacancy } from '@/api/mutations/hhIntegration';
import { useHabrStatus, useHabrVacancies } from '@/api/hooks/useHabrIntegration';
import { useHabrLinkVacancy, useHabrUnlinkVacancy } from '@/api/mutations/habrIntegration';
import { useAvitoStatus } from '@/api/hooks/useAvitoIntegration';
import { useAvitoLinkVacancy, useAvitoUnlinkVacancy } from '@/api/mutations/avitoIntegration';
import { useGlafiraSettings } from '@/api/hooks/useGlafiraSettings';
import { useParseVacancyFile } from '@/api/hooks/useParseVacancyFile';
import { useGenerateRubric } from '@/api/hooks/useGenerateRubric';

type VacancyCreate = components['schemas']['VacancyCreate'];
type VacancyUpdate = components['schemas']['VacancyUpdate'];

// Локальные типы для новых полей автоматизации (openapi отстаёт)
type VacancyFormData = VacancyCreate & {
  auto_qa: boolean;
  auto_reject_message: boolean;
  rejection_text: string | null;
  auto_move_stage: string | null;
  auto_qa_stage: string | null;
  auto_qa_target_stage: string | null;
  auto_qa_mode: string | null;
  auto_qa_fixed_text: string | null;
};

type VacancyCreateExtended = VacancyCreate & {
  auto_qa: boolean;
  auto_reject_message: boolean;
  rejection_text: string | null;
  auto_move_stage: string | null;
  auto_qa_stage: string | null;
  auto_qa_target_stage: string | null;
  auto_qa_mode: string | null;
  auto_qa_fixed_text: string | null;
  stages: StageInput[];
  reject_reasons: Array<{
    side: 'candidate' | 'company';
    label: string;
    order_index: number;
    is_system: boolean;
  }>;
};

type VacancyUpdateExtended = VacancyUpdate & {
  auto_qa: boolean;
  auto_reject_message: boolean;
  rejection_text: string | null;
  auto_move_stage: string | null;
  auto_qa_stage: string | null;
  auto_qa_target_stage: string | null;
  auto_qa_mode: string | null;
  auto_qa_fixed_text: string | null;
};

// Защищённые (системные) этапы — зеркало с бэкенда
const PROTECTED_STAGE_KEYS = new Set(['hired', 'rejected', 'added', 'response']);


// Типы этапов
const FUNNEL_STAGE_TYPES = {
  start: { label: 'Стартовый', dot: '#2A8AF0', bg: '#EAF3FE', fg: '#1865BE' },
  system: { label: 'Системный', dot: '#7E5CF0', bg: '#F0EAFE', fg: '#5C3FBE' },
  middle: { label: 'Промежуточный', dot: '#9AA3AE', bg: '#ECEFF2', fg: '#3A4452' },
  finalOk: { label: 'Финальный · успех', dot: '#16A34A', bg: '#DEF5E5', fg: '#128640' },
  finalBad: { label: 'Финальный · отказ', dot: '#DC4646', bg: '#FCE3E3', fg: '#B83030' },
};

// Дефолтные этапы (эталон)
const NV_DEFAULT_STAGES: Stage[] = [
  { id: 1, name: 'Отклик', type: 'start', desc: 'Кандидат пришёл с источника. Глафира делает первичный скрининг и зовёт в чат.' },
  { id: 3, name: 'Добавлен', type: 'system', desc: 'Кандидат добавлен рекрутером вручную из общей базы. Системный этап, не удаляется.' },
  { id: 2, name: 'Отобран', type: 'middle', desc: 'Глафира посчитала кандидата подходящим — ждём контакта рекрутера.' },
  { id: 4, name: 'Контакт с рекрутером', type: 'middle', desc: 'Назначен/проведён звонок-знакомство.' },
  { id: 5, name: 'Интервью', type: 'middle', desc: 'Техническое или профильное интервью.' },
  { id: 6, name: 'Контакт с менеджером', type: 'middle', desc: 'Финальная встреча с заказчиком.' },
  { id: 7, name: 'Оффер', type: 'middle', desc: 'Оффер выслан и согласовывается.' },
  { id: 8, name: 'Нанят', type: 'finalOk', desc: 'Кандидат вышел на работу. Стартует Пульс-Онбординг.' },
  { id: 9, name: 'Отказ', type: 'finalBad', desc: 'Завершение по причине из справочника.' },
];

// Шаблоны с разными наборами этапов
const FUNNEL_TEMPLATES = [
  {
    id: 'default',
    name: 'По умолчанию',
    stages: NV_DEFAULT_STAGES
  },
  {
    id: 'mass',
    name: 'Массовый подбор · короткая',
    stages: [
      { id: 1, name: 'Отклик', type: 'start', desc: 'Кандидат пришёл с источника.' },
      { id: 2, name: 'Отобран', type: 'middle', desc: 'Подходящий кандидат.' },
      { id: 3, name: 'Интервью', type: 'middle', desc: 'Быстрое собеседование.' },
      { id: 4, name: 'Нанят', type: 'finalOk', desc: 'Успешно принят на работу.' },
      { id: 5, name: 'Отказ', type: 'finalBad', desc: 'Не подошёл.' },
    ] as Stage[]
  },
  {
    id: 'technical',
    name: 'Техническая · с тестовым',
    stages: [
      { id: 1, name: 'Отклик', type: 'start', desc: 'Кандидат пришёл с источника.' },
      { id: 2, name: 'Отобран', type: 'middle', desc: 'Прошёл первичный скрининг.' },
      { id: 3, name: 'Тест', type: 'middle', desc: 'Выполняет тестовое задание.' },
      { id: 4, name: 'Техническое интервью', type: 'middle', desc: 'Разбор решения с техлидом.' },
      { id: 5, name: 'Встреча с командой', type: 'middle', desc: 'Знакомство с будущими коллегами.' },
      { id: 6, name: 'Оффер', type: 'middle', desc: 'Обсуждение условий.' },
      { id: 7, name: 'Нанят', type: 'finalOk', desc: 'Принят в команду.' },
      { id: 8, name: 'Отказ', type: 'finalBad', desc: 'Не подошёл.' },
    ] as Stage[]
  },
  {
    id: 'sales',
    name: 'Продажи · 4 этапа',
    stages: [
      { id: 1, name: 'Отклик', type: 'start', desc: 'Кандидат откликнулся.' },
      { id: 2, name: 'Скрининг', type: 'middle', desc: 'Проверка опыта продаж.' },
      { id: 3, name: 'Ролевая игра', type: 'middle', desc: 'Симуляция продажи.' },
      { id: 4, name: 'Нанят', type: 'finalOk', desc: 'Принят в отдел продаж.' },
      { id: 5, name: 'Отказ', type: 'finalBad', desc: 'Не подошёл.' },
    ] as Stage[]
  },
];

// Типы для редактора
type Stage = {
  id: number;
  name: string;
  type: 'start' | 'system' | 'middle' | 'finalOk' | 'finalBad';
  desc: string;
  stage_key?: string; // Добавлено для работы с API в edit-режиме
  count?: number; // Число кандидатов на этапе (для edit-режима)
};

type StageInput = {
  stage_key: string;
  label: string;
  order_index: number;
  is_terminal: boolean;
  description: string | null;
};

// Описание этапа по stage_key (для предзаполнения карточки этапа в редакторе).
function getStageDescription(stageKey: string, type: Stage['type']): string {
  const descriptions: Record<string, string> = {
    'response': 'Кандидат пришёл с источника. Глафира делает первичный скрининг и зовёт в чат.',
    'added': 'Кандидат добавлен рекрутером вручную из общей базы. Системный этап, не удаляется.',
    'selected': 'Глафира посчитала кандидата подходящим — ждём контакта рекрутера.',
    'recruiter': 'Назначен/проведён звонок-знакомство.',
    'interview': 'Техническое или профильное интервью.',
    'manager': 'Финальная встреча с заказчиком.',
    'offer': 'Оффер выслан и согласовывается.',
    'hired': 'Кандидат вышел на работу. Стартует Пульс-Онбординг.',
    'rejected': 'Завершение по причине из справочника.',
  };
  return descriptions[stageKey] ||
    (type === 'finalOk' ? 'Успешное завершение процесса подбора.' :
     type === 'finalBad' ? 'Завершение процесса по причине отказа.' :
     type === 'system' ? 'Системный этап воронки.' :
     'Этап процесса подбора.');
}

// Воронка по умолчанию компании (GET /settings/default-funnel) → локальные Stage редактора.
// Тип этапа выводится той же логикой, что и в edit-режиме (позиция + is_terminal + защищённость).
function mapDefaultFunnelToStages(funnel: DefaultFunnelStage[]): Stage[] {
  return funnel.map((s, index) => {
    let type: Stage['type'];
    if (index === 0) {
      type = 'start';
    } else if (s.is_terminal) {
      type = s.stage_key === 'hired' || s.label.toLowerCase().includes('нанят') ? 'finalOk' : 'finalBad';
    } else if (PROTECTED_STAGE_KEYS.has(s.stage_key)) {
      type = 'system';
    } else {
      type = 'middle';
    }
    return {
      id: index + 1,
      name: s.label,
      type,
      desc: s.description || getStageDescription(s.stage_key, type),
      stage_key: s.stage_key,
    };
  });
}

// Локальная причина отказа в редакторе формы. key — клиентский стабильный ключ (create-режим).
type RejectReasonLocal = {
  key: string;
  id?: string;            // серверный id (edit-режим)
  side: 'candidate' | 'company';
  label: string;
  order_index: number;
  is_system: boolean;
};

let rrKeyCounter = 0;

function mapCompanyReasonsToLocal(reasons: RejectReasonOut[]): RejectReasonLocal[] {
  // Сид create-режима из дефолтов компании → НОВЫЕ причины вакансии (без серверного id).
  return reasons.map((r, i) => ({
    key: `seed-${i}`,
    side: r.side === 'company' ? 'company' : 'candidate',
    label: r.label,
    order_index: r.order_index ?? i,
    is_system: !!(r as RejectReasonOut).is_system,
  }));
}

const EMPLOYMENT_TYPES = [
  { id: 'full', label: 'Полная' },
  { id: 'part', label: 'Частичная' },
  { id: 'project', label: 'Проектная' },
];

const STEPS = [
  { id: 'desc', label: 'Описание вакансии', icon: 'briefcase' },
  { id: 'funnel', label: 'Воронка', icon: 'funnel' },
  { id: 'team', label: 'Команда', icon: 'users' },
  { id: 'automation', label: 'Автоматизация', icon: 'sparkle' },
];

export default function VacancyFormPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const editMode = !!id;

  const { data: vacancy } = useVacancy(id || '');
  const { data: vacancyStages } = useVacancyStages(id || '');
  const { data: defaultFunnel } = useDefaultFunnel();
  const { data: clients } = useClients();
  const { data: users } = useUsers();

  // Воронка по умолчанию компании из Настроек → локальные Stage. null = пусто/не настроена.
  const companyDefaultStages = useMemo<Stage[] | null>(
    () => (defaultFunnel && defaultFunnel.length > 0 ? mapDefaultFunnelToStages(defaultFunnel) : null),
    [defaultFunnel]
  );
  // Сидируем стартовые этапы из дефолта компании один раз (create-режим). Пусто → остаётся NV_DEFAULT_STAGES.
  const seededFromDefaultRef = useRef(false);

  // Причины отказа: в create-режиме сидируем из дефолтов компании (Настройки) и шлём на submit.
  const { data: companyRejectReasons } = useRejectReasons();
  const [rejectReasons, setRejectReasons] = useState<RejectReasonLocal[]>([]);
  const seededReasonsRef = useRef(false);

  const createMutation = useCreateVacancy();
  const updateMutation = useUpdateVacancy();
  const addStageMutation = useAddVacancyStage();
  const renameStageMutation = useRenameVacancyStage();
  const deleteStageMutation = useDeleteVacancyStage();
  const reorderStagesMutation = useReorderVacancyStages();

  // Парсинг файла вакансии
  const parseVacancyMutation = useParseVacancyFile();
  const [parseIsDragging, setParseIsDragging] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const parseFileInputRef = useRef<HTMLInputElement>(null);

  // Генерация критериев оценки Глафиры
  const generateRubricMutation = useGenerateRubric();
  const [rubricError, setRubricError] = useState<string | null>(null);

  const handleGenerateRubric = async () => {
    setRubricError(null);
    const descriptionText = formData.description || '';
    if (!descriptionText.trim().replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, '').trim()) {
      setRubricError('Сначала заполните описание вакансии');
      return;
    }
    try {
      const result = await generateRubricMutation.mutateAsync({
        name: formData.name || null,
        description: formData.description || null,
        city: formData.city || null,
        department: formData.department || null,
        employment_type: formData.employment_type || null,
        salary_from: formData.salary_from ?? null,
        salary_to: formData.salary_to ?? null,
      });
      if (result.generated && result.rubric) {
        setRecruiterScoring(result.rubric);
      } else {
        setRubricError(result.reason || 'Не удалось сгенерировать критерии');
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : null;
      setRubricError(msg || 'Ошибка при генерации критериев');
    }
  };

  const handleVacancyFile = async (file: File) => {
    setParseError(null);
    try {
      const result = await parseVacancyMutation.mutateAsync(file);
      if (result.parsed) {
        const f = result.fields;
        const updates: Partial<VacancyFormData> = {};
        if (f.name) updates.name = f.name;
        if (f.city) updates.city = f.city;
        if (f.department) updates.department = f.department;
        if (f.employment_type && ['full', 'part', 'project'].includes(f.employment_type)) {
          updates.employment_type = f.employment_type as VacancyFormData['employment_type'];
        }
        if (f.salary_from != null) updates.salary_from = f.salary_from;
        if (f.salary_to != null) updates.salary_to = f.salary_to;
        if (f.description) {
          // Plain-text → HTML: переводы строк превращаем в <br>
          const html = f.description
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
          updates.description = html;
        }
        updateFormData(updates);
      } else if (!result.parsed && result.reason) {
        setParseError(`Не удалось распознать файл (${result.reason}) — заполните поля вручную`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : null;
      setParseError(msg || 'Ошибка при распознавании файла — заполните поля вручную');
    }
  };

  const handleParseFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleVacancyFile(file);
    // сбрасываем value, чтобы можно было выбрать тот же файл повторно
    e.target.value = '';
  };

  const handleParseDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleParseDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setParseIsDragging(true);
  };

  const handleParseDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Сбрасываем только когда курсор реально покинул зону (а не ушёл на дочерний элемент)
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setParseIsDragging(false);
  };

  const handleParseDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setParseIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleVacancyFile(file);
  };

  const [activeStep, setActiveStep] = useState('desc');
  const [formData, setFormData] = useState<VacancyFormData>({
    name: '',
    sort_order: 500,
    client_id: null,
    city: null,
    deadline: null,
    positions_count: 1,
    department: null,
    employment_type: 'full',
    is_confidential: false,
    salary_from: null,
    salary_to: null,
    currency: 'RUB',
    description: null,
    funnel_template: 'default',
    team: [],
    glafira_mode: 'A',
    // Шаг 4 (автоматизация) — реальные поля (П.1/П.2/П.3/П.4 рабочие, дефолт OFF, opt-in)
    auto_move: false,
    auto_move_threshold: 80,
    auto_move_stage: 'selected',
    auto_qa: false,
    auto_qa_stage: 'response',
    auto_qa_target_stage: 'selected',
    auto_qa_mode: 'weak',
    auto_qa_fixed_text: null,
    auto_reject: false,
    auto_reject_message: false,
    rejection_text: null,
  });

  // Состояние этапов воронки
  const [stages, setStages] = useState<Stage[]>(NV_DEFAULT_STAGES);
  // Ошибка сабмита (кнопка создания/сохранения вакансии)
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Инструкции рекрутёра для AI-скоринга (поле вакансии recruiter_scoring_instructions).
  // Держим отдельным state, чтобы не расширять сгенерённый тип VacancyCreate.
  const [recruiterScoring, setRecruiterScoring] = useState('');

  // Pre-populate form in edit mode
  useEffect(() => {
    if (editMode && vacancy) {
      setFormData({
        name: vacancy.name,
        sort_order: vacancy.sort_order,
        client_id: vacancy.client_id,
        city: vacancy.city,
        deadline: vacancy.deadline,
        positions_count: vacancy.positions_count,
        department: vacancy.department,
        employment_type: vacancy.employment_type || 'full',
        is_confidential: vacancy.is_confidential,
        salary_from: vacancy.salary_from,
        salary_to: vacancy.salary_to,
        currency: vacancy.currency,
        description: vacancy.description,
        funnel_template: 'default',
        team: vacancy.team?.map(u => u.id) || [],
        glafira_mode: (vacancy as any).glafira_mode || 'A',
        auto_move: (vacancy as any).auto_move || false,
        auto_move_threshold: (vacancy as any).auto_move_threshold || 80,
        auto_move_stage: (vacancy as any).auto_move_stage || 'selected',
        auto_qa: (vacancy as any).auto_qa || false,
        auto_qa_stage: (vacancy as any).auto_qa_stage || 'response',
        auto_qa_target_stage: (vacancy as any).auto_qa_target_stage || 'selected',
        auto_qa_mode: (vacancy as any).auto_qa_mode || 'weak',
        auto_qa_fixed_text: (vacancy as any).auto_qa_fixed_text ?? null,
        auto_reject: (vacancy as any).auto_reject || false,
        auto_reject_message: (vacancy as any).auto_reject_message || false,
        rejection_text: (vacancy as any).rejection_text || null,
      });
      setRecruiterScoring((vacancy as { recruiter_scoring_instructions?: string | null }).recruiter_scoring_instructions || '');
    }
  }, [editMode, vacancy]);

  // Pre-populate stages in edit mode from API
  useEffect(() => {
    if (editMode && vacancyStages && vacancyStages.length > 0) {
      const apiStages: Stage[] = vacancyStages.map((vStage, index) => {
        // Определяем тип этапа на основе позиции и is_terminal
        let type: Stage['type'];
        if (index === 0) {
          type = 'start';
        } else if (vStage.is_terminal) {
          // Определяем тип финального этапа по stage_key или label
          type = vStage.stage_key === 'hired' || vStage.label.toLowerCase().includes('нанят')
            ? 'finalOk'
            : 'finalBad';
        } else if (PROTECTED_STAGE_KEYS.has(vStage.stage_key)) {
          type = 'system';
        } else {
          type = 'middle';
        }

        return {
          id: index + 1, // Локальный ID для React key
          name: vStage.label,
          type,
          desc: vStage.description || getStageDescription(vStage.stage_key, type),
          stage_key: vStage.stage_key,
          count: vStage.count,
        };
      });

      setStages(apiStages);
    }
  }, [editMode, vacancyStages]);

  // Create-режим: подставить воронку по умолчанию компании как стартовые этапы (один раз).
  useEffect(() => {
    if (editMode) return;
    if (seededFromDefaultRef.current) return;
    if (defaultFunnel === undefined) return; // ещё грузится — ждём
    seededFromDefaultRef.current = true;
    if (companyDefaultStages) {
      setStages(companyDefaultStages);
    }
    // companyDefaultStages == null (дефолт пуст) → остаётся NV_DEFAULT_STAGES (fallback)
  }, [editMode, defaultFunnel, companyDefaultStages]);

  // Create-режим: сид причин отказа из дефолтов компании (один раз).
  useEffect(() => {
    if (editMode) return;
    if (seededReasonsRef.current) return;
    if (companyRejectReasons === undefined) return; // ещё грузится
    seededReasonsRef.current = true;
    setRejectReasons(mapCompanyReasonsToLocal(companyRejectReasons));
  }, [editMode, companyRejectReasons]);

  const currentStepIndex = STEPS.findIndex(s => s.id === activeStep);

  // Валидация перехода
  const canProceed = () => {
    if (activeStep === 'desc') {
      return formData.name.trim().length > 0;
    }
    if (activeStep === 'funnel') {
      return stages.length >= 3;
    }
    return true;
  };

  const handleNext = () => {
    if (!canProceed()) return;

    if (currentStepIndex < STEPS.length - 1) {
      setActiveStep(STEPS[currentStepIndex + 1].id);
    } else {
      handleSubmit();
    }
  };

  const handlePrev = () => {
    if (currentStepIndex > 0) {
      setActiveStep(STEPS[currentStepIndex - 1].id);
    } else {
      navigate('/vacancies');
    }
  };

  const handleSubmit = async () => {
    setSubmitError(null);
    try {
      if (editMode && id) {
        // openapi отстаёт: новые поля auto_qa, rejection_text еще нет в VacancyUpdate
        const updateData = {
          ...formData,
          recruiter_scoring_instructions: recruiterScoring.trim() || null,
        } as VacancyUpdateExtended;
        await updateMutation.mutateAsync({ id, data: updateData });
        navigate(`/vacancies/${id}`);
      } else {
        // Генерируем StageInput из stages для отправки на бэк
        const stageInputs: StageInput[] = stages.map((stage, index) => ({
          stage_key: getStageKey(stage),
          label: stage.name.substring(0, 60), // Ограничение бэка: ≤60 симв
          order_index: index,
          is_terminal: stage.type === 'finalOk' || stage.type === 'finalBad',
          description: stage.desc?.trim() || null,
        }));

        // Причины отказа из формы (сид дефолтов компании ± правки) → привязка к вакансии
        const rejectReasonInputs = rejectReasons.map(r => ({
          side: r.side,
          label: r.label.substring(0, 120),
          order_index: r.order_index,
          is_system: r.is_system,
        }));

        // Добавляем stages + reject_reasons + новые поля автоматизации в payload с приведением типа (openapi не регенерён)
        const payload = {
          ...formData,
          stages: stageInputs,
          reject_reasons: rejectReasonInputs,
          recruiter_scoring_instructions: recruiterScoring.trim() || null,
        } as VacancyCreateExtended;

        const result = await createMutation.mutateAsync(payload);
        navigate(`/vacancies/${result.id}`);
      }
    } catch (error) {
      const e = error as ApiError;
      setSubmitError(e.error?.message || 'Не удалось сохранить вакансию');
    }
  };

  // Генерирует stage_key для этапа
  const getStageKey = (stage: Stage): string => {
    // Этап пришёл из воронки компании / API — сохраняем его реальный ключ (hired/rejected/interview…),
    // не переслугивая по названию (иначе переименованный этап осиротит историю).
    if (stage.stage_key) return stage.stage_key;
    // Канонические ключи для стандартных этапов (важно для hired/rejected)
    const canonicalKeys: Record<string, string> = {
      'Отклик': 'response',
      'Добавлен': 'added',
      'Отобран': 'selected',
      'Контакт с рекрутером': 'recruiter',
      'Интервью': 'interview',
      'Тест': 'test',
      'Контакт с менеджером': 'manager',
      'Оффер': 'offer',
      'Нанят': 'hired',
      'Отказ': 'rejected',
      'Скрининг': 'screening',
      'Ролевая игра': 'roleplay',
      'Техническое интервью': 'tech_interview',
      'Встреча с командой': 'team_meet',
    };

    const canonicalKey = canonicalKeys[stage.name];
    if (canonicalKey) {
      return canonicalKey;
    }

    // Для кастомных этапов генерируем slug
    const slug = stage.name
      .toLowerCase()
      .replace(/[^а-яё\w\s]/g, '')
      .replace(/\s+/g, '_')
      .substring(0, 20);

    return slug || `stage_${stage.id}`;
  };

  const updateFormData = (updates: Partial<VacancyFormData>) => {
    setFormData(prev => ({ ...prev, ...updates }));
  };

  // Прогресс для чипов
  const completion: Record<string, boolean> = {
    desc: formData.name.trim().length > 0,
    funnel: stages.length >= 3,
    team: formData.team.length > 0,
    automation: true, // Всегда проходим
  };

  return (
    <div className="nv-wrap">
      <div className="nv-topbar">
        <div className="nv-crumbs">
          <span className="nv-crumb-home" onClick={() => navigate('/vacancies')}>
            <Icon name="chevL" size={14} /> Вакансии
          </span>
          <span className="nv-crumb-sep">/</span>
          <span className="nv-crumb-cur">
            {editMode ? 'Редактирование вакансии' : 'Создание вакансии'}
          </span>
        </div>
        <div className="nv-top-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/vacancies')}>
            <Icon name="x" size={13} /> Отмена
          </button>
        </div>
      </div>

      {/* Чипсы шагов — 1:1 как воронка в списке вакансий, только индикация */}
      <div className="funnel-row nv-funnel-row">
        {STEPS.map((step, i) => {
          const isActive = step.id === activeStep;
          const isDone = completion[step.id] && !isActive && i < currentStepIndex;
          return (
            <React.Fragment key={step.id}>
              <div className={`funnel-chip nv-chip-readonly ${isActive ? 'active' : ''} ${isDone ? 'funnel-hired' : ''}`}>
                {isDone
                  ? <Icon name="check" size={12} />
                  : <span className="nv-step-num">{i + 1}</span>}
                {step.label}
              </div>
              {i < STEPS.length - 1 && <Icon name="chevR" size={12} className="funnel-arrow" />}
            </React.Fragment>
          );
        })}
      </div>

      {/* Форма на всю ширину — кнопки внутри карточки */}
      <div className="nv-grid">
        <div className="nv-card nv-card-full">
          {activeStep === 'desc' && (
            <DescriptionStep
              data={formData}
              onChange={updateFormData}
              clients={clients || []}
              recruiterScoring={recruiterScoring}
              onRecruiterScoringChange={setRecruiterScoring}
              isParsing={parseVacancyMutation.isPending}
              parseIsDragging={parseIsDragging}
              parseError={parseError}
              parseFileInputRef={parseFileInputRef}
              onParseDragOver={handleParseDragOver}
              onParseDragEnter={handleParseDragEnter}
              onParseDragLeave={handleParseDragLeave}
              onParseDrop={handleParseDrop}
              onParseFileChange={handleParseFileChange}
              editMode={editMode}
              isGeneratingRubric={generateRubricMutation.isPending}
              rubricError={rubricError}
              onGenerateRubric={handleGenerateRubric}
            />
          )}
          {activeStep === 'funnel' && (
            <FunnelStep
              data={formData}
              onChange={updateFormData}
              stages={stages}
              onStagesChange={setStages}
              companyDefaultStages={companyDefaultStages}
              rejectReasons={rejectReasons}
              onRejectReasonsChange={setRejectReasons}
              editMode={editMode}
              vacancyId={id || ''}
              addStageMutation={addStageMutation}
              renameStageMutation={renameStageMutation}
              deleteStageMutation={deleteStageMutation}
              reorderStagesMutation={reorderStagesMutation}
            />
          )}
          {activeStep === 'team' && (
            <TeamStep
              data={formData}
              onChange={updateFormData}
              users={users?.items || []}
            />
          )}
          {activeStep === 'automation' && (
            <AutomationStep
              editMode={editMode}
              vacancyId={id}
              vacancy={vacancy}
              formData={formData}
              onChange={updateFormData}
              autoStages={stages
                .filter((s) => s.type === 'middle')
                .map((s) => ({ key: getStageKey(s), name: s.name }))}
              autoSourceStages={stages
                .filter((s) => s.type !== 'finalOk' && s.type !== 'finalBad')
                .map((s) => ({ key: getStageKey(s), name: s.name }))}
            />
          )}

          {submitError && (
            <div className="error-banner" role="alert">{submitError}</div>
          )}

          <div className="nv-card-foot">
            {currentStepIndex > 0 ? (
              <button className="btn btn-secondary btn-sm" onClick={handlePrev}>
                <Icon name="chevL" size={13} /> Назад
              </button>
            ) : <div />}
            <div className="nv-foot-progress">
              Шаг <b>{currentStepIndex + 1}</b> из <b>{STEPS.length}</b>
            </div>
            <button
              className={`btn btn-primary btn-sm ${!canProceed() ? 'is-disabled' : ''}`}
              disabled={!canProceed()}
              onClick={handleNext}
            >
              <Icon name="arrowRight" size={14} />
              {currentStepIndex === STEPS.length - 1
                ? editMode
                  ? 'Сохранить'
                  : 'Создать вакансию'
                : 'Далее'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Пустой HTML (только <br>/пробелы/&nbsp;) считаем за null, чтобы не хранить мусор.
function normalizeHtml(html: string): string | null {
  const text = html
    .replace(/<br\s*\/?>/gi, '')
    .replace(/&nbsp;/gi, '')
    .replace(/<[^>]+>/g, '')
    .trim();
  return text ? html : null;
}

// Реальный rich-text редактор (contentEditable + execCommand). Ключ к «применяется к
// выделенному»: onMouseDown + preventDefault на кнопках — фокус/выделение НЕ уходят из поля.
function RichTextField({
  value,
  onChange,
  placeholder,
  minHeight,
}: {
  value: string;
  onChange: (html: string | null) => void;
  placeholder?: string;
  minHeight?: number; // переопределить min-height редактируемой области (px)
}) {
  const ref = useRef<HTMLDivElement>(null);

  // Синхронизация из внешнего значения (загрузка данных в edit-режиме) без сброса курсора:
  // переписываем DOM только когда он реально отличается от value.
  useEffect(() => {
    const el = ref.current;
    if (el && el.innerHTML !== value) {
      el.innerHTML = value || '';
    }
  }, [value]);

  const push = () => {
    if (ref.current) onChange(normalizeHtml(ref.current.innerHTML));
  };

  const exec = (e: React.MouseEvent, cmd: string, arg?: string) => {
    e.preventDefault(); // сохраняем выделение внутри редактора
    document.execCommand(cmd, false, arg);
    push();
  };

  const insertLink = (e: React.MouseEvent) => {
    e.preventDefault();
    const sel = window.getSelection();
    const range = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
    const url = window.prompt('Ссылка (URL):', 'https://');
    if (!url) return;
    if (sel && range) {
      sel.removeAllRanges();
      sel.addRange(range);
    }
    document.execCommand('createLink', false, url);
    push();
  };

  return (
    <div className="nv-editor">
      <div className="nv-toolbar">
        <button type="button" className="nv-tb-btn" style={{ fontWeight: 700 }} title="Жирный"
                onMouseDown={e => exec(e, 'bold')}>B</button>
        <button type="button" className="nv-tb-btn" style={{ fontStyle: 'italic' }} title="Курсив"
                onMouseDown={e => exec(e, 'italic')}>I</button>
        <button type="button" className="nv-tb-btn" style={{ textDecoration: 'underline' }} title="Подчёркнутый"
                onMouseDown={e => exec(e, 'underline')}>U</button>
        <span className="nv-tb-sep" />
        <button type="button" className="nv-tb-btn" title="Маркированный список"
                onMouseDown={e => exec(e, 'insertUnorderedList')}>•</button>
        <button type="button" className="nv-tb-btn" title="Нумерованный список"
                onMouseDown={e => exec(e, 'insertOrderedList')}>1.</button>
        <span className="nv-tb-sep" />
        <button type="button" className="nv-tb-btn" title="Ссылка"
                onMouseDown={insertLink}>link</button>
      </div>
      <div
        ref={ref}
        className="nv-rte"
        contentEditable
        suppressContentEditableWarning
        data-placeholder={placeholder}
        onInput={push}
        style={minHeight ? { minHeight } : undefined}
      />
    </div>
  );
}

function DescriptionStep({
  data,
  onChange,
  clients,
  recruiterScoring,
  onRecruiterScoringChange,
  isParsing,
  parseIsDragging,
  parseError,
  parseFileInputRef,
  onParseDragOver,
  onParseDragEnter,
  onParseDragLeave,
  onParseDrop,
  onParseFileChange,
  editMode,
  isGeneratingRubric,
  rubricError,
  onGenerateRubric,
}: {
  data: VacancyCreate;
  onChange: (updates: Partial<VacancyCreate>) => void;
  clients: any[];
  recruiterScoring: string;
  onRecruiterScoringChange: (v: string) => void;
  isParsing: boolean;
  parseIsDragging: boolean;
  parseError: string | null;
  parseFileInputRef: React.RefObject<HTMLInputElement>;
  onParseDragOver: (e: React.DragEvent) => void;
  onParseDragEnter: (e: React.DragEvent) => void;
  onParseDragLeave: (e: React.DragEvent) => void;
  onParseDrop: (e: React.DragEvent) => void;
  onParseFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  editMode: boolean;
  isGeneratingRubric: boolean;
  rubricError: string | null;
  onGenerateRubric: () => void;
}) {
  return (
    <div className="nv-step-body">
      <div className="nv-h1">Описание вакансии</div>
      <div className="nv-h2">Базовая информация — название, локация, дата закрытия. Текст требований и обязанностей.</div>

      {/* Загрузка файла вакансии для AI-парсинга — только при создании */}
      {!editMode && (
        <>
          {parseError && (
            <div className="nc-parse-error" style={{ marginBottom: '16px' }}>
              {parseError}
            </div>
          )}
          <label
            className={`nv-vacancy-drop${parseIsDragging ? ' is-drag' : ''}`}
            onDragOver={onParseDragOver}
            onDragEnter={onParseDragEnter}
            onDragLeave={onParseDragLeave}
            onDrop={onParseDrop}
          >
            {isParsing ? (
              <>
                <div className="nc-parse-spinner">💃</div>
                <div className="nc-drop-text">
                  <span className="nc-drop-title">Глафира читает вакансию…</span>
                  <span className="nc-drop-fmt">Заполним поля автоматически</span>
                </div>
              </>
            ) : (
              <>
                <Icon name="open" size={20} className="nc-drop-icon" />
                <div className="nc-drop-text">
                  <span className="nc-drop-title">
                    Перетащите файл вакансии или <span className="nc-drop-link">загрузите файл</span>
                  </span>
                  <span className="nc-drop-fmt">PDF · DOC · DOCX — до 10 МБ · Глафира заполнит поля</span>
                </div>
              </>
            )}
            <input
              ref={parseFileInputRef}
              type="file"
              accept=".pdf,.doc,.docx"
              hidden
              onChange={onParseFileChange}
            />
          </label>
        </>
      )}

      <div className="nv-field">
        <label className="nv-label">Название вакансии <span className="nv-req">*</span></label>
        <input className="nv-input" placeholder="Например, Frontend-разработчик (Senior)"
               value={data.name} onChange={e => onChange({ name: e.target.value })} />
      </div>

      <div className="nv-field nv-field-sort">
        <label className="nv-label" title="Чем меньше число — тем выше вакансия в списке слева. По умолчанию 500.">
          Сортировка
          <span className="nv-mute" style={{ fontWeight: 400, marginLeft: 6 }}>(порядок в списке)</span>
        </label>
        <input className="nv-input t-mono" type="number" step="10" min="0"
               placeholder="500"
               value={data.sort_order}
               onChange={e => onChange({ sort_order: e.target.value === '' ? 500 : Number(e.target.value) })} />
      </div>

      <div className="nv-grid-3">
        <div className="nv-field">
          <label className="nv-label">Клиент</label>
          {/* Упростим пока до простого селекта, стилизованного как nv-select */}
          <select
            className="nv-input"
            value={data.client_id || ''}
            onChange={e => onChange({ client_id: e.target.value || null })}
            style={{
              height: '38px',
              borderRadius: '8px',
              fontSize: '13px',
              color: data.client_id ? 'var(--fg-1)' : 'var(--fg-3)'
            }}
          >
            <option value="">Выберите клиента…</option>
            {clients.map(client => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </select>
        </div>

        <div className="nv-field">
          <label className="nv-label">Город</label>
          <CityAutocomplete value={data.city ?? null} onChange={city => onChange({ city })} />
        </div>

        <div className="nv-field">
          <label className="nv-label">Ожидаемая дата закрытия</label>
          <input
            className="nv-input"
            type="date"
            value={data.deadline || ''}
            onChange={e => onChange({ deadline: e.target.value || null })}
          />
        </div>
      </div>

      <div className="nv-grid-2">
        <div className="nv-field">
          <label className="nv-label">Кол-во позиций</label>
          <input className="nv-input" type="number" min="1" value={data.positions_count}
                 onChange={e => onChange({ positions_count: Number(e.target.value) })} />
        </div>

        <div className="nv-field">
          <label className="nv-label">Отдел</label>
          <input
            className="nv-input"
            placeholder="Выберите отдел…"
            value={data.department || ''}
            onChange={e => onChange({ department: e.target.value || null })}
          />
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-label">Тип занятости</label>
        <div className="nv-segmented">
{EMPLOYMENT_TYPES.map(type => (
            <button
              key={type.id}
              type="button"
              className={data.employment_type === type.id ? 'active' : ''}
              onClick={() => onChange({ employment_type: type.id as any })}
            >
              {type.label}
            </button>
          ))}
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-toggle-row">
          <span className={`nv-switch ${data.is_confidential ? 'on' : ''}`}>
            <span className="nv-switch-knob" />
          </span>
          <span>
            <b>Конфиденциальная вакансия</b>
            <span className="nv-mute"> · видна только участникам команды</span>
          </span>
        </label>
        <button className="nv-toggle-btn"
                onClick={() => onChange({ is_confidential: !data.is_confidential })}
                style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }} aria-hidden="true" />
      </div>

      <div className="nv-field">
        <label className="nv-label">Зарплатная вилка</label>
        <div className="nv-grid-2-tight">
          <div className="nv-input-wrap">
            <input className="nv-input" placeholder="от" value={data.salary_from || ''}
                   onChange={e => onChange({ salary_from: e.target.value ? Number(e.target.value) : null })} />
            <span className="nv-suffix">₽</span>
          </div>
          <div className="nv-input-wrap">
            <input className="nv-input" placeholder="до" value={data.salary_to || ''}
                   onChange={e => onChange({ salary_to: e.target.value ? Number(e.target.value) : null })} />
            <span className="nv-suffix">₽</span>
          </div>
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-label">Требования, обязанности, условия</label>
        <RichTextField
          value={data.description || ''}
          onChange={html => onChange({ description: html })}
          placeholder={"Требования:\nОбязанности:\nУсловия работы:"}
        />
      </div>

      <div className="nv-field">
        <div className="nv-scoring-label-row">
          <label className="nv-label">Оценка для Глафиры AI</label>
          <button
            type="button"
            className="nv-generate-rubric-btn"
            onClick={onGenerateRubric}
            disabled={isGeneratingRubric}
            title="Глафира разложит требования по весам (0–100) — можно отредактировать"
          >
            {isGeneratingRubric ? (
              <>
                <span className="nv-generate-rubric-spinner">💃</span>
                Глафира составляет критерии…
              </>
            ) : (
              <>
                <Icon name="sparkles" size={13} />
                Сгенерировать критерии
              </>
            )}
          </button>
        </div>
        <div className="nv-h2" style={{ marginTop: 0, marginBottom: 8 }}>
          Этот текст Глафира учитывает при оценке резюме в баллах. Напишите, что важно именно вам:
          ключевые навыки, стоп-факторы, на что обратить внимание.
        </div>
        {rubricError && (
          <div className="nv-rubric-error">{rubricError}</div>
        )}
        <textarea
          className="nv-textarea"
          placeholder="Например: обязателен реальный опыт с Kubernetes от 2 лет; не подходят кандидаты без английского B2; ценим стабильность — насторожить, если меняет работу чаще раза в год."
          value={recruiterScoring}
          onChange={e => onRecruiterScoringChange(e.target.value)}
        />
      </div>
    </div>
  );
}

function FunnelStep({
  data,
  onChange,
  stages,
  onStagesChange,
  companyDefaultStages = null,
  rejectReasons,
  onRejectReasonsChange,
  editMode = false,
  vacancyId,
  addStageMutation,
  renameStageMutation,
  deleteStageMutation,
  reorderStagesMutation,
}: {
  data: VacancyCreate;
  onChange: (updates: Partial<VacancyCreate>) => void;
  stages: Stage[];
  onStagesChange: (stages: Stage[]) => void;
  companyDefaultStages?: Stage[] | null;
  rejectReasons: RejectReasonLocal[];
  onRejectReasonsChange: (reasons: RejectReasonLocal[]) => void;
  editMode?: boolean;
  vacancyId?: string;
  addStageMutation?: any;
  renameStageMutation?: any;
  deleteStageMutation?: any;
  reorderStagesMutation?: any;
}) {
  // Ошибка операции над этапом (инлайн-баннер вместо alert — паттерн проекта)
  const [stageError, setStageError] = useState<string | null>(null);
  // Базовое значение названия на момент фокуса — чтобы PATCH'ить только при реальном изменении
  const renameBaseline = useRef<Record<string, string>>({});
  const descBaseline = useRef<Record<string, string>>({});

  // Шаблоны воронок из Настроек (БД). Пусто (до seed) → хардкод-пресеты как fallback.
  const { data: backendTemplates } = useFunnelTemplates();
  const templateOptions = useMemo<{ id: string; name: string; backend: boolean }[]>(() => {
    const base = [{ id: 'default', name: 'По умолчанию', backend: false }];
    if (backendTemplates && backendTemplates.length > 0) {
      return [...base, ...backendTemplates.map(t => ({ id: t.id, name: t.name, backend: true }))];
    }
    return [...base, ...FUNNEL_TEMPLATES.filter(t => t.id !== 'default').map(t => ({ id: t.id, name: t.name, backend: false }))];
  }, [backendTemplates]);

  // Применить выбранный шаблон
  const applyTemplate = async (opt: { id: string; backend: boolean }) => {
    // В edit-режиме шаблоны не применяем — этапы управляются через API
    if (editMode) return;

    if (opt.id === 'default') {
      // «По умолчанию» = воронка из Настроек (company_default_stages). Пусто → хардкод-эталон.
      const base = companyDefaultStages && companyDefaultStages.length > 0
        ? companyDefaultStages
        : NV_DEFAULT_STAGES;
      onStagesChange(base.map(s => ({ ...s })));
    } else if (opt.backend) {
      // Шаблон из БД — тянем его этапы
      try {
        const res = await api.get(`/settings/funnel-templates/${opt.id}/stages`);
        onStagesChange(mapDefaultFunnelToStages(res.data as DefaultFunnelStage[]));
      } catch {
        setStageError('Не удалось загрузить шаблон воронки');
      }
    } else {
      // Fallback-пресет (хардкод, пока в БД пусто)
      const template = FUNNEL_TEMPLATES.find(t => t.id === opt.id);
      if (template) {
        onStagesChange(template.stages.map(s => ({ ...s })));
      }
    }
    onChange({ funnel_template: opt.id });
  };

  // Перемещение этапа
  const moveStage = async (idx: number, dir: number) => {
    const j = idx + dir;
    // Нельзя двигать в зоны 1-го и 2 последних (эталонная логика)
    if (j < 1 || j > stages.length - 2) return;
    if (idx === 0 || idx >= stages.length - 2) return;

    if (editMode && vacancyId && reorderStagesMutation) {
      // В edit-режиме отправляем reorder запрос
      setStageError(null);
      const next = stages.slice();
      [next[idx], next[j]] = [next[j], next[idx]];

      const orderKeys = next.map(stage => stage.stage_key!);

      try {
        await reorderStagesMutation.mutateAsync({
          vacancyId,
          data: { order: orderKeys }
        });
      } catch (error: any) {
        const e = error as ApiError;
        setStageError(e.error?.message || 'Ошибка при изменении порядка этапов');
      }
    } else {
      // В create-режиме локальная мутация
      const next = stages.slice();
      [next[idx], next[j]] = [next[j], next[idx]];
      onStagesChange(next);
    }
  };

  // Удаление этапа
  const removeStage = async (idx: number) => {
    const s = stages[idx];
    // Нельзя удалять первый этап, финальные и системные
    if (idx === 0 || s.type === 'finalOk' || s.type === 'finalBad' || s.type === 'system') return;

    if (editMode && vacancyId && deleteStageMutation && s.stage_key) {
      setStageError(null);
      try {
        await deleteStageMutation.mutateAsync({
          vacancyId,
          stageKey: s.stage_key
        });
      } catch (error: any) {
        const e = error as ApiError;
        setStageError(e.error?.message || 'Ошибка при удалении этапа');
      }
    } else {
      // В create-режиме локальная мутация
      onStagesChange(stages.filter((_, i) => i !== idx));
    }
  };

  // Добавление этапа
  const addStage = async () => {
    if (editMode && vacancyId && addStageMutation) {
      // В edit-режиме создаём через API
      setStageError(null);
      const stageKey = `stage_${Date.now()}`;
      const orderIndex = stages.length - 2; // Перед финальными

      try {
        await addStageMutation.mutateAsync({
          vacancyId,
          data: {
            stage_key: stageKey,
            label: 'Новый этап',
            order_index: orderIndex,
            is_terminal: false
          }
        });
      } catch (error: any) {
        const e = error as ApiError;
        setStageError(e.error?.message || 'Ошибка при добавлении этапа');
      }
    } else {
      // В create-режиме локальная мутация
      const newStage: Stage = {
        id: Date.now(),
        name: 'Новый этап',
        type: 'middle',
        desc: 'Опишите, что происходит на этом этапе.',
      };
      // Вставляем перед двумя последними финальными
      const idx = stages.length - 2;
      const next = stages.slice();
      next.splice(idx, 0, newStage);
      onStagesChange(next);
    }
  };

  // Изменение названия этапа — локальный апдейт (ввод работает в обоих режимах)
  const updateStageName = (idx: number, name: string) => {
    const next = stages.slice();
    next[idx] = { ...next[idx], name };
    onStagesChange(next);
  };

  // Зафиксировать переименование на сервере (edit-режим) — по blur и только если реально изменилось
  const commitStageName = async (idx: number, name: string) => {
    if (!editMode || !vacancyId || !renameStageMutation) return;
    const stage = stages[idx];
    if (!stage.stage_key) return;
    const trimmed = name.trim().substring(0, 60); // ограничение бэка ≤60
    if (!trimmed || trimmed === renameBaseline.current[stage.stage_key]) return;
    setStageError(null);
    try {
      await renameStageMutation.mutateAsync({
        vacancyId,
        stageKey: stage.stage_key,
        data: { label: trimmed }
      });
    } catch (error: any) {
      const e = error as ApiError;
      setStageError(e.error?.message || 'Ошибка при изменении названия этапа');
    }
  };

  // Описание этапа — локальный апдейт (работает в обоих режимах)
  const updateStageDesc = (idx: number, desc: string) => {
    const next = stages.slice();
    next[idx] = { ...next[idx], desc };
    onStagesChange(next);
  };

  // Зафиксировать описание на сервере (edit-режим) — по blur, только если реально изменилось.
  // Шлём вместе с текущим label (PATCH требует label); stage_key неизменен.
  const commitStageDesc = async (idx: number, desc: string) => {
    if (!editMode || !vacancyId || !renameStageMutation) return;
    const stage = stages[idx];
    if (!stage.stage_key) return;
    if (desc === descBaseline.current[stage.stage_key]) return;
    setStageError(null);
    try {
      await renameStageMutation.mutateAsync({
        vacancyId,
        stageKey: stage.stage_key,
        data: { label: stage.name.trim().substring(0, 60), description: desc.trim() || null }
      });
    } catch (error: any) {
      const e = error as ApiError;
      setStageError(e.error?.message || 'Ошибка при сохранении описания этапа');
    }
  };

  // Проверка блокировки удаления
  const getDeleteDisabledReason = (stage: Stage, idx: number): string | null => {
    if (idx === 0) return 'Первый этап нельзя удалить';
    if (stage.type === 'finalOk' || stage.type === 'finalBad') return 'Финальный этап нельзя удалить';
    if (stage.type === 'system') return 'Системный этап нельзя удалить';
    if (editMode && stage.stage_key && PROTECTED_STAGE_KEYS.has(stage.stage_key)) return 'Системный этап нельзя удалить';
    if (editMode && stage.count && stage.count > 0) return 'Переместите кандидатов с этапа перед удалением';
    return null;
  };

  // Проверка блокировки переименования
  const getRenameDisabledReason = (stage: Stage): string | null => {
    if (stage.type === 'system') return 'Системный этап нельзя переименовать';
    if (editMode && stage.stage_key && PROTECTED_STAGE_KEYS.has(stage.stage_key)) return 'Системный этап нельзя переименовать';
    return null;
  };

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Воронка подбора</div>
      <div className="nv-h2">Этапы, по которым пойдёт кандидат. По умолчанию — шаблон из настроек. Можно переставлять и добавлять — кроме первого и двух последних финальных этапов.</div>

      <div className="nv-banner">
        <Icon name="sparkle" size={16} />
        <div>
          <b>Совет.</b> Чем короче воронка, тем быстрее закрытие. Для массового подбора достаточно 3-4 этапов.
        </div>
      </div>

      {!editMode && (
        <div className="nv-field">
          <label className="nv-label">Шаблон воронки</label>
          <div className="funnel-templates">
            {templateOptions.map(opt => (
              <label key={opt.id} className="funnel-template">
                <input
                  type="radio"
                  name="funnel_template"
                  value={opt.id}
                  checked={data.funnel_template === opt.id}
                  onChange={() => applyTemplate(opt)}
                />
                <span className="funnel-template-name">{opt.name}</span>
              </label>
            ))}
          </div>
        </div>
      )}

      {stageError && (
        <div className="error-banner" role="alert">{stageError}</div>
      )}

      <div className="funnel-editor">
        {stages.map((s, idx) => {
          const t = FUNNEL_STAGE_TYPES[s.type] || { label: 'Промежуточный', dot: '#9AA3AE', bg: '#ECEFF2', fg: '#3A4452' };
          const isFinal = s.type === 'finalOk' || s.type === 'finalBad';
          const isFirst = idx === 0;
          const isSystem = s.type === 'system';
          const locked = isFirst || isFinal || isSystem;

          // Блокировки для edit-режима
          const deleteReason = getDeleteDisabledReason(s, idx);
          const renameReason = getRenameDisabledReason(s);
          const deleteDisabled = deleteReason !== null;
          const renameDisabled = renameReason !== null;

          return (
            <div key={s.stage_key || s.id} className={`fn-stage ${isFinal ? 'fn-final' : ''}`}>
              <div className="nv-fn-arrows">
                <button
                  className="nv-fn-arr"
                  disabled={locked || idx <= 1}
                  title={locked ? 'Этап зафиксирован' : 'Выше'}
                  onClick={() => moveStage(idx, -1)}
                >
                  ▲
                </button>
                <button
                  className="nv-fn-arr"
                  disabled={locked || idx >= stages.length - 3}
                  title={locked ? 'Этап зафиксирован' : 'Ниже'}
                  onClick={() => moveStage(idx, 1)}
                >
                  ▼
                </button>
              </div>
              <div className="fn-num">{idx + 1}</div>
              <div className="fn-body">
                <div className="fn-row1">
                  <input
                    className="fn-name"
                    value={s.name}
                    onFocus={(e) => { if (s.stage_key) renameBaseline.current[s.stage_key] = e.target.value; }}
                    onChange={(e) => updateStageName(idx, e.target.value)}
                    onBlur={(e) => commitStageName(idx, e.target.value)}
                    disabled={renameDisabled}
                    title={renameDisabled ? renameReason || undefined : undefined}
                  />
                  <span className="stage-type-pill" style={{ background: t.bg, color: t.fg }}>
                    <span className="st-dot" style={{ background: t.dot }} />
                    {t.label}
                  </span>
                  {editMode && typeof s.count === 'number' && (
                    <span className="stage-count-badge" title="Кандидатов на этапе">
                      {s.count}
                    </span>
                  )}
                  {(locked || renameDisabled) && (
                    <span className="nv-locked-pill" title={renameDisabled ? renameReason || 'Заблокирован' : 'Зафиксирован'}>
                      <Icon name="lock" size={11} /> закреплён
                    </span>
                  )}
                </div>
                <textarea
                  className="fn-desc-input"
                  value={s.desc}
                  placeholder="Что происходит на этапе: инструкции рекрутеру, суть тестового, чек-лист интервью…"
                  rows={2}
                  onFocus={(e) => { if (s.stage_key) descBaseline.current[s.stage_key] = e.target.value; }}
                  onChange={(e) => updateStageDesc(idx, e.target.value)}
                  onBlur={(e) => commitStageDesc(idx, e.target.value)}
                />
              </div>
              <button
                className="row-icon-btn"
                disabled={deleteDisabled}
                onClick={() => removeStage(idx)}
                title={deleteDisabled ? deleteReason || 'Этап нельзя удалить' : 'Удалить этап'}
              >
                <Icon name="x" size={14} />
              </button>
            </div>
          );
        })}
        <button className="fn-add" onClick={addStage}>
          <Icon name="plus" size={14} /> Добавить этап
        </button>
      </div>

      <RejectReasonsEditor
        reasons={rejectReasons}
        onChange={onRejectReasonsChange}
        editMode={editMode}
        vacancyId={vacancyId}
      />
    </div>
  );
}

function RejectReasonsEditor({
  reasons,
  onChange,
  editMode,
  vacancyId,
}: {
  reasons: RejectReasonLocal[];
  onChange: (reasons: RejectReasonLocal[]) => void;
  editMode: boolean;
  vacancyId?: string;
}) {
  // edit-режим: причины грузятся/правятся через API вакансии; create-режим: локальный набор.
  const { data: vacancyReasons } = useVacancyRejectReasons(editMode ? vacancyId : undefined);
  const addMut = useAddVacancyRejectReason(vacancyId || '');
  const updMut = useUpdateVacancyRejectReason(vacancyId || '');
  const delMut = useDeleteVacancyRejectReason(vacancyId || '');

  const list: RejectReasonLocal[] = editMode
    ? (vacancyReasons || []).map(r => ({
        key: r.id,
        id: r.id,
        side: r.side === 'company' ? 'company' : 'candidate',
        label: r.label,
        order_index: r.order_index ?? 0,
        is_system: !!(r as RejectReasonOut).is_system,
      }))
    : reasons;

  const handleAdd = (side: 'candidate' | 'company') => {
    const count = list.filter(r => r.side === side).length;
    if (editMode) {
      if (vacancyId) addMut.mutate({ side, label: 'Новая причина', order_index: count });
    } else {
      onChange([...reasons, { key: `n${rrKeyCounter++}`, side, label: 'Новая причина', order_index: count, is_system: false }]);
    }
  };

  const handleRename = (item: RejectReasonLocal, raw: string) => {
    const label = raw.trim().substring(0, 120);
    if (!label || label === item.label) return;
    if (editMode) {
      if (vacancyId && item.id) updMut.mutate({ id: item.id, label });
    } else {
      onChange(reasons.map(r => (r.key === item.key ? { ...r, label } : r)));
    }
  };

  const handleDelete = (item: RejectReasonLocal) => {
    if (item.is_system) return;
    if (editMode) {
      if (vacancyId && item.id) delMut.mutate(item.id);
    } else {
      onChange(reasons.filter(r => r.key !== item.key));
    }
  };

  const renderGroup = (side: 'candidate' | 'company', title: string) => (
    <div className="nv-rr-group">
      <div className="nv-rr-title">{title}</div>
      <div className="nv-rr-chips">
        {list.filter(r => r.side === side).map(item => (
          <span key={item.key} className="nv-rr-chip">
            <span className={`nv-rr-dot ${side === 'company' ? 'co' : ''}`} />
            <input
              className="nv-rr-input"
              defaultValue={item.label}
              key={`${item.key}-${item.label}`}
              size={Math.max(item.label.length, 4)}
              onBlur={(e) => handleRename(item, e.target.value)}
            />
            {item.is_system ? (
              <span className="nv-rr-lock" title="Системная причина — нельзя удалить">
                <Icon name="lock" size={11} />
              </span>
            ) : (
              <button className="nv-rr-x" aria-label="Удалить" onClick={() => handleDelete(item)}>
                <Icon name="x" size={11} />
              </button>
            )}
          </span>
        ))}
        <button className="nv-rr-add" onClick={() => handleAdd(side)}>
          <Icon name="plus" size={12} /> Добавить
        </button>
      </div>
    </div>
  );

  return (
    <div className="nv-rr">
      <div className="nv-rr-head">Причины отказа</div>
      <div className="nv-rr-sub">
        Появятся при отклонении кандидата в этой вакансии. По умолчанию — из Настроек, можно изменить.
        Системную (с замком) удалить нельзя.
      </div>
      <div className="nv-rr-grid">
        {renderGroup('candidate', 'От кандидата')}
        {renderGroup('company', 'Со стороны компании')}
      </div>
    </div>
  );
}

function TeamStep({
  data,
  onChange,
  users,
}: {
  data: VacancyCreate;
  onChange: (updates: Partial<VacancyCreate>) => void;
  users: any[];
}) {
  const [query, setQuery] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');

  const filtered = users.filter(u => {
    if (roleFilter === 'rec' && !u.role?.toLowerCase().includes('рекрут')) return false;
    if (roleFilter === 'mgr' && !u.role?.toLowerCase().includes('менеджер')) return false;
    if (query && !`${u.full_name} ${u.email} ${u.department || ''}`.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  const toggle = (uid: string) => {
    if (data.team.includes(uid)) onChange({ team: data.team.filter(x => x !== uid) });
    else onChange({ team: [...data.team, uid] });
  };

  const owner = data.team[0];

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Команда вакансии</div>
      <div className="nv-h2">Кто видит вакансию, ведёт кандидатов и принимает решения. Первый добавленный — ответственный рекрутер.</div>

      <div className="nv-team-toolbar">
        <div className="nv-search">
          <Icon name="search" size={14} style={{ color: 'var(--fg-3)' }} />
          <input placeholder="Поиск по имени, email или отделу…"
                 value={query} onChange={e => setQuery(e.target.value)} />
        </div>
        <div className="seg-sm">
          <button className={roleFilter === 'all' ? 'active' : ''} onClick={() => setRoleFilter('all')}>Все</button>
          <button className={roleFilter === 'rec' ? 'active' : ''} onClick={() => setRoleFilter('rec')}>Рекрутеры</button>
          <button className={roleFilter === 'mgr' ? 'active' : ''} onClick={() => setRoleFilter('mgr')}>Менеджеры</button>
        </div>
      </div>

      {data.team.length > 0 && (
        <div className="nv-team-selected">
          <div className="nv-team-selhead">Выбраны · {data.team.length}</div>
          <div className="nv-team-chips">
            {data.team.map(uid => {
              const u = users.find(x => x.id === uid);
              if (!u) return null;
              return (
                <div key={uid} className={`nv-team-chip ${uid === owner ? 'owner' : ''}`}>
                  <Avatar name={u.full_name} size="sm" />
                  <div className="nv-tc-text">
                    <div className="nv-tc-name">{u.full_name}{uid === owner && <span className="nv-owner-badge">владелец</span>}</div>
                    <div className="nv-tc-role">{u.role}</div>
                  </div>
                  <button className="nv-tc-x" onClick={() => toggle(uid)}><Icon name="x" size={12} /></button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="nv-user-list">
        {filtered.length === 0 ? (
          <div className="nv-empty">Никого не найдено по запросу «{query}».</div>
        ) : filtered.map(u => {
          const on = data.team.includes(u.id);
          return (
            <div key={u.id} className={`nv-user-row ${on ? 'on' : ''}`} onClick={() => toggle(u.id)}>
              <span className={`nv-check ${on ? 'on' : ''}`}>{on && <Icon name="check" size={11} />}</span>
              <Avatar name={u.full_name} size="md" />
              <div className="nv-ur-text">
                <div className="nv-ur-name">{u.full_name}</div>
                <div className="nv-ur-meta">{u.role} <span className="sep">·</span> {u.department || 'Без отдела'}</div>
              </div>
              <div className="nv-ur-email">{u.email}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AutomationStep({
  editMode = false,
  vacancyId,
  vacancy,
  formData,
  onChange,
  autoStages = [],
  autoSourceStages = [],
}: {
  editMode?: boolean;
  vacancyId?: string;
  vacancy?: any;
  formData: any;
  onChange: (updates: any) => void;
  autoStages?: { key: string; name: string }[];
  autoSourceStages?: { key: string; name: string }[];
}) {
  // Текст по умолчанию для префилла текстареа отказа: текст компании из Настроек,
  // иначе встроенный вежливый текст (зеркало backend).
  const { data: glafiraSettings } = useGlafiraSettings();
  const defaultRejectionText =
    (glafiraSettings?.default_rejection_text?.trim() || '') || POLITE_REJECTION_FALLBACK;
  // Шаблоны сообщений (Настройки) — для режима «определённые вопросы»: вставка готового текста.
  const { data: msgTemplatesData } = useMessageTemplates();
  const msgTemplates = msgTemplatesData ?? [];

  // Целевой этап автоперевода (П.1) — выбор из НЕ начальных/конечных этапов воронки.
  // Эффективное значение валидируем по доступным; нормализуем на первый, если выбранного нет.
  const autoMoveValue = autoStages.some((s) => s.key === formData.auto_move_stage)
    ? formData.auto_move_stage
    : (autoStages[0]?.key ?? 'selected');
  const autoKeys = autoStages.map((s) => s.key).join(',');
  useEffect(() => {
    if (
      formData.auto_move &&
      autoStages.length > 0 &&
      !autoStages.some((s) => s.key === formData.auto_move_stage)
    ) {
      onChange({ auto_move_stage: autoStages[0].key });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData.auto_move, formData.auto_move_stage, autoKeys]);

  // П.2 — исходный этап (любой НЕ терминальный, дефолт 'response') и целевой
  // (middle, как П.1, дефолт 'selected'). Та же нормализация на валидное значение.
  const autoQaSourceValue = autoSourceStages.some((s) => s.key === formData.auto_qa_stage)
    ? formData.auto_qa_stage
    : (autoSourceStages[0]?.key ?? 'response');
  const autoQaTargetValue = autoStages.some((s) => s.key === formData.auto_qa_target_stage)
    ? formData.auto_qa_target_stage
    : (autoStages[0]?.key ?? 'selected');
  const autoSourceKeys = autoSourceStages.map((s) => s.key).join(',');
  useEffect(() => {
    if (
      formData.auto_qa &&
      autoSourceStages.length > 0 &&
      !autoSourceStages.some((s) => s.key === formData.auto_qa_stage)
    ) {
      onChange({ auto_qa_stage: autoSourceStages[0].key });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData.auto_qa, formData.auto_qa_stage, autoSourceKeys]);
  useEffect(() => {
    if (
      formData.auto_qa &&
      autoStages.length > 0 &&
      !autoStages.some((s) => s.key === formData.auto_qa_target_stage)
    ) {
      onChange({ auto_qa_target_stage: autoStages[0].key });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData.auto_qa, formData.auto_qa_target_stage, autoKeys]);

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Автоматизация</div>
      <div className="nv-h2">Глафира будет действовать сама — переводить кандидатов, задавать уточняющие вопросы и закрывать карточки. Включайте по необходимости.</div>

      {/* П.1: Автоперевод по AI-скорингу (РАБОЧИЙ) */}
      <div className={`nv-auto-block ${formData.auto_move ? 'on' : 'off'}`}>
        <div className="nv-auto-head" onClick={() => onChange({ auto_move: !formData.auto_move })}>
          <span className={`nv-cb ${formData.auto_move ? 'on' : ''}`}>
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Автоматический перевод по AI-скорингу</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-inline">
            <span>Автоматически переводить на этап</span>
            <select
              className="nv-input"
              value={autoMoveValue}
              onChange={(e) => onChange({ auto_move_stage: e.target.value })}
              disabled={!formData.auto_move}
              style={{ height: '30px', borderRadius: '6px', fontSize: '13px', width: 'auto', padding: '0 8px' }}
            >
              {autoStages.length === 0 ? (
                <option value="">нет доступных этапов</option>
              ) : (
                autoStages.map((s) => (
                  <option key={s.key} value={s.key}>{s.name}</option>
                ))
              )}
            </select>
            <span>при скоринге AI &gt;</span>
            <input
              className="nv-num-input"
              type="number"
              min="0"
              max="100"
              value={formData.auto_move_threshold}
              onChange={(e) => onChange({ auto_move_threshold: parseInt(e.target.value) || 80 })}
              disabled={!formData.auto_move}
            />
            <span className="nv-mute">из 100</span>
          </div>
          <div className="nv-auto-hint">
            <Icon name="sparkle" size={12} />
            Глафира двигает только уверенных кандидатов.
          </div>
        </div>
      </div>

      {/* П.2: Уточняющие вопросы + автоперевод (РАБОЧЕЕ; только hh-кандидаты) */}
      <div className={`nv-auto-block ${formData.auto_qa ? 'on' : 'off'}`}>
        <div className="nv-auto-head" onClick={() => onChange({ auto_qa: !formData.auto_qa })}>
          <span className={`nv-cb ${formData.auto_qa ? 'on' : ''}`}>
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Уточняющие вопросы и автоперевод</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-inline">
            <span>Если карточка на этапе</span>
            <select
              className="nv-input"
              value={autoQaSourceValue}
              onChange={(e) => onChange({ auto_qa_stage: e.target.value })}
              disabled={!formData.auto_qa}
              style={{ height: '30px', borderRadius: '6px', fontSize: '13px', width: 'auto', padding: '0 8px' }}
            >
              {autoSourceStages.length === 0 ? (
                <option value="">нет этапов</option>
              ) : (
                autoSourceStages.map((s) => (
                  <option key={s.key} value={s.key}>{s.name}</option>
                ))
              )}
            </select>
            <span>— Глафира задаёт кандидату уточняющие вопросы и переводит в</span>
            <select
              className="nv-input"
              value={autoQaTargetValue}
              onChange={(e) => onChange({ auto_qa_target_stage: e.target.value })}
              disabled={!formData.auto_qa}
              style={{ height: '30px', borderRadius: '6px', fontSize: '13px', width: 'auto', padding: '0 8px' }}
            >
              {autoStages.length === 0 ? (
                <option value="">нет этапов</option>
              ) : (
                autoStages.map((s) => (
                  <option key={s.key} value={s.key}>{s.name}</option>
                ))
              )}
            </select>
            <span>по ответам.</span>
          </div>

          {/* Развилка: какие вопросы задавать */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', margin: '10px 0 0' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
              <input
                type="radio"
                name="auto_qa_mode"
                value="weak"
                checked={(formData.auto_qa_mode || 'weak') === 'weak'}
                onChange={() => onChange({ auto_qa_mode: 'weak' })}
                disabled={!formData.auto_qa}
              />
              <span>По слабым сторонам резюме <span className="nv-mute">— Глафира сама подбирает вопросы из оценки</span></span>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
              <input
                type="radio"
                name="auto_qa_mode"
                value="fixed"
                checked={formData.auto_qa_mode === 'fixed'}
                onChange={() => onChange({ auto_qa_mode: 'fixed' })}
                disabled={!formData.auto_qa}
              />
              <span>Определённые вопросы <span className="nv-mute">— всегда одни и те же</span></span>
            </label>
          </div>

          {formData.auto_qa_mode === 'fixed' && (
            <div style={{ margin: '8px 0 0', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <RichTextField
                value={formData.auto_qa_fixed_text || ''}
                onChange={(html) => onChange({ auto_qa_fixed_text: html })}
                placeholder={"Напишите вопросы кандидату — отправятся как есть, всегда одни и те же…"}
                minHeight={120}
              />
              {msgTemplates.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="nv-mute">Вставить из шаблона:</span>
                  <select
                    className="nv-input"
                    value=""
                    onChange={(e) => {
                      const t = msgTemplates.find((x) => x.id === e.target.value);
                      // Шаблон — плоский текст; переносы → <br>, чтобы отобразились в rich-редакторе
                      // (на отправке _strip_html вернёт их в переносы строк).
                      if (t) onChange({ auto_qa_fixed_text: t.body.replace(/\n/g, '<br>') });
                    }}
                    disabled={!formData.auto_qa}
                    style={{ height: '30px', borderRadius: '6px', fontSize: '13px', width: 'auto', padding: '0 8px' }}
                  >
                    <option value="">— шаблон —</option>
                    {msgTemplates.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          )}

          <div className="nv-auto-hint">
            <Icon name="sparkle" size={12} />
            Только для откликов с hh.ru (через переписку). Вопросы задаются один раз. В режиме «Под контролем» не работает.
          </div>
        </div>
      </div>

      {/* П.3: Автоотказ при неинтересе (РАБОЧЕЕ; полный отказ только в режиме «Автомат») */}
      <div className={`nv-auto-block ${formData.auto_reject ? 'on' : 'off'}`}>
        <div className="nv-auto-head" onClick={() => onChange({ auto_reject: !formData.auto_reject })}>
          <span className={`nv-cb ${formData.auto_reject ? 'on' : ''}`}>
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Автоматический отказ при неинтересе</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-text">
            Если Глафира по диалогу понимает, что вакансия кандидату <b>не интересна</b> или он <b>принял другой оффер</b>, она переведёт его в «Отказ» с причиной из справочника и отправит текст отказа.
          </div>
          <div className="nv-reasons-row">
            <span className="nv-reason-pill"><span className="nv-rp-dot grey" />Не интересно</span>
            <span className="nv-reason-pill"><span className="nv-rp-dot grey" />Принял оффер</span>
          </div>
          <div className="nv-auto-hint">
            <Icon name="sparkle" size={12} />
            Отказ необратим, поэтому срабатывает только при явной незаинтересованности и высокой уверенности. Полный автоотказ — лишь в режиме «Автомат»; в «Полуавтомате» Глафира только помечает карточку подсказкой рекрутёру. В режиме «Под контролем» не работает.
          </div>
        </div>
      </div>

      {/* П.4: Авто-сообщение при отказе + текст отказа для вакансии (РАБОЧИЙ) */}
      <div className={`nv-auto-block ${formData.auto_reject_message ? 'on' : 'off'}`}>
        <div className="nv-auto-head" onClick={() => onChange({ auto_reject_message: !formData.auto_reject_message })}>
          <span className={`nv-cb ${formData.auto_reject_message ? 'on' : ''}`}>
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Автоматически писать кандидату при переводе в отказ</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-hint">
            <Icon name="sparkle" size={12} />
            Вежливое сообщение при отказе поднимает рейтинг «вежливости» компании на hh.ru. Отправляется только для откликов с hh.ru; сам отказ на hh идёт в любом случае.
          </div>
          <textarea
            className="nv-textarea"
            placeholder="Текст сообщения кандидату при отказе"
            value={formData.rejection_text ?? (formData.auto_reject_message ? defaultRejectionText : '')}
            onChange={(e) => onChange({ rejection_text: e.target.value || null })}
            disabled={!formData.auto_reject_message}
            rows={4}
            style={{
              width: '100%',
              resize: 'vertical',
              minHeight: '80px'
            }}
          />
        </div>
      </div>

      <HhPublicationBlock editMode={editMode} vacancyId={vacancyId} vacancy={vacancy} />
      <HabrPublicationBlock editMode={editMode} vacancyId={vacancyId} vacancy={vacancy} />
      <AvitoPublicationBlock editMode={editMode} vacancyId={vacancyId} vacancy={vacancy} />
    </div>
  );
}

function HhPublicationBlock({ editMode, vacancyId, vacancy }: { editMode: boolean; vacancyId?: string; vacancy?: any }) {
  const [hhError, setHhError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const { data: hhStatus, isLoading: hhStatusLoading } = useHhStatus();
  const { data: hhVacancies, isLoading: hhVacanciesLoading } = useHhVacancies(hhStatus?.connected && editMode && !!vacancyId);

  const hhLinkMutation = useHhLinkVacancy();
  const hhUnlinkMutation = useHhUnlinkVacancy();
  const hhPublishMutation = useHhPublishVacancy();

  const [selectedHhVacancyId, setSelectedHhVacancyId] = useState('');

  const isConnected = hhStatus?.connected;
  const isLinked = vacancy && vacancy.hh_vacancy_id;
  const canManage = editMode && vacancyId; // Вакансия сохранена

  const handleLink = async () => {
    if (!selectedHhVacancyId || !vacancyId) return;
    setHhError(null);
    try {
      await hhLinkMutation.mutateAsync({ vacancyId, hhVacancyId: selectedHhVacancyId });
      setSuccessMessage('Вакансия успешно привязана к hh.ru');
      setSelectedHhVacancyId('');
    } catch (error) {
      const e = error as unknown as ApiError;
      setHhError(e.error?.message || 'Ошибка при привязке к hh.ru');
    }
  };

  const handleUnlink = async () => {
    if (!vacancyId) return;
    setHhError(null);
    try {
      await hhUnlinkMutation.mutateAsync(vacancyId);
      setSuccessMessage('Вакансия отвязана от hh.ru');
    } catch (error) {
      const e = error as unknown as ApiError;
      setHhError(e.error?.message || 'Ошибка при отвязке от hh.ru');
    }
  };

  const handlePublish = async () => {
    if (!vacancyId) return;
    setHhError(null);
    try {
      const result = await hhPublishMutation.mutateAsync(vacancyId);
      setSuccessMessage(`Вакансия создана на hh.ru с ID: ${result.hh_vacancy_id}`);
    } catch (error) {
      const e = error as unknown as ApiError;
      setHhError(e.error?.message || 'Ошибка при создании вакансии на hh.ru');
    }
  };

  return (
    <div className="nv-hh-block">
      <div className="nv-h3" style={{ marginBottom: '8px', marginTop: '24px' }}>Публикация на hh.ru</div>

      {hhError && (
        <div className="error-banner" role="alert" style={{ marginBottom: '12px' }}>
          {hhError}
        </div>
      )}

      {successMessage && (
        <div className="info-banner" style={{
          marginBottom: '12px',
          background: 'var(--success-bg)',
          borderColor: 'var(--success-border)',
          color: 'var(--success-fg)'
        }}>
          <Icon name="check" size={16} />
          <div>{successMessage}</div>
        </div>
      )}

      {hhStatusLoading ? (
        <div style={{ padding: '16px', color: 'var(--fg-3)', textAlign: 'center' }}>
          Загрузка статуса hh.ru...
        </div>
      ) : !isConnected ? (
        <div className="nv-hh-disabled">
          <Icon name="x" size={16} style={{ color: 'var(--fg-3)' }} />
          <div>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '4px' }}>
              hh.ru не подключён
            </div>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>
              Подключите hh.ru в <a href="/settings?tab=integrations" style={{ color: 'var(--accent)' }}>Настройках → Интеграции</a>
            </div>
          </div>
        </div>
      ) : !canManage ? (
        <div className="nv-hh-disabled">
          <Icon name="lock" size={16} style={{ color: 'var(--fg-3)' }} />
          <div>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '4px' }}>
              Сначала сохраните вакансию
            </div>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>
              Привязка к hh.ru доступна только для сохранённых вакансий
            </div>
          </div>
        </div>
      ) : isLinked ? (
        <div className="nv-hh-linked">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Icon name="link" size={16} style={{ color: 'var(--success-fg)' }} />
            <div>
              <div style={{ fontSize: '13px', color: 'var(--fg-2)' }}>
                <strong>Привязана к hh:</strong> {vacancy.hh_vacancy_id}
              </div>
            </div>
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleUnlink}
            disabled={hhUnlinkMutation.isPending}
          >
            {hhUnlinkMutation.isPending ? 'Отвязка...' : 'Отвязать'}
          </button>
        </div>
      ) : (
        <div className="nv-hh-controls">
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--fg-2)', marginBottom: '8px' }}>
              Привязать к существующей вакансии на hh.ru
            </label>
            {hhVacanciesLoading ? (
              <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>Загрузка вакансий...</div>
            ) : (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <select
                  value={selectedHhVacancyId}
                  onChange={(e) => setSelectedHhVacancyId(e.target.value)}
                  style={{
                    minWidth: '200px',
                    padding: '6px 8px',
                    fontSize: '13px',
                    border: '1px solid var(--border-1)',
                    borderRadius: '6px',
                    background: 'var(--bg-1)'
                  }}
                >
                  <option value="">Выберите вакансию...</option>
                  {hhVacancies?.map(hv => (
                    <option key={hv.id} value={hv.id}>
                      {hv.name} {hv.area ? `(${hv.area})` : ''}
                    </option>
                  ))}
                </select>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleLink}
                  disabled={!selectedHhVacancyId || hhLinkMutation.isPending}
                >
                  {hhLinkMutation.isPending ? 'Привязка...' : 'Привязать'}
                </button>
              </div>
            )}
          </div>

          <div style={{ borderTop: '1px solid var(--border-2)', paddingTop: '16px' }}>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '8px' }}>
              Или создать новую вакансию на hh.ru
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={handlePublish}
              disabled={hhPublishMutation.isPending}
            >
              {hhPublishMutation.isPending ? 'Создание...' : 'Создать на hh.ru'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function HabrPublicationBlock({ editMode, vacancyId, vacancy }: { editMode: boolean; vacancyId?: string; vacancy?: any }) {
  const [habrError, setHabrError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const { data: habrStatus, isLoading: habrStatusLoading } = useHabrStatus();
  const { data: habrVacancies, isLoading: habrVacanciesLoading, error: habrVacanciesError } = useHabrVacancies(
    !!(habrStatus?.connected && editMode && vacancyId)
  );

  const habrLinkMutation = useHabrLinkVacancy();
  const habrUnlinkMutation = useHabrUnlinkVacancy();

  const [selectedHabrVacancyId, setSelectedHabrVacancyId] = useState('');
  const [manualHabrId, setManualHabrId] = useState('');

  const isConnected = habrStatus?.connected;
  const isLinked = vacancy && vacancy.habr_vacancy_id;
  const canManage = editMode && vacancyId;

  const handleLink = async () => {
    const targetId = selectedHabrVacancyId || manualHabrId.trim();
    if (!targetId || !vacancyId) return;
    setHabrError(null);
    try {
      await habrLinkMutation.mutateAsync({ vacancyId, habrVacancyId: targetId });
      setSuccessMessage('Вакансия успешно привязана к Хабр Карьера');
      setSelectedHabrVacancyId('');
      setManualHabrId('');
    } catch (error) {
      const e = error as unknown as ApiError;
      setHabrError(e.error?.message || 'Ошибка при привязке к Хабр Карьера');
    }
  };

  const handleUnlink = async () => {
    if (!vacancyId) return;
    setHabrError(null);
    try {
      await habrUnlinkMutation.mutateAsync(vacancyId);
      setSuccessMessage('Вакансия отвязана от Хабр Карьера');
    } catch (error) {
      const e = error as unknown as ApiError;
      setHabrError(e.error?.message || 'Ошибка при отвязке от Хабр Карьера');
    }
  };

  return (
    <div className="nv-hh-block">
      <div className="nv-h3" style={{ marginBottom: '8px', marginTop: '24px' }}>Привязка к Хабр Карьера</div>

      {habrError && (
        <div className="error-banner" role="alert" style={{ marginBottom: '12px' }}>
          {habrError}
        </div>
      )}

      {successMessage && (
        <div className="info-banner" style={{
          marginBottom: '12px',
          background: 'var(--success-bg)',
          borderColor: 'var(--success-border)',
          color: 'var(--success-fg)'
        }}>
          <Icon name="check" size={16} />
          <div>{successMessage}</div>
        </div>
      )}

      {habrStatusLoading ? (
        <div style={{ padding: '16px', color: 'var(--fg-3)', textAlign: 'center' }}>
          Загрузка статуса Хабр Карьера...
        </div>
      ) : !isConnected ? (
        <div className="nv-hh-disabled">
          <Icon name="x" size={16} style={{ color: 'var(--fg-3)' }} />
          <div>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '4px' }}>
              Хабр Карьера не подключён
            </div>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>
              Подключите Хабр Карьера в <a href="/settings?tab=integrations" style={{ color: 'var(--accent)' }}>Настройках → Интеграции</a>
            </div>
          </div>
        </div>
      ) : !canManage ? (
        <div className="nv-hh-disabled">
          <Icon name="lock" size={16} style={{ color: 'var(--fg-3)' }} />
          <div>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '4px' }}>
              Сначала сохраните вакансию
            </div>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>
              Привязка к Хабр Карьера доступна только для сохранённых вакансий
            </div>
          </div>
        </div>
      ) : isLinked ? (
        <div className="nv-hh-linked">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Icon name="link" size={16} style={{ color: 'var(--success-fg)' }} />
            <div>
              <div style={{ fontSize: '13px', color: 'var(--fg-2)' }}>
                <strong>Привязана к Хабр Карьера:</strong> {vacancy.habr_vacancy_id}
              </div>
            </div>
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleUnlink}
            disabled={habrUnlinkMutation.isPending}
          >
            {habrUnlinkMutation.isPending ? 'Отвязка...' : 'Отвязать'}
          </button>
        </div>
      ) : (
        <div className="nv-hh-controls">
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--fg-2)', marginBottom: '8px' }}>
              Привязать к вакансии на Хабр Карьера
            </label>
            {habrVacanciesLoading ? (
              <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>Загрузка вакансий...</div>
            ) : habrVacanciesError || !habrVacancies || habrVacancies.length === 0 ? (
              // Список недоступен (эндпоинт-ASSUMPTION, до одобрения приложения Хабром)
              <div>
                <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginBottom: '8px' }}>
                  Список вакансий Хабра недоступен — введите ID вручную
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <input
                    type="text"
                    value={manualHabrId}
                    onChange={(e) => setManualHabrId(e.target.value)}
                    placeholder="ID вакансии на Хабр Карьера"
                    style={{
                      minWidth: '200px',
                      padding: '6px 8px',
                      fontSize: '13px',
                      border: '1px solid var(--border-1)',
                      borderRadius: '6px',
                      background: 'var(--bg-1)',
                      color: 'var(--fg-1)',
                    }}
                  />
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleLink}
                    disabled={!manualHabrId.trim() || habrLinkMutation.isPending}
                  >
                    {habrLinkMutation.isPending ? 'Привязка...' : 'Привязать'}
                  </button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <select
                  value={selectedHabrVacancyId}
                  onChange={(e) => setSelectedHabrVacancyId(e.target.value)}
                  style={{
                    minWidth: '200px',
                    padding: '6px 8px',
                    fontSize: '13px',
                    border: '1px solid var(--border-1)',
                    borderRadius: '6px',
                    background: 'var(--bg-1)',
                    color: 'var(--fg-1)',
                  }}
                >
                  <option value="">Выберите вакансию...</option>
                  {habrVacancies.map(hv => (
                    <option key={hv.id} value={hv.id}>
                      {hv.title} {hv.city ? `(${hv.city})` : ''}
                    </option>
                  ))}
                </select>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={handleLink}
                  disabled={!selectedHabrVacancyId || habrLinkMutation.isPending}
                >
                  {habrLinkMutation.isPending ? 'Привязка...' : 'Привязать'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function AvitoPublicationBlock({ editMode, vacancyId, vacancy }: { editMode: boolean; vacancyId?: string; vacancy?: any }) {
  const [avitoError, setAvitoError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [manualAvitoId, setManualAvitoId] = useState('');

  const { data: avitoStatus, isLoading: avitoStatusLoading } = useAvitoStatus();
  const avitoLinkMutation = useAvitoLinkVacancy();
  const avitoUnlinkMutation = useAvitoUnlinkVacancy();

  const isConnected = avitoStatus?.connected;
  // avito_vacancy_id может прийти как новое поле (openapi отстаёт, читаем через any)
  const isLinked = vacancy && (vacancy as any).avito_vacancy_id;
  const canManage = editMode && vacancyId;

  const handleLink = async () => {
    const targetId = manualAvitoId.trim();
    if (!targetId || !vacancyId) return;
    setAvitoError(null);
    try {
      await avitoLinkMutation.mutateAsync({ vacancyId, avitoVacancyId: targetId });
      setSuccessMessage('Вакансия успешно привязана к Авито Работа');
      setManualAvitoId('');
    } catch (error) {
      const e = error as unknown as ApiError;
      setAvitoError(e.error?.message || 'Ошибка при привязке к Авито Работа');
    }
  };

  const handleUnlink = async () => {
    if (!vacancyId) return;
    setAvitoError(null);
    try {
      await avitoUnlinkMutation.mutateAsync(vacancyId);
      setSuccessMessage('Вакансия отвязана от Авито Работа');
    } catch (error) {
      const e = error as unknown as ApiError;
      setAvitoError(e.error?.message || 'Ошибка при отвязке от Авито Работа');
    }
  };

  return (
    <div className="nv-hh-block">
      <div className="nv-h3" style={{ marginBottom: '8px', marginTop: '24px' }}>Привязка к Авито Работа</div>

      {avitoError && (
        <div className="error-banner" role="alert" style={{ marginBottom: '12px' }}>
          {avitoError}
        </div>
      )}

      {successMessage && (
        <div className="info-banner" style={{
          marginBottom: '12px',
          background: 'var(--success-bg)',
          borderColor: 'var(--success-border)',
          color: 'var(--success-fg)'
        }}>
          <Icon name="check" size={16} />
          <div>{successMessage}</div>
        </div>
      )}

      {avitoStatusLoading ? (
        <div style={{ padding: '16px', color: 'var(--fg-3)', textAlign: 'center' }}>
          Загрузка статуса Авито Работа...
        </div>
      ) : !isConnected ? (
        <div className="nv-hh-disabled">
          <Icon name="x" size={16} style={{ color: 'var(--fg-3)' }} />
          <div>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '4px' }}>
              Авито Работа не подключена
            </div>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>
              Подключите в <a href="/settings?tab=integrations" style={{ color: 'var(--accent)' }}>Настройках → Интеграции</a>
            </div>
          </div>
        </div>
      ) : !canManage ? (
        <div className="nv-hh-disabled">
          <Icon name="lock" size={16} style={{ color: 'var(--fg-3)' }} />
          <div>
            <div style={{ fontSize: '13px', color: 'var(--fg-2)', marginBottom: '4px' }}>
              Сначала сохраните вакансию
            </div>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)' }}>
              Привязка к Авито доступна только для сохранённых вакансий
            </div>
          </div>
        </div>
      ) : isLinked ? (
        <div className="nv-hh-linked">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Icon name="link" size={16} style={{ color: 'var(--success-fg)' }} />
            <div>
              <div style={{ fontSize: '13px', color: 'var(--fg-2)' }}>
                <strong>Привязана к Авито:</strong> {(vacancy as any).avito_vacancy_id}
              </div>
              <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '2px' }}>
                Телефон кандидата приходит бесплатно — дополнительных действий не нужно
              </div>
            </div>
          </div>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleUnlink}
            disabled={avitoUnlinkMutation.isPending}
          >
            {avitoUnlinkMutation.isPending ? 'Отвязка...' : 'Отвязать'}
          </button>
        </div>
      ) : (
        <div className="nv-hh-controls">
          <div style={{ marginBottom: '16px' }}>
            <label style={{ display: 'block', fontSize: '13px', color: 'var(--fg-2)', marginBottom: '8px' }}>
              Привязать к вакансии на Авито Работа
            </label>
            <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginBottom: '8px' }}>
              Введите числовой ID вакансии (из URL объявления на Авито)
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <input
                type="text"
                value={manualAvitoId}
                onChange={(e) => setManualAvitoId(e.target.value.replace(/[^0-9]/g, ''))}
                placeholder="Например: 123456789"
                style={{
                  minWidth: '200px',
                  padding: '6px 8px',
                  fontSize: '13px',
                  border: '1px solid var(--border-1)',
                  borderRadius: '6px',
                  background: 'var(--bg-1)',
                  color: 'var(--fg-1)',
                  fontFamily: 'var(--font-mono)',
                }}
              />
              <button
                className="btn btn-primary btn-sm"
                onClick={handleLink}
                disabled={!manualAvitoId.trim() || avitoLinkMutation.isPending}
              >
                {avitoLinkMutation.isPending ? 'Привязка...' : 'Привязать'}
              </button>
            </div>
          </div>
          <div className="info-banner small">
            <Icon name="alert-triangle" size={14} />
            <div>
              ID вакансии — цифры из URL объявления на Авито (например: avito.ru/...</div>
          </div>
        </div>
      )}
    </div>
  );
}