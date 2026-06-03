import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import './Pulse.css';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { usePulseEmployee } from '@/api/hooks/usePulse';
import { useAddNote, useRunSurvey, useRegenerateAiSummary } from '@/api/mutations/pulse';
import { OverviewTab } from './components/tabs/OverviewTab';
import { PlanTab } from './components/tabs/PlanTab';
import { SurveysTab } from './components/tabs/SurveysTab';
import { ChatTab } from '@/pages/funnel/candidate-detail/tabs/ChatTab';
import { AllActionsTab } from '@/pages/funnel/candidate-detail/tabs/AllActionsTab';

const TABS = [
  { id: 'overview', label: 'Обзор' },
  { id: 'plan', label: 'План адаптации' },
  { id: 'surveys', label: 'Опросы' },
  { id: 'chat', label: 'Чат' },
  { id: 'actions', label: 'Действия' },
] as const;

function AdaptBar({ day }: { day: number }) {
  const total = 90;
  const pct = Math.min(100, (day / total) * 100);
  const ticks = [
    { d: 0,  label: 'Найм' },
    { d: 7,  label: 'D7' },
    { d: 30, label: 'D30' },
    { d: 90, label: 'D90' },
  ];
  return (
    <div className="adapt-bar">
      <div className="track"/>
      <div className="fill" style={{width: `${pct}%`}}/>
      {ticks.map(t => {
        const left = (t.d / total) * 100;
        const done = day > t.d;
        const now  = Math.abs(day - t.d) < 4;
        return (
          <div key={t.d}>
            <div className={`tick ${done ? 'done' : ''} ${now ? 'now' : ''}`} style={{left: `${left}%`}}/>
            <div className="tick-label" style={{left: `${left}%`}}>{t.label}</div>
          </div>
        );
      })}
    </div>
  );
}

