import { useSearchParams } from 'react-router-dom';
import { Icon } from '@/components/ui/Icon';
import { useVerification } from '@/api/hooks/useVerification';
import { useRequestConsent, useRunVerification, useConfirmConsentSigned } from '@/api/mutations/candidateDetail';
import type { ApiError } from '@/api/aliases';

// Человекочитаемые подписи полей блоков верификации (ключи из backend verify.py).
const FIELD_LABELS: Record<string, string> = {
  phone: 'Телефон', email: 'Email', name: 'ФИО',
  original: 'Указано', standardized: 'Стандартизовано', provider: 'Оператор',
  region: 'Регион', valid: 'Валидно', type: 'Тип',
  surname: 'Фамилия', patronymic: 'Отчество', gender: 'Пол',
  gender_match: 'Пол совпадает', parsed_correctly: 'Разобрано корректно',
  summary: 'Вывод', flags: 'Замечания', confidence: 'Уверенность',
  note: 'Примечание', status: 'Статус',
};
// Технические поля, которые не показываем (коды качества DaData и т.п.).
const HIDDEN_KEYS = new Set(['qc']);

function vfLabel(key: string): string {
  return FIELD_LABELS[key] || key;
}

// Привести значение к читаемой строке (булево → Да/Нет, массив → через «; », null → «—»).
function vfScalar(value: any): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (Array.isArray(value)) {
    return value.length
      ? value.map(v => (v && typeof v === 'object' ? JSON.stringify(v) : String(v))).join('; ')
      : '—';
  }
  return String(value);
}

