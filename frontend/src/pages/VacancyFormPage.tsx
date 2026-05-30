import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './vacancies/VacancyForm.css';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { useCreateVacancy, useUpdateVacancy } from '@/api/mutations/vacancies';
import { useVacancy } from '@/api/hooks/useVacancy';
import { useClients } from '@/api/hooks/useClients';
import { useUsers } from '@/api/hooks/useUsers';
import type { components } from '@/api/types';

type VacancyCreate = components['schemas']['VacancyCreate'];
type VacancyUpdate = components['schemas']['VacancyUpdate'];

const FUNNEL_TEMPLATES = [
  { id: 'default', name: 'По умолчанию' },
  { id: 'mass', name: 'Массовый подбор · короткая' },
  { id: 'technical', name: 'Техническая · с тестовым' },
  { id: 'sales', name: 'Продажи · 4 этапа' },
];

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
  const { data: clients } = useClients();
  const { data: users } = useUsers();

  const createMutation = useCreateVacancy();
  const updateMutation = useUpdateVacancy();

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

  const currentStepIndex = STEPS.findIndex(s => s.id === activeStep);

  // Валидация перехода
  const canProceed = () => {
    if (activeStep === 'desc') {
      return formData.name.trim().length > 0;
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
        const result = await createMutation.mutateAsync(formData);
        navigate(`/vacancies/${result.id}`);
      }
    } catch (error) {
      // Удаляем console.log согласно заданию
    }
  };

  const updateFormData = (updates: Partial<VacancyCreate>) => {
    setFormData(prev => ({ ...prev, ...updates }));
  };

  // Прогресс для чипов
  const completion: Record<string, boolean> = {
    desc: formData.name.trim().length > 0,
    funnel: true, // Всегда проходим
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
}: {
  data: VacancyCreate;
  onChange: (updates: Partial<VacancyCreate>) => void;
}) {
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
                onChange={e => onChange({ funnel_template: e.target.value })}
              />
              <span className="funnel-template-name">{template.name}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="nv-field">
        <div style={{
          padding: '16px 20px',
          background: 'var(--bg-panel-2)',
          border: '1px solid var(--border-1)',
          borderRadius: '8px',
          color: 'var(--fg-2)',
          fontSize: '13px',
          fontStyle: 'italic'
        }}>
          Полный редактор этапов воронки — скоро
        </div>
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