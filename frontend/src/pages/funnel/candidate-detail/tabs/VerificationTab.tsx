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

  // Получить иконку блока по ключу
  function getBlockIcon(key: string) {
    switch (key) {
      case 'inn':
        return <span className="vf-icon-letter">№</span>;
      case 'fssp':
        return <span className="vf-icon-letter">⚖</span>;
      case 'bankruptcy':
        return <span className="vf-icon-letter">Ю</span>;
      case 'registries':
        return <span className="vf-icon-letter">Р</span>;
      case 'public':
        return <span className="vf-icon-letter">★</span>;
      case 'ai_intel':
        return <span className="vf-icon-letter ai">✦</span>;
      case 'alimony':
        return <span className="vf-icon-letter">₽</span>;
      default:
        // Первая буква title или номер
        const firstLetter = key?.charAt(0)?.toUpperCase() || '#';
        return <span className="vf-icon-letter">{firstLetter}</span>;
    }
  }

  // Получить источники блока по данным
  function getBlockSources(sources: any[]) {
    if (!sources || !Array.isArray(sources)) {
      return (
        <>
          <span className="vf-src vf-src-api">API</span>
          <span className="vf-src vf-src-api">База данных</span>
        </>
      );
    }

    return sources.map((source, idx) => {
      const type = source.type || 'api';
      return (
        <span key={idx} className={`vf-src vf-src-${type}`}>
          {source.name}
        </span>
      );
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
    <div className="verify-tab">
      {verification.is_mock && (
        <div style={{
          background: 'var(--ark-yellow-100)',
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
        <span>
          Проверка выполнена <b>{new Date(verification.created_at).toLocaleDateString('ru-RU')} · 16:42</b>
          · по согласию №<b className="t-mono">PD-{verification.consent_number || verification.id?.slice(-8) || '000001'}/26</b>
        </span>
        <span style={{flex:1}}/>
        <button
          className="btn btn-sm btn-secondary"
          onClick={handleRunVerification}
          disabled={verifyMutation.isPending}
        >
          <Icon name={verifyMutation.isPending ? "loader" : "refresh-cw"} size={14} />
          Перепроверить
        </button>
      </div>

      {verification.blocks && verification.blocks.length > 0 ? (
        <div>
          {verification.blocks.map((block, index) => (
            <section key={index} className="vf-block">
              <header className="vf-head">
                <div className="vf-head-left">
                  <div className="vf-icon">
                    {getBlockIcon(block.key || '')}
                  </div>
                  <div className="vf-head-text">
                    <div className="vf-title">
                      {block.title || block.key?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || `Проверка ${index + 1}`}
                    </div>
                    <div className="vf-sources">
                      {getBlockSources(block.sources)}
                    </div>
                  </div>
                </div>
                <span className={`vf-status vf-st-${block.status || 'info'}`}>
                  {block.status === 'clean' && (
                    <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
                      <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                  {(block.status === 'warn' || block.status === 'risk' || block.status === 'info') && (
                    <span className="vf-dot"/>
                  )}
                  {block.status === 'clean' && 'Найден'}
                  {block.status === 'warn' && 'Внимание'}
                  {block.status === 'risk' && 'Риск'}
                  {block.status === 'info' && '1 связь'}
                  {!block.status && 'В разработке'}
                </span>
              </header>
              <div className="vf-body">
                {typeof block.data === 'string' ? (
                  <p>{block.data}</p>
                ) : block.data && typeof block.data === 'object' ? (
                  Object.entries(block.data).map(([key, value]: [string, any]) => (
                    <div key={key} className="vf-kv">
                      <span className="vf-k">{key}</span>
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