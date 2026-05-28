import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import type { EmployeeDetail } from '@/api/aliases';

type Props = {
  employee: EmployeeDetail;
  onRunSurvey: (type: string, templateKey?: string) => void;
};

const SURVEY_TYPE_LABELS = {
  weekly: 'Еженедельный',
  monthly: 'Месячный',
  special: 'Специальный',
  enps: 'eNPS',
} as const;

export function SurveysTab({ employee, onRunSurvey }: Props) {
  const [expandedSurvey, setExpandedSurvey] = useState<string | null>(null);

  const surveys = (employee.surveys || []).sort(
    (a, b) => new Date(b.sent_at).getTime() - new Date(a.sent_at).getTime()
  );

  const toggleExpanded = (surveyId: string) => {
    setExpandedSurvey(expandedSurvey === surveyId ? null : surveyId);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('ru-RU', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const renderAnswers = (answers: any[]) => {
    if (!answers || answers.length === 0) {
      return (
        <div style={{
          color: 'var(--fg-3)',
          fontSize: '13px',
          fontStyle: 'italic'
        }}>
          Ответы не предоставлены
        </div>
      );
    }

    return (
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)'
      }}>
        {answers.map((answer: any, index: number) => (
          <div
            key={index}
            style={{
              padding: 'var(--space-3)',
              backgroundColor: 'var(--bg-3)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '13px'
            }}
          >
            {typeof answer === 'string' ? answer : JSON.stringify(answer)}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div>
      {/* Кнопка запуска нового опроса */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 'var(--space-5)'
      }}>
        <h3 style={{
          fontSize: '16px',
          fontWeight: 600,
          color: 'var(--fg-1)',
          margin: 0
        }}>
          История опросов ({surveys.length})
        </h3>

        <button
          onClick={() => onRunSurvey('weekly')}
          style={{
            padding: '8px 16px',
            fontSize: '14px',
            fontWeight: 500,
            backgroundColor: 'var(--accent)',
            color: 'white',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)'
          }}
        >
          <Icon name="plus" size={14} />
          Запустить новый опрос
        </button>
      </div>

      {/* Список опросов */}
      {surveys.length === 0 ? (
        <div style={{
          padding: 'var(--space-8)',
          textAlign: 'center',
          backgroundColor: 'var(--bg-panel-2)',
          borderRadius: 'var(--radius-lg)',
          border: '1px solid var(--border-1)'
        }}>
          <Icon name="clipboard" size={32} style={{
            color: 'var(--fg-4)',
            marginBottom: 'var(--space-3)'
          }} />
          <h3 style={{
            fontSize: '16px',
            fontWeight: 600,
            color: 'var(--fg-2)',
            margin: '0 0 var(--space-2) 0'
          }}>
            Опросы ещё не отправлялись
          </h3>
          <p style={{
            fontSize: '14px',
            color: 'var(--fg-3)',
            margin: 0
          }}>
            Первый опрос будет отправлен автоматически через неделю после начала работы
          </p>
        </div>
      ) : (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-3)'
        }}>
          {surveys.map((survey) => {
            const isExpanded = expandedSurvey === survey.id;
            const hasAnswers = survey.answers && survey.answers.length > 0;

            return (
              <div
                key={survey.id}
                style={{
                  backgroundColor: 'var(--bg-2)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-lg)',
                  overflow: 'hidden'
                }}
              >
                {/* Заголовок опроса */}
                <div
                  onClick={() => toggleExpanded(survey.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--space-4)',
                    padding: 'var(--space-4)',
                    cursor: hasAnswers ? 'pointer' : 'default',
                    transition: 'background-color 0.2s ease'
                  }}
                  onMouseEnter={(e) => {
                    if (hasAnswers) {
                      e.currentTarget.style.backgroundColor = 'var(--bg-3)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.backgroundColor = 'transparent';
                  }}
                >
                  {/* Тип опроса */}
                  <div style={{
                    padding: '4px 8px',
                    fontSize: '11px',
                    fontWeight: 600,
                    backgroundColor: 'var(--accent)',
                    color: 'white',
                    borderRadius: 'var(--radius-sm)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em'
                  }}>
                    {SURVEY_TYPE_LABELS[survey.type as keyof typeof SURVEY_TYPE_LABELS] || survey.type}
                  </div>

                  {/* Информация */}
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontSize: '14px',
                      fontWeight: 500,
                      color: 'var(--fg-1)',
                      marginBottom: '2px'
                    }}>
                      Отправлен {formatDate(survey.sent_at)}
                    </div>
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-3)',
                      fontSize: '12px',
                      color: 'var(--fg-3)'
                    }}>
                      {survey.answered_at ? (
                        <span style={{ color: 'var(--risk-low)' }}>
                          ✓ Отвечен {formatDate(survey.answered_at)}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--risk-mid)' }}>
                          ⏳ Ожидает ответа
                        </span>
                      )}
                      {survey.overall_score && (
                        <>
                          <span>•</span>
                          <span>Оценка: {survey.overall_score}/5</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Стрелка раскрытия */}
                  {hasAnswers && (
                    <Icon
                      name="chevron-down"
                      size={16}
                      style={{
                        color: 'var(--fg-3)',
                        transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                        transition: 'transform 0.2s ease'
                      }}
                    />
                  )}
                </div>

                {/* Развёрнутый контент */}
                {isExpanded && hasAnswers && (
                  <div style={{
                    padding: '0 var(--space-4) var(--space-4) var(--space-4)',
                    borderTop: '1px solid var(--border-1)'
                  }}>
                    <div style={{
                      fontSize: '13px',
                      fontWeight: 500,
                      color: 'var(--fg-2)',
                      marginBottom: 'var(--space-3)'
                    }}>
                      Ответы:
                    </div>
                    {renderAnswers(survey.answers)}
                  </div>
                )}

                {/* Если нет ответов, но пытаемся раскрыть */}
                {isExpanded && !hasAnswers && (
                  <div style={{
                    padding: '0 var(--space-4) var(--space-4) var(--space-4)',
                    borderTop: '1px solid var(--border-1)',
                    textAlign: 'center',
                    color: 'var(--fg-3)',
                    fontSize: '13px',
                    fontStyle: 'italic'
                  }}>
                    Сотрудник ещё не ответил на этот опрос
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}