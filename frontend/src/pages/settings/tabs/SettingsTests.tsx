import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card } from '../components/FormComponents';
import { useTests, useTestDetail, type TestListItem } from '@/api/hooks/useTests';
import { TestConfig } from './TestConfig';
import './SettingsTests.css';

const KIND_LABEL: Record<string, string> = {
  single: 'Одиночный тест',
  blocked: 'Тест с блоками',
};

type Props = {
  readOnly?: boolean;
};

/** Экран 8 — каталог тестов (Настройки → Тесты) + вход в настройку теста (экран 9). */
export function SettingsTests({ readOnly = false }: Props) {
  const [configId, setConfigId] = useState<string | null>(null);
  const { data: tests, isLoading } = useTests();

  if (configId) {
    return <TestConfig testId={configId} onBack={() => setConfigId(null)} readOnly={readOnly} />;
  }

  return (
    <div className="set-content-inner st-tests">
      <PageHead
        title="Тесты"
        subtitle="Тесты способностей, которые кандидат проходит по ссылке. Результат приходит в карточку кандидата."
      />

      <Card
        title="Отдельные тесты"
        desc="Кандидат открывает тест по ссылке без авторизации — таймер запускается по нажатию «Начать»."
      >
        {isLoading ? (
          <div className="ts-empty-note">Загрузка тестов…</div>
        ) : !tests || tests.length === 0 ? (
          <div className="ts-empty-note">
            Тесты ещё не заведены для компании. Обратитесь к администратору Глафиры для их
            подключения.
          </div>
        ) : (
          <div className="ts-grid">
            {tests.map((t) => (
              <TestCatalogCard key={t.id} test={t} onConfigure={() => setConfigId(t.id)} />
            ))}
          </div>
        )}
      </Card>

      {/* «Наборы» (несколько тестов одной ссылкой) в бэке НЕТ — честная «Скоро»-заглушка (§0),
          без фейковых карточек-наборов и без мёртвых кнопок. */}
      <Card
        title="Наборы"
        desc="Несколько тестов одной ссылкой — кандидат проходит их подряд, с паузой между."
      >
        <div className="ts-soon">Скоро — наборы тестов пока в разработке.</div>
      </Card>
    </div>
  );
}

/** Карточка теста в каталоге — состав/длительность подтягивает GET /tests/{id}. */
function TestCatalogCard({ test, onConfigure }: { test: TestListItem; onConfigure: () => void }) {
  // Детали (длительность, блоки) — отдельным запросом; список даёт только счётчики.
  const { data: detail } = useTestDetail(test.id);
  const isActive = test.status === 'active';

  const durationMin = detail?.duration_sec ? Math.round(detail.duration_sec / 60) : null;
  const blockDurationMin =
    detail && detail.blocks.length
      ? detail.blocks.reduce((a, b) => a + Math.round(b.duration_sec / 60), 0)
      : null;
  const totalMin = durationMin ?? blockDurationMin;
  const blocks = detail?.blocks ?? [];

  return (
    <div className="ts-card">
      <div className="ts-card-top">
        <span className="ts-ico">
          <Icon name="clipboard" size={18} />
        </span>
        <div className="ts-card-ttl">
          <h3>{test.name}</h3>
          <div className="kind">{KIND_LABEL[test.kind] || test.kind}</div>
        </div>
        <span className={`ts-state ${isActive ? 'on' : 'draft'}`}>
          {isActive ? 'активен' : 'черновик'}
        </span>
      </div>

      <div className="ts-meta">
        <span>
          <b>{test.item_count}</b> заданий
        </span>
        {totalMin != null && (
          <span>
            <b>{totalMin}</b> мин
          </span>
        )}
        {blocks.length > 0 && (
          <span>
            <b>{blocks.length}</b> блока
          </span>
        )}
      </div>

      {blocks.length > 0 && (
        <div className="ts-blocks">{blocks.map((b) => b.title).join(' · ')}</div>
      )}

      <div className="ts-card-foot">
        <button className="btn btn-secondary btn-sm" onClick={onConfigure}>
          Настроить
        </button>
        <span className="assigned">назначен {test.assigned_count}×</span>
      </div>
    </div>
  );
}
