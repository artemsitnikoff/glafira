import { useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { useVerification } from '@/api/hooks/useVerification';
import { useRequestConsent, useRunVerification } from '@/api/mutations/candidateDetail';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

export function VerificationTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const [, setSearchParams] = useSearchParams();
  const { data: verification, isLoading, error } = useVerification(actualCandidateId);
  const consentMutation = useRequestConsent(actualCandidateId);
  const verifyMutation = useRunVerification(actualCandidateId);

  function handleRequestConsent() {
    consentMutation.mutate({
      channel: 'email',
    });
  }

  function handleRunVerification() {
    verifyMutation.mutate(undefined, {
      onError: (error) => {
        // 403 CONSENT_REQUIRED -> переключить на этот таб и показать блок consent
        if (error.message.includes('CONSENT_REQUIRED')) {
          setSearchParams(prev => {
            prev.set('tab', 'verification');
            return prev;
          });
          // Scroll to consent block
          setTimeout(() => {
            const consentElement = document.querySelector('.verification-lock');
            consentElement?.scrollIntoView({ behavior: 'smooth' });
          }, 100);
        }
      }
    });
  }

  if (isLoading) {
    return (
      <div className="tab-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загружается верификация...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="alert-circle" size={48} className="empty-state__icon" />
          <p className="empty-state__text">
            Ошибка загрузки верификации: {error.message}
          </p>
        </div>
      </div>
    );
  }

  // Check if we need consent - if there's no verification or it failed due to consent
  const needsConsent = !verification || verification.status === 'consent_required';

  if (needsConsent) {
    return (
      <div className="tab-content">
        <div className="verification-lock">
          <div className="verification-lock__icon">
            <Icon name="lock" size={48} />
          </div>
          <h3 className="verification-lock__title">
            Требуется согласие на обработку персональных данных
          </h3>
          <p className="verification-lock__text">
            Для проведения верификации кандидата необходимо получить его согласие на обработку персональных данных.
          </p>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleRequestConsent}
            disabled={consentMutation.isPending}
          >
            <Icon name={consentMutation.isPending ? "loader" : "mail"} size={16} />
            Получить согласие
          </button>
        </div>
      </div>
    );
  }

  if (!verification) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="shield" size={48} className="empty-state__icon" />
          <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>
            Верификация не проводилась
          </h3>
          <p className="empty-state__text">
            Запустите верификацию для проверки данных кандидата.
          </p>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={handleRunVerification}
            disabled={verifyMutation.isPending}
            style={{ marginTop: 'var(--space-3)' }}
          >
            <Icon name={verifyMutation.isPending ? "loader" : "shield"} size={16} />
            Запустить верификацию
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="tab-content">
      {verification.is_mock && (
        <div style={{
          background: 'var(--warning-bg)',
          border: '1px solid var(--warning-border)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-3) var(--space-4)',
          marginBottom: 'var(--space-4)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)'
        }}>
          <Icon name="alert-triangle" size={20} style={{ color: 'var(--warning-text)', flex: 'none' }} />
          <div style={{ fontSize: '15px', fontWeight: '500', color: 'var(--warning-text)' }}>
            <strong>Демо-данные.</strong> Реальная проверка по госреестрам не подключена.
            Не используйте для кадровых решений.
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-4)' }}>
        <h2 style={{ margin: 0, fontSize: '18px', fontWeight: '600' }}>Результаты верификации</h2>
        <button
          className="candidate-toolbar__btn"
          onClick={handleRunVerification}
          disabled={verifyMutation.isPending}
        >
          <Icon name={verifyMutation.isPending ? "loader" : "refresh-cw"} size={16} />
          Повторить верификацию
        </button>
      </div>

      {verification.blocks && verification.blocks.length > 0 ? (
        <div className="list-container">
          {verification.blocks.map((block, index) => (
            <div key={index} className="list-item">
              <div className="list-item__header">
                <h4 className="list-item__title">
                  {block.key?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || `Блок ${index + 1}`}
                </h4>
                <span className="list-item__meta">
                  Проверено: {new Date(verification.created_at).toLocaleDateString('ru')}
                </span>
              </div>
              <div className="list-item__content">
                {typeof block.data === 'string' ? (
                  <p>{block.data}</p>
                ) : (
                  <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: '14px' }}>
                    {JSON.stringify(block.data, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="search" size={24} className="empty-state__icon" />
          <p className="empty-state__text">Нет данных верификации</p>
        </div>
      )}
    </div>
  );
}