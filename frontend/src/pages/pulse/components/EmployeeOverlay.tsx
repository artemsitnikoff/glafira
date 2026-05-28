import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { AdaptBar } from './AdaptBar';
import { RiskBadge } from './RiskBadge';
import { HireOriginBlock } from './HireOriginBlock';
import { AlertsList } from './AlertsList';
import { OverviewTab } from './tabs/OverviewTab';
import { PlanTab } from './tabs/PlanTab';
import { SurveysTab } from './tabs/SurveysTab';
import { ChatTab } from '@/pages/funnel/candidate-detail/tabs/ChatTab';
import { AllActionsTab } from '@/pages/funnel/candidate-detail/tabs/AllActionsTab';
import type { EmployeeDetail } from '@/api/aliases';

type Props = {
  employee: EmployeeDetail;
  onClose: () => void;
  onNote?: (text: string) => void;
  onSurvey?: (type: string, templateKey?: string) => void;
};

const TABS = [
  { id: 'overview', label: 'Обзор' },
  { id: 'plan', label: 'План адаптации' },
  { id: 'surveys', label: 'Опросы' },
  { id: 'chat', label: 'Чат' },
  { id: 'actions', label: 'Действия' },
] as const;

export function EmployeeOverlay({ employee, onClose, onNote, onSurvey }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'overview';

  const [noteText, setNoteText] = useState('');
  const [showNoteModal, setShowNoteModal] = useState(false);
  const [showSurveyModal, setShowSurveyModal] = useState(false);

  const setActiveTab = (tabId: string) => {
    if (tabId === 'overview') {
      searchParams.delete('tab');
    } else {
      searchParams.set('tab', tabId);
    }
    setSearchParams(searchParams);
  };

  const handleAddNote = () => {
    if (noteText.trim() && onNote) {
      onNote(noteText.trim());
      setNoteText('');
      setShowNoteModal(false);
    }
  };

  const handleRunSurvey = (type: string) => {
    if (onSurvey) {
      onSurvey(type);
      setShowSurveyModal(false);
    }
  };

  const formatLastSurvey = () => {
    if (!employee.surveys || employee.surveys.length === 0) {
      return 'Опросов нет';
    }

    const lastSurvey = employee.surveys
      .sort((a, b) => new Date(b.sent_at).getTime() - new Date(a.sent_at).getTime())[0];

    const daysSince = Math.floor(
      (Date.now() - new Date(lastSurvey.sent_at).getTime()) / (1000 * 60 * 60 * 24)
    );

    const daysText = daysSince === 0 ? 'сегодня' : `${daysSince} дн. назад`;
    const scoreText = lastSurvey.overall_score ? `${lastSurvey.overall_score}/5` : '—';

    return `${daysText} · ${scoreText}`;
  };

  // Фильтрация алертов по сотруднику
  const employeeAlerts = employee.alerts || [];

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      right: 0,
      width: 'clamp(720px, 80vw, 1100px)',
      height: '100vh',
      backgroundColor: 'var(--bg-2)',
      boxShadow: '-4px 0 24px rgba(0, 0, 0, 0.1)',
      zIndex: 1000,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      {/* Тулбар */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-3)',
        padding: 'var(--space-4)',
        borderBottom: '1px solid var(--border-1)',
        backgroundColor: 'var(--bg-2)'
      }}>
        <button
          onClick={() => setActiveTab('chat')}
          style={{
            padding: '6px 12px',
            fontSize: '12px',
            fontWeight: 500,
            backgroundColor: 'var(--accent)',
            color: 'white',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-1)'
          }}
        >
          <span>💬</span>
          Связаться
        </button>

        <button
          onClick={() => setShowSurveyModal(true)}
          style={{
            padding: '6px 12px',
            fontSize: '12px',
            fontWeight: 500,
            backgroundColor: 'var(--bg-3)',
            color: 'var(--fg-1)',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-1)'
          }}
        >
          <span>📋</span>
          Запустить опрос
        </button>

        <button
          onClick={() => setShowNoteModal(true)}
          style={{
            padding: '6px 12px',
            fontSize: '12px',
            fontWeight: 500,
            backgroundColor: 'var(--bg-3)',
            color: 'var(--fg-1)',
            border: '1px solid var(--border-1)',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer'
          }}
        >
          Заметка
        </button>

        <div style={{ flex: 1 }} />

        <button
          onClick={onClose}
          style={{
            padding: '6px',
            backgroundColor: 'transparent',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            cursor: 'pointer',
            color: 'var(--fg-3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          <Icon name="x" size={16} />
        </button>
      </div>

      {/* Баннер для уволенного сотрудника */}
      {employee.status === 'left' && employee.left_at && (
        <div style={{
          padding: 'var(--space-3)',
          backgroundColor: 'var(--risk-high-soft)',
          borderBottom: '1px solid var(--risk-high)',
          color: 'var(--risk-high)',
          fontSize: '13px',
          fontWeight: 500,
          textAlign: 'center'
        }}>
          Сотрудник уволен {new Date(employee.left_at).toLocaleDateString('ru-RU')}
          {employee.left_reason && ` · ${employee.left_reason}`}
        </div>
      )}

      {/* Скроллируемый контент */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: 'var(--space-6)'
      }}>
        {/* Шапка */}
        <div style={{
          display: 'flex',
          gap: 'var(--space-6)',
          marginBottom: 'var(--space-6)'
        }}>
          {/* Левая колонка */}
          <div style={{ flex: 1 }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-4)',
              marginBottom: 'var(--space-3)'
            }}>
              {/* Avatar placeholder - можно добавить реальный аватар если есть */}
              <div style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                backgroundColor: 'var(--bg-3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '24px',
                fontWeight: 600,
                color: 'var(--fg-3)',
                border: '2px solid var(--border-1)'
              }}>
                {employee.full_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
              </div>

              <div>
                <h1 style={{
                  fontSize: '24px',
                  fontWeight: 700,
                  color: 'var(--fg-1)',
                  margin: 0,
                  marginBottom: '4px'
                }}>
                  {employee.full_name}
                </h1>
                <div style={{
                  fontSize: '14px',
                  color: 'var(--fg-2)'
                }}>
                  {[employee.position, employee.department].filter(Boolean).join(' · ')}
                </div>
              </div>
            </div>

            <div style={{
              fontSize: '13px',
              color: 'var(--fg-3)',
              marginBottom: 'var(--space-4)'
            }}>
              Руководитель: {employee.manager_full_name || '—'} ·
              Дата выхода: {new Date(employee.start_date).toLocaleDateString('ru-RU')} ·
              День {employee.adapt_day} из {employee.probation_days}
            </div>

            {/* AdaptBar большая */}
            <AdaptBar
              adaptDay={employee.adapt_day}
              probationDays={employee.probation_days}
              riskLevel={employee.risk_level}
              variant="large"
            />

            {/* HireOriginBlock */}
            <HireOriginBlock employee={employee} />
          </div>

          {/* Правая колонка */}
          <div style={{ minWidth: '180px' }}>
            <RiskBadge riskLevel={employee.risk_level} variant="large" />
            <div style={{
              fontSize: '12px',
              color: 'var(--fg-3)',
              marginTop: 'var(--space-2)',
              textAlign: 'center'
            }}>
              Последний опрос: {formatLastSurvey()}
            </div>
          </div>
        </div>

        {/* Алерты по сотруднику */}
        {employeeAlerts.length > 0 && (
          <div style={{ marginBottom: 'var(--space-6)' }}>
            <div style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--fg-1)',
              marginBottom: 'var(--space-3)'
            }}>
              Алерты Глафиры ({employeeAlerts.length})
            </div>
            <AlertsList alerts={employeeAlerts} />
          </div>
        )}

        {/* Табы */}
        <div style={{
          borderBottom: '1px solid var(--border-1)',
          marginBottom: 'var(--space-5)'
        }}>
          <div style={{
            display: 'flex',
            gap: 'var(--space-1)'
          }}>
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                style={{
                  padding: 'var(--space-3) var(--space-4)',
                  fontSize: '14px',
                  fontWeight: 500,
                  backgroundColor: 'transparent',
                  color: activeTab === tab.id ? 'var(--accent)' : 'var(--fg-2)',
                  border: 'none',
                  borderBottom: `2px solid ${activeTab === tab.id ? 'var(--accent)' : 'transparent'}`,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease'
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Контент табов */}
        <div style={{ minHeight: '400px' }}>
          {activeTab === 'overview' && <OverviewTab employee={employee} />}
          {activeTab === 'plan' && <PlanTab employee={employee} />}
          {activeTab === 'surveys' && <SurveysTab employee={employee} onRunSurvey={handleRunSurvey} />}
          {activeTab === 'chat' && <ChatTab candidateId={employee.candidate_id} />}
          {activeTab === 'actions' && <AllActionsTab candidateId={employee.candidate_id} />}
        </div>
      </div>

      {/* Модал заметки */}
      {showNoteModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1001
        }}>
          <div style={{
            backgroundColor: 'var(--bg-2)',
            padding: 'var(--space-6)',
            borderRadius: 'var(--radius-lg)',
            maxWidth: '480px',
            width: '90%',
            border: '1px solid var(--border-1)'
          }}>
            <h3 style={{
              margin: '0 0 var(--space-4) 0',
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--fg-1)'
            }}>
              Добавить заметку
            </h3>
            <textarea
              value={noteText}
              onChange={(e) => setNoteText(e.target.value)}
              placeholder="Введите заметку..."
              style={{
                width: '100%',
                height: '120px',
                padding: 'var(--space-3)',
                fontSize: '14px',
                backgroundColor: 'var(--bg-1)',
                border: '1px solid var(--border-1)',
                borderRadius: 'var(--radius-md)',
                color: 'var(--fg-1)',
                resize: 'vertical',
                fontFamily: 'inherit'
              }}
            />
            <div style={{
              display: 'flex',
              gap: 'var(--space-2)',
              marginTop: 'var(--space-4)',
              justifyContent: 'flex-end'
            }}>
              <button
                onClick={() => setShowNoteModal(false)}
                style={{
                  padding: '8px 16px',
                  fontSize: '14px',
                  backgroundColor: 'var(--bg-3)',
                  color: 'var(--fg-1)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-md)',
                  cursor: 'pointer'
                }}
              >
                Отмена
              </button>
              <button
                onClick={handleAddNote}
                disabled={!noteText.trim()}
                style={{
                  padding: '8px 16px',
                  fontSize: '14px',
                  backgroundColor: 'var(--accent)',
                  color: 'white',
                  border: 'none',
                  borderRadius: 'var(--radius-md)',
                  cursor: noteText.trim() ? 'pointer' : 'not-allowed',
                  opacity: noteText.trim() ? 1 : 0.5
                }}
              >
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Модал опроса */}
      {showSurveyModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1001
        }}>
          <div style={{
            backgroundColor: 'var(--bg-2)',
            padding: 'var(--space-6)',
            borderRadius: 'var(--radius-lg)',
            maxWidth: '400px',
            width: '90%',
            border: '1px solid var(--border-1)'
          }}>
            <h3 style={{
              margin: '0 0 var(--space-4) 0',
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--fg-1)'
            }}>
              Запустить опрос
            </h3>
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-2)'
            }}>
              {[
                { type: 'weekly', label: 'Еженедельный' },
                { type: 'monthly', label: 'Месячный' },
                { type: 'special', label: 'Специальный' },
                { type: 'enps', label: 'eNPS' },
              ].map((surveyType) => (
                <button
                  key={surveyType.type}
                  onClick={() => handleRunSurvey(surveyType.type)}
                  style={{
                    padding: 'var(--space-3)',
                    fontSize: '14px',
                    backgroundColor: 'var(--bg-3)',
                    color: 'var(--fg-1)',
                    border: '1px solid var(--border-1)',
                    borderRadius: 'var(--radius-md)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    transition: 'background-color 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--bg-3-hover)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'var(--bg-3)';
                  }}
                >
                  {surveyType.label}
                </button>
              ))}
            </div>
            <div style={{
              display: 'flex',
              justifyContent: 'flex-end',
              marginTop: 'var(--space-4)'
            }}>
              <button
                onClick={() => setShowSurveyModal(false)}
                style={{
                  padding: '8px 16px',
                  fontSize: '14px',
                  backgroundColor: 'var(--bg-3)',
                  color: 'var(--fg-1)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-md)',
                  cursor: 'pointer'
                }}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}