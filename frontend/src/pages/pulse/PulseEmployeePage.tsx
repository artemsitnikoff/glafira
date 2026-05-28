import { useParams, useNavigate } from 'react-router-dom';
import { usePulseEmployee } from '@/api/hooks/usePulse';
import { useAddNote, useRunSurvey } from '@/api/mutations/pulse';
import { EmployeeOverlay } from './components/EmployeeOverlay';
import { Icon } from '@/components/ui/Icon';

export function PulseEmployeePage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();

  const { data: employee, isLoading, error } = usePulseEmployee(employeeId);
  const addNoteMutation = useAddNote();
  const runSurveyMutation = useRunSurvey();

  const handleClose = () => {
    navigate('/pulse');
  };

  const handleAddNote = async (text: string) => {
    if (!employeeId) return;

    try {
      await addNoteMutation.mutateAsync({ employeeId, text });
    } catch (error) {
      console.error('Failed to add note:', error);
      // В реальном приложении тут должен быть toast с ошибкой
    }
  };

  const handleRunSurvey = async (type: string, templateKey?: string) => {
    if (!employeeId) return;

    try {
      await runSurveyMutation.mutateAsync({ employeeId, type, templateKey });
    } catch (error) {
      console.error('Failed to run survey:', error);
      // В реальном приложении тут должен быть toast с ошибкой
    }
  };

  if (isLoading) {
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
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 'var(--space-4)'
        }}>
          <Icon name="loader" size={32} style={{ color: 'var(--fg-3)' }} />
          <div style={{ color: 'var(--fg-2)' }}>Загружается карточка сотрудника...</div>
        </div>
      </div>
    );
  }

  if (error || !employee) {
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
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 'var(--space-4)',
          textAlign: 'center',
          maxWidth: '400px'
        }}>
          <Icon name="alert-triangle" size={32} style={{ color: 'var(--risk-mid)' }} />
          <div>
            <h3 style={{
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--fg-1)',
              margin: '0 0 var(--space-2) 0'
            }}>
              Сотрудник не найден
            </h3>
            <p style={{
              fontSize: '14px',
              color: 'var(--fg-3)',
              margin: '0 0 var(--space-4) 0'
            }}>
              Возможно, сотрудник был удалён или вы перешли по неверной ссылке.
            </p>
          </div>
          <button
            onClick={handleClose}
            style={{
              padding: '8px 16px',
              fontSize: '14px',
              backgroundColor: 'var(--accent)',
              color: 'white',
              border: 'none',
              borderRadius: 'var(--radius-md)',
              cursor: 'pointer'
            }}
          >
            Вернуться к списку
          </button>
        </div>
      </div>
    );
  }

  // Скрыть кнопку «Закрыть карточку адаптации» если статус уже passed
  // (согласно ТЗ пункт 2: «В состоянии status='passed' скрой (не disabled — именно убрать)»)
  // const showCloseAdaptationButton = employee.status !== 'passed';

  return (
    <EmployeeOverlay
      employee={employee}
      onClose={handleClose}
      onNote={handleAddNote}
      onSurvey={handleRunSurvey}
    />
  );
}