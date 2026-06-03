import { Icon } from '@/components/ui/Icon';
import type { EmployeeDetail } from '@/api/aliases';

type Props = {
  employee: EmployeeDetail;
  onRegenerateAiSummary?: () => void;
};

export function OverviewTab({ employee, onRegenerateAiSummary }: Props) {

  // Расчёт мини-плашек
  const enps = employee.enps ?? null;

  const satisfaction = employee.surveys && employee.surveys.length > 0
    ? (employee.surveys.reduce((sum, survey) => sum + (survey.overall_score || 0), 0) / employee.surveys.length)
    : null;

  const planProgress = employee.plan && employee.plan.length > 0
    ? Math.round((employee.plan.filter(item => item.is_done).length / employee.plan.length) * 100)
    : 0;

  // Обработчик генерации AI-сводки
  function handleRegenerateAiSummary() {
    onRegenerateAiSummary?.();
  }

  // Timeline последних событий (мини-версия)
  const recentEvents = [
    // Последние notes
    ...(employee.notes || []).map(note => ({
      type: 'note',
      text: `Заметка: ${note.text}`,
      date: note.created_at,
      icon: 'file-text'
    })),
    // Последние surveys
    ...(employee.surveys || []).map(survey => ({
      type: 'survey',
      text: `Опрос отправлен${survey.answered_at ? ' и отвечен' : ''}`,
      date: survey.sent_at,
      icon: 'clipboard'
    })),
    // Последние alerts
    ...(employee.alerts || []).map(alert => ({
      type: 'alert',
      text: alert.title,
      date: alert.created_at,
      icon: 'alert-triangle'
    }))
  ]
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
    .slice(0, 5);

  return (
    <div>
      {/* AI-сводка */}
      <div style={{
        padding: 'var(--space-5)',
        backgroundColor: 'var(--bg-panel-2)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-1)',
        marginBottom: 'var(--space-5)',
        position: 'relative'
      }}>
        {employee.ai_summary ? (
          <>
            <div style={{
              textAlign: 'left',
              marginBottom: 'var(--space-4)'
            }}>
              <p style={{
                fontSize: '15px',
                fontWeight: 400,
                color: 'var(--fg-1)',
                margin: 0,
                lineHeight: 1.5
              }}>
                {employee.ai_summary}
              </p>
            </div>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}>
              <div style={{
                fontSize: '12px',
                color: 'var(--fg-3)'
              }}>
                Обновлено: {employee.ai_summary_generated_at
                  ? new Date(employee.ai_summary_generated_at).toLocaleString('ru-RU', {
                      dateStyle: 'short',
                      timeStyle: 'short'
                    })
                  : 'неизвестно'}
              </div>
              <button
                onClick={handleRegenerateAiSummary}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: '12px',
                  backgroundColor: 'var(--bg-3)',
                  color: 'var(--fg-2)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer'
                }}
              >
                <Icon
                  name="refresh-cw"
                  size={12}
                />
                Переоценить
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ textAlign: 'center' }}>
              <Icon name="brain" size={32} style={{
                color: 'var(--fg-4)',
                marginBottom: 'var(--space-3)'
              }} />
              <h3 style={{
                fontSize: '16px',
                fontWeight: 600,
                color: 'var(--fg-2)',
                margin: '0 0 var(--space-2) 0'
              }}>
                Сводка появится после первых опросов
              </h3>
              <p style={{
                fontSize: '14px',
                color: 'var(--fg-3)',
                margin: '0 0 var(--space-4) 0'
              }}>
                Глафира проанализирует ответы сотрудника и даст рекомендации
              </p>
              <button
                onClick={handleRegenerateAiSummary}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 'var(--space-2)',
                  padding: 'var(--space-2) var(--space-3)',
                  fontSize: '13px',
                  backgroundColor: 'var(--bg-3)',
                  color: 'var(--fg-2)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer'
                }}
              >
                <Icon
                  name="brain"
                  size={14}
                />
                Сгенерировать
              </button>
            </div>
          </>
        )}
      </div>

      {/* 4 мини-плашки */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: 'var(--space-4)',
        marginBottom: 'var(--space-6)'
      }}>
        {/* eNPS */}
        <div style={{
          padding: 'var(--space-4)',
          backgroundColor: 'var(--bg-2)',
          border: '1px solid var(--border-1)',
          borderRadius: 'var(--radius-md)',
          textAlign: 'center'
        }}>
          <div style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--fg-1)',
            marginBottom: 'var(--space-1)'
          }}>
            {enps !== null ? `+${enps}` : '—'}
          </div>
          <div style={{
            fontSize: '11px',
            color: 'var(--fg-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em'
          }}>
            eNPS
          </div>
        </div>

        {/* Удовлетворённость */}
        <div style={{
          padding: 'var(--space-4)',
          backgroundColor: 'var(--bg-2)',
          border: '1px solid var(--border-1)',
          borderRadius: 'var(--radius-md)',
          textAlign: 'center'
        }}>
          <div style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--fg-1)',
            marginBottom: 'var(--space-1)'
          }}>
            {satisfaction !== null ? `${satisfaction.toFixed(1)}/5` : '—'}
          </div>
          <div style={{
            fontSize: '11px',
            color: 'var(--fg-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em'
          }}>
            Удовлетворённость
          </div>
        </div>

        {/* Активность */}
        <div style={{
          padding: 'var(--space-4)',
          backgroundColor: 'var(--bg-2)',
          border: '1px solid var(--border-1)',
          borderRadius: 'var(--radius-md)',
          textAlign: 'center'
        }}>
          <div style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--fg-1)',
            marginBottom: 'var(--space-1)'
          }}>
            —
          </div>
          <div style={{
            fontSize: '11px',
            color: 'var(--fg-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em'
          }}>
            Активность
          </div>
          {/* Tooltip или пояснение для нет данных */}
          <div style={{
            fontSize: '10px',
            color: 'var(--fg-4)',
            marginTop: '2px'
          }}>
            нет данных
          </div>
        </div>

        {/* Прогресс плана */}
        <div style={{
          padding: 'var(--space-4)',
          backgroundColor: 'var(--bg-2)',
          border: '1px solid var(--border-1)',
          borderRadius: 'var(--radius-md)',
          textAlign: 'center'
        }}>
          <div style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--fg-1)',
            marginBottom: 'var(--space-1)'
          }}>
            {planProgress}%
          </div>
          <div style={{
            fontSize: '11px',
            color: 'var(--fg-3)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em'
          }}>
            Прогресс плана
          </div>
        </div>
      </div>

      {/* Timeline последних событий */}
      <div>
        <h3 style={{
          fontSize: '16px',
          fontWeight: 600,
          color: 'var(--fg-1)',
          margin: '0 0 var(--space-4) 0'
        }}>
          Последние события
        </h3>

        {recentEvents.length === 0 ? (
          <div style={{
            padding: 'var(--space-6)',
            textAlign: 'center',
            color: 'var(--fg-3)',
            backgroundColor: 'var(--bg-panel-2)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border-1)'
          }}>
            Событий пока нет
          </div>
        ) : (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-3)'
          }}>
            {recentEvents.map((event, index) => (
              <div
                key={index}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 'var(--space-3)',
                  padding: 'var(--space-3)',
                  backgroundColor: 'var(--bg-2)',
                  border: '1px solid var(--border-1)',
                  borderRadius: 'var(--radius-md)'
                }}
              >
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  backgroundColor: 'var(--bg-3)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0
                }}>
                  <Icon name={event.icon as any /* event.icon is valid icon name from static data above */} size={14} style={{ color: 'var(--fg-3)' }} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: '13px',
                    color: 'var(--fg-1)',
                    marginBottom: '2px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap'
                  }}>
                    {event.text}
                  </div>
                  <div style={{
                    fontSize: '11px',
                    color: 'var(--fg-3)',
                    fontFamily: 'var(--font-mono)'
                  }}>
                    {new Date(event.date).toLocaleDateString('ru-RU', {
                      day: '2-digit',
                      month: 'short',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </div>
                </div>

                {event.type === 'alert' && (
                  <div style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    backgroundColor: 'var(--risk-mid-soft)',
                    color: 'var(--risk-mid)',
                    borderRadius: 'var(--radius-sm)',
                    fontWeight: 500
                  }}>
                    АЛЕРТ
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}