// URL для показа: без протокола и финального слэша.
function prettyUrl(url: string): string {
  return String(url || '').replace(/^https?:\/\//, '').replace(/\/$/, '');
}

// Блок «Публичная экспертиза» — карточки найденных профилей (GitHub/Habr/StackExchange/TGStat).
function renderProfiles(data: any) {
  if (data?.pending) {
    return (
      <p className="vf-searching">
        <Icon name="loader" size={14} /> Идёт разведка по открытым источникам…
      </p>
    );
  }
  const profiles: any[] = Array.isArray(data?.profiles) ? data.profiles : [];
  if (!profiles.length) {
    return <p className="vf-empty">{data?.note || 'Профили не найдены'}</p>;
  }
  return (
    <div className="vf-profiles">
      <div className="vf-profiles-cap">Найдены профили</div>
      {profiles.map((p, i) => (
        <a key={i} className="vf-profile" href={p.url} target="_blank" rel="noopener noreferrer">
          <span className="vf-profile-platform">{p.platform || '—'}</span>
          {p.handle && <span className="vf-profile-handle">{p.handle}</span>}
          {p.stats && <span className="vf-profile-stats">{p.stats}</span>}
        </a>
      ))}
    </div>
  );
}

// Блок «Упоминания» — цитаты со ссылкой на источник.
function renderMentions(data: any) {
  if (data?.pending) {
    return (
      <p className="vf-searching">
        <Icon name="loader" size={14} /> Идёт разведка по открытым источникам…
      </p>
    );
  }
  const mentions: any[] = Array.isArray(data?.mentions) ? data.mentions : [];
  if (!mentions.length) {
    return <p className="vf-empty">{data?.note || 'Упоминаний не найдено'}</p>;
  }
  return (
    <div className="vf-mentions">
      {mentions.map((m, i) => (
        <div key={i} className="vf-mention">
          {m.quote && <p className="vf-mention-quote">«{m.quote}»</p>}
          <a className="vf-mention-src" href={m.url} target="_blank" rel="noopener noreferrer">
            {prettyUrl(m.url)}
          </a>
        </div>
      ))}
    </div>
  );
}

type Props = {
  candidateId?: string;
  candidate?: any;
  /** Подписано ли согласие на обработку ПдН (Consent.status='signed'). Верификация без него невозможна (152-ФЗ). */
  hasPdn?: boolean;
  fromPool?: boolean;
};

export function VerificationTab({ candidateId, candidate, hasPdn }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const [, setSearchParams] = useSearchParams();
  const { data: verification, isLoading, error, refetch } = useVerification(actualCandidateId);
  const consentMutation = useRequestConsent(actualCandidateId);
  const verifyMutation = useRunVerification(actualCandidateId);
  const confirmMutation = useConfirmConsentSigned(actualCandidateId);

  // Подписанное согласие: проп из application/candidate (has_pdn = exists Consent signed),
  // либо рекрутёр только что подтвердил вручную (confirmMutation).
  const consentSigned = (hasPdn ?? candidate?.has_pdn ?? false) || confirmMutation.isSuccess;
  const runErrorCode = (verifyMutation.error as unknown as ApiError)?.error?.code;

  function handleRequestConsent() {
    consentMutation.mutate({
      channel: 'email',
    });
  }

  function handleConfirmSigned() {
    // Рекрутёр под свою ответственность отмечает согласие подписанным → сразу верификация.
    confirmMutation.mutate();
  }

  function handleRunVerification() {
    verifyMutation.mutate(undefined, {
      onError: (err) => {
        // 403 CONSENT_REQUIRED -> остаёмся на табе верификации (покажется блок «Запросить ПдН»)
        if ((err as unknown as ApiError)?.error?.code === 'CONSENT_REQUIRED') {
          setSearchParams(prev => {
            prev.set('tab', 'verification');
            return prev;
          });
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
      case 'public_expertise':
        return <span className="vf-icon-letter ai">★</span>;
      case 'mentions':
        return <span className="vf-icon-letter ai">“</span>;
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

  // Реальная ошибка загрузки (отсутствие верификации НЕ ошибка — хук вернёт null на 404).
  if (error) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="alert-circle" size={48} className="empty-state__icon" />
          <p className="empty-state__text">
            Ошибка загрузки верификации: {(error as unknown as ApiError)?.error?.message || 'неизвестная ошибка'}
          </p>
          <button
            className="candidate-toolbar__btn candidate-toolbar__btn--primary"
            onClick={() => refetch()}
            style={{ marginTop: 'var(--space-3)' }}
          >
            <Icon name="refresh-cw" size={16} />
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  // Нет подписанного согласия → запросить у кандидата ИЛИ отметить подписанным (ответственность рекрутёра).
  if (!consentSigned) {
    return (
      <div className="verify-locked">
        <div className="verify-locked-ico">
          <Icon name="lock" size={36} />
        </div>
        <h3>Требуется согласие на обработку ПдН</h3>
        <p>
          Запросите согласие у кандидата — или отметьте, что оно уже получено
          (например, подписано на бумаге). Согласие подтверждает рекрутёр под свою
          ответственность; после подтверждения Глафира сразу проверит кандидата.
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={handleRequestConsent}
            disabled={consentMutation.isPending || confirmMutation.isPending}
          >
            <Icon name={consentMutation.isPending ? "loader" : "mail"} size={14} />
            {consentMutation.isSuccess ? 'Запрос отправлен' : 'Запросить ПдН'}
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleConfirmSigned}
            disabled={confirmMutation.isPending}
          >
            <Icon name={confirmMutation.isPending ? "loader" : "check"} size={14} />
            {confirmMutation.isPending ? 'Проверяем…' : 'ПдН подписан'}
          </button>
        </div>
        {confirmMutation.isError && (
          <p className="empty-state__text" style={{ color: 'var(--ark-red-600)', marginTop: 'var(--space-2)' }} role="alert">
            {(confirmMutation.error as unknown as ApiError)?.error?.message || 'Не удалось подтвердить согласие'}
          </p>
        )}
        {consentMutation.isError && (
          <p className="empty-state__text" style={{ color: 'var(--ark-red-600)', marginTop: 'var(--space-2)' }} role="alert">
            {(consentMutation.error as unknown as ApiError)?.error?.message || 'Не удалось отправить запрос'}
          </p>
        )}
      </div>
    );
  }

  // Согласие подписано, но верификации ещё нет → можно запустить вручную.
  if (!verification) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="shield" size={48} className="empty-state__icon" />
          <h3 style={{ margin: '0 0 var(--space-2) 0', fontSize: '16px', fontWeight: '600' }}>
            Верификация не проводилась
          </h3>
          <p className="empty-state__text">
            Согласие получено. Запустите верификацию — или она пройдёт автоматически
            при следующей AI-оценке.
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
          {verifyMutation.isError && runErrorCode !== 'CONSENT_REQUIRED' && (
            <p className="empty-state__text" style={{ color: 'var(--ark-red-600)', marginTop: 'var(--space-2)' }} role="alert">
              {(verifyMutation.error as unknown as ApiError)?.error?.message || 'Не удалось запустить верификацию'}
            </p>
          )}
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
          Проверка выполнена <b>{new Date(verification.created_at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })}</b>
          {verification.consent_number && (
            <> · по согласию №<b className="t-mono">{verification.consent_number}</b></>
          )}
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
                  {block.status === 'clean' && 'Проверено'}
                  {block.status === 'warn' && 'Внимание'}
                  {block.status === 'risk' && 'Риск'}
                  {block.status === 'info' && 'Инфо'}
                  {!block.status && 'В разработке'}
                </span>
              </header>
              <div className="vf-body">
                {block.key === 'public_expertise' ? (
                  renderProfiles(block.data)
                ) : block.key === 'mentions' ? (
                  renderMentions(block.data)
                ) : typeof block.data === 'string' ? (
                  <p>{block.data}</p>
                ) : block.data && typeof block.data === 'object' && Object.keys(block.data).length > 0 ? (
                  Object.entries(block.data)
                    .filter(([key]) => !HIDDEN_KEYS.has(key))
                    .map(([key, value]: [string, any]) => {
                      // Вложенный объект (напр. phone/email/name) → группа с под-полями.
                      if (value && typeof value === 'object' && !Array.isArray(value)) {
                        return (
                          <div key={key} className="vf-group">
                            <div className="vf-group-title">{vfLabel(key)}</div>
                            {Object.entries(value)
                              .filter(([k]) => !HIDDEN_KEYS.has(k))
                              .map(([k, v]: [string, any]) => (
                                <div key={k} className="vf-kv">
                                  <span className="vf-k">{vfLabel(k)}</span>
                                  <span className="vf-v">{vfScalar(v)}</span>
                                </div>
                              ))}
                          </div>
                        );
                      }
                      return (
                        <div key={key} className="vf-kv">
                          <span className="vf-k">{vfLabel(key)}</span>
                          <span className="vf-v">{vfScalar(value)}</span>
                        </div>
                      );
                    })
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

      {verification.blocks?.some(b => b.key === 'public_expertise' || b.key === 'mentions') && (
        <div className="vf-firewall">
          <Icon name="shield" size={13} />
          <span>
            Разведка по открытым источникам на основе согласия кандидата (ФИО, контакты,
            город, должность). В отчёт включены только публичные находки с источником (URL);
            сами контактные данные в отчёте не публикуются.
          </span>
        </div>
      )}
    </div>
  );
}