export function PulseEmployeePage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'overview';

  const { data: employee, isLoading, error } = usePulseEmployee(employeeId);
  const addNoteMutation = useAddNote();
  const runSurveyMutation = useRunSurvey();
  const regenerateAiSummaryMutation = useRegenerateAiSummary();

  const setActiveTab = (tabId: string) => {
    if (tabId === 'overview') {
      searchParams.delete('tab');
    } else {
      searchParams.set('tab', tabId);
    }
    setSearchParams(searchParams);
  };

  const handleClose = () => {
    navigate('/pulse');
  };

  const handleAddNote = async (text: string) => {
    if (!employeeId) return;

    try {
      await addNoteMutation.mutateAsync({ employeeId, text });
    } catch (error) {
      console.error('Failed to add note:', error);
    }
  };

  const handleRunSurvey = async (type: string, templateKey?: string) => {
    if (!employeeId) return;

    try {
      await runSurveyMutation.mutateAsync({ employeeId, type, templateKey });
    } catch (error) {
      console.error('Failed to run survey:', error);
    }
  };

  const handleRegenerateAiSummary = async () => {
    if (!employeeId) return;

    try {
      await regenerateAiSummaryMutation.mutateAsync(employeeId);
    } catch (error) {
      console.error('Failed to regenerate AI summary:', error);
    }
  };

  if (isLoading) {
    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          <div style={{padding:'40px', textAlign:'center', color:'var(--fg-3)'}}>
            Загружается карточка сотрудника...
          </div>
        </div>
      </div>
    );
  }

  if (error || !employee) {
    return (
      <div className="pulse-content">
        <div className="pulse-content-inner">
          <div style={{marginBottom:12}}>
            <div className="pulse-back" onClick={handleClose}>
              <Icon name="chevron-left" size={14}/> К списку сотрудников
            </div>
          </div>
          <div style={{padding:'40px', textAlign:'center', color:'var(--fg-3)'}}>
            Сотрудник не найден
          </div>
        </div>
      </div>
    );
  }

  const getRiskBucket = (riskLevel: string): 'red' | 'yellow' | 'green' => {
    switch (riskLevel) {
      case 'high': return 'red';
      case 'mid': return 'yellow';
      case 'low': return 'green';
      default: return 'green';
    }
  };

  const bucket = getRiskBucket(employee.risk_level);
  const riskLabelRu = employee.risk_level === 'high' ? 'Высокий' : employee.risk_level === 'mid' ? 'Средний' : 'Норма';

  const renderActiveTab = () => {
    switch (activeTab) {
      case 'plan':
        return <PlanTab employee={employee} />;
      case 'surveys':
        return <SurveysTab employee={employee} onRunSurvey={handleRunSurvey} />;
      case 'chat':
        return employee.candidate_id ? (
          <ChatTab candidateId={employee.candidate_id} />
        ) : (
          <div style={{padding: '40px', textAlign: 'center', color: 'var(--fg-3)'}}>
            Чат недоступен (нет связи с кандидатом)
          </div>
        );
      case 'actions':
        return employee.candidate_id ? (
          <AllActionsTab candidateId={employee.candidate_id} />
        ) : (
          <div style={{padding: '40px', textAlign: 'center', color: 'var(--fg-3)'}}>
            История действий недоступна
          </div>
        );
      default:
        return <OverviewTab employee={employee} onRegenerateAiSummary={handleRegenerateAiSummary} />;
    }
  };

  return (
    <div className="pulse-content">
      <div className="pulse-content-inner">
        <div style={{marginBottom:12}}>
          <div className="pulse-back" onClick={handleClose}>
            <Icon name="chevron-left" size={14}/> К списку сотрудников
          </div>
        </div>

        {/* Баннер для уволенного сотрудника */}
        {employee.status === 'left' && employee.left_at && (
          <div style={{
            padding: '12px 14px',
            backgroundColor: 'var(--risk-high-soft)',
            border: '1px solid var(--risk-high)',
            borderRadius: '8px',
            color: 'var(--risk-high)',
            fontSize: '13px',
            fontWeight: 500,
            marginBottom: '16px',
            textAlign: 'center'
          }}>
            Сотрудник уволен {new Date(employee.left_at).toLocaleDateString('ru-RU')}
            {employee.left_reason && ` · ${employee.left_reason}`}
          </div>
        )}

        {/* Шапка в стиле эталона */}
        <div className="ec-head">
          <div className="ec-head-left">
            <div style={{display:'flex', alignItems:'center', gap:14}}>
              <Avatar name={employee.full_name} size="lg"/>
              <div>
                <h1 className="ec-name">{employee.full_name}</h1>
                <div className="ec-meta">
                  {employee.position && (
                    <>
                      {employee.position}
                      <span className="sep">·</span>
                    </>
                  )}
                  {employee.department && (
                    <>
                      {employee.department}
                      <span className="sep">·</span>
                    </>
                  )}
                  Руководитель: {employee.manager_full_name || '—'}
                </div>
              </div>
            </div>
            <div className="ec-day-line">
              <span className="ec-day-num">День {employee.adapt_day} из {employee.probation_days}</span>
              <span style={{color:'var(--fg-3)'}}>·</span>
              <span>Нанят: {new Date(employee.start_date).toLocaleDateString('ru-RU')}</span>
            </div>
            <div style={{marginTop:8}}>
              <AdaptBar day={employee.adapt_day}/>
            </div>
            <div className="ec-actions">
              <button className="btn btn-primary" onClick={() => setActiveTab('chat')}>
                <Icon name="message-square" size={14}/> Связаться
              </button>
              <button className="btn btn-secondary" onClick={() => handleRunSurvey('pulse')}>
                <Icon name="clipboard" size={14}/> Запустить опрос
              </button>
              <button className="btn btn-ghost" onClick={() => handleAddNote('')}>
                Заметка
              </button>
            </div>
          </div>
          <div className="ec-head-right">
            <div className={`ec-risk-big ${bucket}`}>
              <div className="lbl">{riskLabelRu}</div>
            </div>
          </div>
        </div>

        {/* Табы */}
        <div className="set-toptabs">
          {TABS.map(tab => (
            <button key={tab.id}
              className={`set-toptab ${activeTab === tab.id ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.id)}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Контент таба */}
        <div style={{ marginTop: '20px' }}>
          {renderActiveTab()}
        </div>
      </div>
    </div>
  );
}