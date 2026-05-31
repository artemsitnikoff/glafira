import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './vacancies/VacancyForm.css';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
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
import { useClients } from '@/api/hooks/useClients';
import { useUsers } from '@/api/hooks/useUsers';
import type { components } from '@/api/types';

type VacancyCreate = components['schemas']['VacancyCreate'];
type VacancyUpdate = components['schemas']['VacancyUpdate'];

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
      desc: getStageDescription(s.stage_key, type),
      stage_key: s.stage_key,
    };
  });
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

  const createMutation = useCreateVacancy();
  const updateMutation = useUpdateVacancy();
  const addStageMutation = useAddVacancyStage();
  const renameStageMutation = useRenameVacancyStage();
  const deleteStageMutation = useDeleteVacancyStage();
  const reorderStagesMutation = useReorderVacancyStages();

  const [activeStep, setActiveStep] = useState('desc');
  const [formData, setFormData] = useState<VacancyCreate>({
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
    // Шаг 4 (автоматизация) — заглушка: off-дефолты, бек их игнорит (поля обязательны по типу)
    auto_move: false,
    auto_move_threshold: 80,
    auto_qa_from: null,
    auto_qa_to: null,
    auto_reject: false,
  });

  // Состояние этапов воронки
  const [stages, setStages] = useState<Stage[]>(NV_DEFAULT_STAGES);

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
        auto_move: false,
        auto_move_threshold: 80,
        auto_qa_from: null,
        auto_qa_to: null,
        auto_reject: false,
      });
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
          desc: getStageDescription(vStage.stage_key, type),
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
    try {
      if (editMode && id) {
        const updateData: VacancyUpdate = { ...formData };
        await updateMutation.mutateAsync({ id, data: updateData });
        navigate(`/vacancies/${id}`);
      } else {
        // Генерируем StageInput из stages для отправки на бэк
        const stageInputs: StageInput[] = stages.map((stage, index) => ({
          stage_key: getStageKey(stage),
          label: stage.name.substring(0, 60), // Ограничение бэка: ≤60 симв
          order_index: index,
          is_terminal: stage.type === 'finalOk' || stage.type === 'finalBad',
        }));

        // Добавляем stages в payload с приведением типа
        const payload = {
          ...formData,
          stages: stageInputs,
        } as VacancyCreate & { stages: StageInput[] };

        const result = await createMutation.mutateAsync(payload);
        navigate(`/vacancies/${result.id}`);
      }
    } catch (error) {
      // Удаляем console.log согласно заданию
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

  const updateFormData = (updates: Partial<VacancyCreate>) => {
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
          <button className="btn btn-secondary btn-sm">Сохранить черновик</button>
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
            />
          )}
          {activeStep === 'funnel' && (
            <FunnelStep
              data={formData}
              onChange={updateFormData}
              stages={stages}
              onStagesChange={setStages}
              companyDefaultStages={companyDefaultStages}
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
            <AutomationStep />
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

function DescriptionStep({
  data,
  onChange,
  clients,
}: {
  data: VacancyCreate;
  onChange: (updates: Partial<VacancyCreate>) => void;
  clients: any[];
}) {
  return (
    <div className="nv-step-body">
      <div className="nv-h1">Описание вакансии</div>
      <div className="nv-h2">Базовая информация — название, локация, дата закрытия. Текст требований и обязанностей.</div>

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
          <input
            className="nv-input"
            placeholder="Начните вводить город…"
            value={data.city || ''}
            onChange={e => onChange({ city: e.target.value || null })}
          />
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
        <div className="nv-editor">
          <div className="nv-toolbar">
            {['B', 'I', 'U'].map(t => <button key={t} className="nv-tb-btn" style={{ fontWeight: t === 'B' ? 700 : 500, fontStyle: t === 'I' ? 'italic' : 'normal', textDecoration: t === 'U' ? 'underline' : 'none' }}>{t}</button>)}
            <span className="nv-tb-sep" />
            <button className="nv-tb-btn">••</button>
            <button className="nv-tb-btn">•</button>
            <button className="nv-tb-btn">1.</button>
            <span className="nv-tb-sep" />
            <button className="nv-tb-btn">link</button>
          </div>
          <textarea className="nv-textarea"
            placeholder="Требования:&#10;Обязанности:&#10;Условия работы:"
            value={data.description || ''} onChange={e => onChange({ description: e.target.value || null })} />
        </div>
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

  // Применить выбранный шаблон
  const applyTemplate = (templateId: string) => {
    // В edit-режиме шаблоны не применяем — этапы управляются через API
    if (editMode) return;

    if (templateId === 'default') {
      // «По умолчанию» = воронка из Настроек (company_default_stages). Пусто → хардкод-эталон.
      const base = companyDefaultStages && companyDefaultStages.length > 0
        ? companyDefaultStages
        : NV_DEFAULT_STAGES;
      onStagesChange(base.map(s => ({ ...s })));
    } else {
      const template = FUNNEL_TEMPLATES.find(t => t.id === templateId);
      if (template) {
        onStagesChange(template.stages.map(s => ({ ...s }))); // Копируем (глубоко по этапам)
      }
    }
    onChange({ funnel_template: templateId });
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
        setStageError(error.response?.data?.error?.message || 'Ошибка при изменении порядка этапов');
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
        setStageError(error.response?.data?.error?.message || 'Ошибка при удалении этапа');
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
        setStageError(error.response?.data?.error?.message || 'Ошибка при добавлении этапа');
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
      setStageError(error.response?.data?.error?.message || 'Ошибка при изменении названия этапа');
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
            {FUNNEL_TEMPLATES.map(template => (
              <label key={template.id} className="funnel-template">
                <input
                  type="radio"
                  name="funnel_template"
                  value={template.id}
                  checked={data.funnel_template === template.id}
                  onChange={e => applyTemplate(e.target.value)}
                />
                <span className="funnel-template-name">{template.name}</span>
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
                <div className="fn-desc">{s.desc}</div>
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

function AutomationStep() {
  return (
    <div className="nv-step-body">
      <div className="nv-h1">Автоматизация</div>
      <div className="nv-h2">Глафира будет действовать сама — переводить кандидатов, задавать уточняющие вопросы и закрывать карточки. Включайте по необходимости.</div>

      {/* Плашка "в разработке" */}
      <div style={{
        display: 'flex',
        gap: '12px',
        alignItems: 'center',
        padding: '12px 16px',
        background: 'var(--warning-bg)',
        border: '1px solid var(--ark-yellow-100)',
        borderRadius: '8px',
        color: 'var(--warning-fg)',
        fontSize: '13px',
        marginBottom: '16px'
      }}>
        <Icon name="sparkle" size={16} />
        <div>
          <b>Скоро.</b> Функции автоматизации находятся в разработке. После запуска вы сможете настроить автоперевод кандидатов и уточняющие вопросы.
        </div>
      </div>

      <div className="nv-auto-block off">
        <div className="nv-auto-head">
          <span className="nv-cb">
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Автоматический перевод по AI-скорингу</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-inline">
            <span>Автоматически переводить на этап</span>
            <div className="nv-inline-select">
              <span className="nv-stage-dot" style={{ background: 'var(--ark-purple-500)' }} />
              <span>Отобран</span>
              <Icon name="chevD" size={12} />
            </div>
            <span>при скоринге AI &gt;</span>
            <input className="nv-num-input" type="number" min="0" max="100" value={80} disabled />
            <span className="nv-mute">из 100</span>
          </div>
          <div className="nv-auto-hint">
            <Icon name="sparkle" size={12} />
            Сейчас порог <b>80</b> — это «сильное совпадение». Глафира двигает только уверенных кандидатов.
          </div>
        </div>
      </div>

      <div className="nv-auto-block off">
        <div className="nv-auto-head">
          <span className="nv-cb">
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Уточняющие вопросы и автоперевод</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-inline">
            <span>Если карточка на этапе</span>
            <div className="nv-inline-select">
              <span className="nv-stage-dot" style={{ background: 'var(--ark-blue-500)' }} />
              <span>Отклик</span>
              <Icon name="chevD" size={12} />
            </div>
            <span>— Глафира задаёт уточняющие вопросы.</span>
          </div>
          <div className="nv-auto-inline">
            <span>При получении ответов переводит на этап</span>
            <div className="nv-inline-select">
              <span className="nv-stage-dot" style={{ background: 'var(--ark-purple-500)' }} />
              <span>Отобран</span>
              <Icon name="chevD" size={12} />
            </div>
          </div>
          <div className="nv-auto-hint">
            <Icon name="sparkle" size={12} />
            Полезно, когда в отклике мало данных — например, нет опыта или зарплаты.
          </div>
        </div>
      </div>

      <div className="nv-auto-block off">
        <div className="nv-auto-head">
          <span className="nv-cb">
            <Icon name="check" size={12} />
          </span>
          <span className="nv-auto-title">Автоматический отказ при неинтересе</span>
        </div>
        <div className="nv-auto-body">
          <div className="nv-auto-text">
            Если LLM по диалогу понимает, что вакансия кандидату <b>не интересна</b> или он <b>принял другой оффер</b>, Глафира сама переведёт его в «Отказ» с соответствующей причиной.
          </div>
          <div className="nv-reasons-row">
            <span className="nv-reason-pill"><span className="nv-rp-dot grey" />Не интересно</span>
            <span className="nv-reason-pill"><span className="nv-rp-dot grey" />Принял оффер</span>
          </div>
        </div>
      </div>
    </div>
  );
}