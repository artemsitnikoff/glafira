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
            const consentElement = document.querySelector('.verify-locked');
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
      <div className="verify-locked">
        <div className="verify-locked-ico">
          <Icon name="lock" size={36} />
        </div>
        <h3>Верификация недоступна</h3>
        <p>
          Кандидат пока не подписал согласие на обработку персональных данных (152-ФЗ).
          Запросите ПдН — после подписания Глафира автоматически проверит кандидата
          по всем реестрам и публичным источникам.
        </p>
        <button
          className="btn btn-primary btn-sm"
          onClick={handleRequestConsent}
          disabled={consentMutation.isPending}
        >
          <Icon name={consentMutation.isPending ? "loader" : "mail"} size={14} />
          Запросить ПдН
        </button>
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
    <div className="verification-tab">
      {verification.is_mock && (
        <div style={{
          background: '#FFF1C8',
          border: '1px solid var(--ark-yellow-500)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-3) var(--space-4)',
          marginBottom: 'var(--space-4)',
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)'
        }}>
          <Icon name="alert-triangle" size={20} style={{ color: 'var(--ark-yellow-600)', flex: 'none' }} />
          <div style={{ fontSize: '15px', fontWeight: '500', color: 'var(--ark-yellow-600)' }}>
            <strong>Демо-данные.</strong> Реальная проверка по госреестрам не подключена.
            Не используйте для кадровых решений.
          </div>
        </div>
      )}

      <div className="vf-meta">
        <span className="vf-meta-glyph">
          <Icon name="shield" size={14} />
        </span>
        Проверка выполнена {new Date(verification.created_at).toLocaleDateString('ru-RU')} · №PD-{verification.id?.slice(-8) || '12345678'}
        <button
          className="btn btn-sm btn-secondary"
          onClick={handleRunVerification}
          disabled={verifyMutation.isPending}
          style={{ marginLeft: 'auto' }}
        >
          <Icon name={verifyMutation.isPending ? "loader" : "refresh-cw"} size={14} />
          Повторить
        </button>
      </div>

      {verification.blocks && verification.blocks.length > 0 ? (
        <div>
          {verification.blocks.map((block, index) => (
            <section key={index} className="vf-block">
              <header className="vf-head">
                <div className="vf-head-left">
                  <div className="vf-icon">
                    <Icon name="search" size={16} />
                  </div>
                  <div className="vf-head-text">
                    <div className="vf-title">
                      {block.key?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || `Проверка ${index + 1}`}
                    </div>
                    <div className="vf-sources">
                      <span className="vf-src vf-src-api">API</span>
                      <span className="vf-src vf-src-db">База данных</span>
                    </div>
                  </div>
                </div>
                {/* Реальная проверка по госреестрам не подключена (интеграция позже).
                    НЕ выдаём mock-статус за вердикт — честная плашка «В разработке». */}
                <span className="vf-status vf-st-dev">
                  <Icon name="clock" size={11} />
                  В разработке
                </span>
              </header>
              <div className="vf-body">
                {typeof block.data === 'string' ? (
                  <p>{block.data}</p>
                ) : block.data && typeof block.data === 'object' ? (
                  Object.entries(block.data).map(([key, value]: [string, any]) => (
                    <div key={key} className="vf-kv">
                      <span className="vf-k">{key}:</span>
                      <span className="vf-v">{String(value)}</span>
                    </div>
                  ))
                ) : (
                  <p>Нет данных</p>
                )}
              </div>
            </section>
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