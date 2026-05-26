import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './vacancies/VacancyForm.css';
import { Icon } from '@/components/ui/Icon';
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

const GLAFIRA_MODES = [
  { id: 'A', name: 'Режим A', description: 'Базовый режим' },
  { id: 'B', name: 'Режим B', description: 'Активный режим' },
  { id: 'C', name: 'Режим C', description: 'Максимальный режим' },
];

const STEPS = [
  { id: 'description', label: 'Описание вакансии', icon: 'briefcase' },
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

  const [currentStep, setCurrentStep] = useState(0);
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
    glafira_mode: 'A',
    team: [],
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
        funnel_template: 'default', // Would need to get from backend
        glafira_mode: vacancy.glafira_mode,
        team: vacancy.team?.map(u => u.id) || [],
        auto_move: false, // Would need to get from backend
        auto_move_threshold: 80,
        auto_qa_from: null,
        auto_qa_to: null,
        auto_reject: false,
      });
    }
  }, [editMode, vacancy]);

  const isValid = formData.name.trim().length > 0;

  const handleNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleSubmit();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
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
      console.error('Failed to save vacancy:', error);
    }
  };

  const updateFormData = (updates: Partial<VacancyCreate>) => {
    setFormData(prev => ({ ...prev, ...updates }));
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

      {/* Progress chips */}
      <div className="funnel-row nv-funnel-row">
        {STEPS.map((step, i) => {
          const isActive = i === currentStep;
          const isDone = i < currentStep;
          return (
            <div key={step.id}>
              <div
                className={`funnel-chip nv-chip-readonly ${isActive ? 'active' : ''} ${
                  isDone ? 'funnel-hired' : ''
                }`}
              >
                {isDone ? (
                  <Icon name="check" size={12} />
                ) : (
                  <span className="nv-step-num">{i + 1}</span>
                )}
                {step.label}
              </div>
              {i < STEPS.length - 1 && <Icon name="chevR" size={12} className="funnel-arrow" />}
            </div>
          );
        })}
      </div>

      {/* Form */}
      <div className="nv-grid">
        <div className="nv-card nv-card-full">
          {currentStep === 0 && (
            <DescriptionStep
              data={formData}
              onChange={updateFormData}
              clients={clients || []}
            />
          )}
          {currentStep === 1 && (
            <FunnelStep
              data={formData}
              onChange={updateFormData}
            />
          )}
          {currentStep === 2 && (
            <TeamStep
              data={formData}
              onChange={updateFormData}
              users={users?.items || []}
            />
          )}
          {currentStep === 3 && (
            <AutomationStep
              data={formData}
              onChange={updateFormData}
            />
          )}

          <div className="nv-card-foot">
            <button className="btn btn-secondary btn-sm" onClick={handlePrev}>
              <Icon name="chevL" size={13} /> {currentStep === 0 ? 'Отмена' : 'Назад'}
            </button>
            <div className="nv-foot-progress">
              Шаг <b>{currentStep + 1}</b> из <b>{STEPS.length}</b>
            </div>
            <button
              className={`btn btn-primary btn-sm ${!isValid ? 'is-disabled' : ''}`}
              disabled={!isValid}
              onClick={handleNext}
            >
              <Icon name="arrowRight" size={14} />
              {currentStep === STEPS.length - 1
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
      <div className="nv-h2">
        Базовая информация — название, локация, дата закрытия. Текст требований и обязанностей.
      </div>

      <div className="nv-field">
        <label className="nv-label">
          Название вакансии <span className="nv-req">*</span>
        </label>
        <input
          className="nv-input"
          placeholder="Например, Frontend-разработчик (Senior)"
          value={data.name}
          onChange={e => onChange({ name: e.target.value })}
        />
      </div>

      <div className="nv-field nv-field-sort">
        <label className="nv-label">
          Сортировка
          <span className="nv-mute" style={{ fontWeight: 400, marginLeft: 6 }}>
            (порядок в списке)
          </span>
        </label>
        <input
          className="nv-input t-mono"
          type="number"
          step="10"
          min="0"
          placeholder="500"
          value={data.sort_order}
          onChange={e => onChange({ sort_order: Number(e.target.value) })}
        />
      </div>

      <div className="nv-grid-3">
        <div className="nv-field">
          <label className="nv-label">Клиент</label>
          <select
            className="nv-input"
            value={data.client_id || ''}
            onChange={e => onChange({ client_id: e.target.value || null })}
          >
            <option value="">Без клиента</option>
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
          <input
            className="nv-input"
            type="number"
            min="1"
            value={data.positions_count}
            onChange={e => onChange({ positions_count: Number(e.target.value) })}
          />
        </div>

        <div className="nv-field">
          <label className="nv-label">Тип занятости</label>
          <div className="nv-segmented">
            {EMPLOYMENT_TYPES.map(type => (
              <button
                key={type.id}
                type="button"
                className={data.employment_type === type.id ? 'active' : ''}
                onClick={() => onChange({ employment_type: type.id })}
              >
                {type.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-toggle-row">
          <input
            type="checkbox"
            checked={data.is_confidential}
            onChange={e => onChange({ is_confidential: e.target.checked })}
          />
          <span>
            <b>Конфиденциальная вакансия</b>
            <span className="nv-mute"> · видна только участникам команды</span>
          </span>
        </label>
      </div>

      <div className="nv-field">
        <label className="nv-label">Зарплатная вилка</label>
        <div className="nv-grid-2-tight">
          <input
            className="nv-input"
            type="number"
            placeholder="от"
            value={data.salary_from || ''}
            onChange={e => onChange({ salary_from: Number(e.target.value) || null })}
          />
          <input
            className="nv-input"
            type="number"
            placeholder="до"
            value={data.salary_to || ''}
            onChange={e => onChange({ salary_to: Number(e.target.value) || null })}
          />
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-label">Требования, обязанности, условия</label>
        <textarea
          className="nv-textarea"
          rows={8}
          placeholder="Требования:&#10;Обязанности:&#10;Условия работы:"
          value={data.description || ''}
          onChange={e => onChange({ description: e.target.value || null })}
        />
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
      <div className="nv-h2">
        Этапы, по которым пойдёт кандидат. По умолчанию — шаблон из настроек.
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
  const toggleUser = (userId: string) => {
    const currentTeam = data.team || [];
    if (currentTeam.includes(userId)) {
      onChange({ team: currentTeam.filter(id => id !== userId) });
    } else {
      onChange({ team: [...currentTeam, userId] });
    }
  };

  return (
    <div className="nv-step-body">
      <div className="nv-h1">Команда вакансии</div>
      <div className="nv-h2">
        Кто видит вакансию, ведёт кандидатов и принимает решения. Первый добавленный — ответственный рекрутер.
      </div>

      <div className="nv-user-list">
        {users.map(user => {
          const isSelected = data.team.includes(user.id);
          const isOwner = data.team[0] === user.id;
          return (
            <div
              key={user.id}
              className={`nv-user-row ${isSelected ? 'on' : ''}`}
              onClick={() => toggleUser(user.id)}
            >
              <span className={`nv-check ${isSelected ? 'on' : ''}`}>
                {isSelected && <Icon name="check" size={11} />}
              </span>
              <div className="nv-ur-text">
                <div className="nv-ur-name">
                  {user.full_name}
                  {isOwner && <span className="nv-owner-badge">ответственный</span>}
                </div>
                <div className="nv-ur-meta">{user.role || 'Сотрудник'}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AutomationStep({
  data,
  onChange,
}: {
  data: VacancyCreate;
  onChange: (updates: Partial<VacancyCreate>) => void;
}) {
  return (
    <div className="nv-step-body">
      <div className="nv-h1">Автоматизация</div>
      <div className="nv-h2">
        Глафира будет действовать сама — переводить кандидатов, задавать уточняющие вопросы и закрывать карточки.
      </div>

      <div className="nv-field">
        <label className="nv-label">Режим Глафиры</label>
        <div className="nv-segmented">
          {GLAFIRA_MODES.map(mode => (
            <button
              key={mode.id}
              type="button"
              className={data.glafira_mode === mode.id ? 'active' : ''}
              onClick={() => onChange({ glafira_mode: mode.id })}
              title={mode.description}
            >
              {mode.name}
            </button>
          ))}
        </div>
      </div>

      <div className="nv-field">
        <label className="nv-toggle-row">
          <input
            type="checkbox"
            checked={data.auto_move}
            onChange={e => onChange({ auto_move: e.target.checked })}
          />
          <span>
            <b>Автоматический перевод по AI-скорингу</b>
            <span className="nv-mute"> · при скоринге выше порога</span>
          </span>
        </label>
        {data.auto_move && (
          <div className="nv-auto-controls">
            <label>
              Порог скоринга:
              <input
                type="number"
                min="0"
                max="100"
                value={data.auto_move_threshold || 80}
                onChange={e => onChange({ auto_move_threshold: Number(e.target.value) })}
              />
            </label>
          </div>
        )}
      </div>

      <div className="nv-field">
        <label className="nv-toggle-row">
          <input
            type="checkbox"
            checked={data.auto_reject}
            onChange={e => onChange({ auto_reject: e.target.checked })}
          />
          <span>
            <b>Автоматический отказ при неинтересе</b>
            <span className="nv-mute"> · если кандидат не заинтересован</span>
          </span>
        </label>
      </div>
    </div>
  );
}