import { useQueryClient } from '@tanstack/react-query';
import { useSmartBaseIndexStatus, useReindexBase } from '@/api/hooks/useSmartSearch';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card } from '../components/FormComponents';
import type { ApiError } from '@/api/aliases';

interface SettingsAIProps {
  readOnly?: boolean;
}

export function SettingsAI({ readOnly = false }: SettingsAIProps) {
  const queryClient = useQueryClient();
  const { data: indexStatus, isLoading } = useSmartBaseIndexStatus();
  const reindexMutation = useReindexBase();

  const handleReindex = async () => {
    try {
      await reindexMutation.mutateAsync();
      // После успешного запуска переиндексации инвалидируем статус для обновления
      queryClient.invalidateQueries({ queryKey: ['smart', 'base', 'index-status'] });
    } catch (error) {
      // Ошибка отображается через reindexMutation.error в UI
    }
  };

  if (isLoading) {
    return <div className="set-content-inner"><div>Загрузка...</div></div>;
  }

  const isIndexing = indexStatus?.indexing === true;
  const canReindex = !readOnly && !isIndexing;

  return (
    <div className="set-content-inner">
      <PageHead
        title="Настройки AI"
        subtitle="Управление искусственным интеллектом и семантическим поиском"
      />

      <Card
        title="Семантический поиск по базе кандидатов"
        desc="Индексация резюме для умного поиска по смыслу, а не только по ключевым словам"
      >
        <div className="ai-index-section">
          {indexStatus ? (
            <div className="ai-index-status">
              <div className="ai-index-info">
                <span className="ai-index-text">
                  Проиндексировано {indexStatus.indexed_candidates} из {indexStatus.total_candidates}
                </span>
                {isIndexing && (
                  <span className="ai-index-progress">
                    <Icon name="loader" size={14} />
                    идёт индексация...
                  </span>
                )}
                {!isIndexing && indexStatus.indexed_candidates < indexStatus.total_candidates && (
                  <span className="ai-index-note">
                    (часть кандидатов без резюме не индексируется)
                  </span>
                )}
              </div>
              {indexStatus.indexed_candidates > 0 && indexStatus.total_candidates > 0 && (
                <div className="ai-index-bar">
                  <div
                    className="ai-index-fill"
                    style={{
                      width: `${Math.min(100, (indexStatus.indexed_candidates / indexStatus.total_candidates) * 100)}%`
                    }}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="ai-index-info">
              <span className="ai-index-text">Статус индексации недоступен</span>
            </div>
          )}

          <div className="ai-index-actions">
            <button
              className="btn btn-primary"
              disabled={!canReindex || reindexMutation.isPending}
              onClick={canReindex ? handleReindex : undefined}
              title={readOnly ? 'Только просмотр' : (!canReindex ? 'Индексация уже запущена' : undefined)}
            >
              {reindexMutation.isPending ? (
                <>
                  <Icon name="loader" size={14} />
                  Запускаю...
                </>
              ) : (
                'Проиндексировать базу'
              )}
            </button>
          </div>

          {reindexMutation.isSuccess && isIndexing && (
            <div className="ai-index-done" role="status">
              <Icon name="loader" size={14} /> Индексация запущена…
            </div>
          )}
          {reindexMutation.isSuccess && !isIndexing && (
            <div className="ai-index-done" role="status">
              <Icon name="check" size={14} /> Индексация выполнена — проиндексировано{' '}
              {indexStatus?.indexed_candidates} из {indexStatus?.total_candidates}
            </div>
          )}

          {reindexMutation.error && (
            <div className="error-banner" role="alert">
              {((reindexMutation.error as unknown as ApiError)?.error?.message) || 'Ошибка запуска индексации'}
            </div>
          )}
        </div>
      </Card>

      <Card
        title="Модель LLM"
        desc="Настройка модели искусственного интеллекта для анализа резюме"
      >
        <div className="ai-model-section">
          <div className="form-field">
            <label className="field-label">Основная модель</label>
            <select className="field-input" disabled value={indexStatus?.model || ''}>
              {indexStatus?.model ? (
                <option value={indexStatus.model}>{indexStatus.model}</option>
              ) : (
                <option value="">Загрузка...</option>
              )}
            </select>
            <div className="field-hint">Смена модели — скоро</div>
          </div>

          {indexStatus?.embed_model && (
            <div className="ai-model-info">
              <span className="ai-model-label">Модель эмбеддингов:</span>
              <span className="ai-model-value">{indexStatus.embed_model} (фиксирована)</span>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}