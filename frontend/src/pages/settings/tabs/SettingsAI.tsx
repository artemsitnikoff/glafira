import { useState } from 'react';
import { useSmartBaseIndexStatus, useReindexBase } from '@/api/hooks/useSmartSearch';
import { useAiModel, useUpdateAiModel } from '@/api/hooks/useAiModel';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card, FormRow, Select } from '../components/FormComponents';
import type { ApiError } from '@/api/aliases';
import './SettingsAI.css';

interface SettingsAIProps {
  readOnly?: boolean;
}

export function SettingsAI({ readOnly = false }: SettingsAIProps) {
  const [dirty, setDirty] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Хуки для индексации
  const { data: indexStatus, isLoading: isIndexLoading } = useSmartBaseIndexStatus();
  const reindexMutation = useReindexBase();

  // Хуки для LLM модели
  const { data: aiModelData, isLoading: isModelLoading } = useAiModel();
  const updateModelMutation = useUpdateAiModel();

  // Инициализация выбранной модели
  if (!selectedModel && aiModelData?.current) {
    setSelectedModel(aiModelData.current);
  }

  const handleReindex = async () => {
    if (readOnly || isIndexing || reindexMutation.isPending) return;

    try {
      await reindexMutation.mutateAsync();
    } catch (error) {
      // Ошибка отображается через reindexMutation.error в UI
    }
  };

  const handleModelChange = (value: string) => {
    setSelectedModel(value);
    setDirty(value !== aiModelData?.current);
    setSaveSuccess(false);
  };

  const handleSave = async () => {
    if (!dirty || !selectedModel || updateModelMutation.isPending) return;

    try {
      await updateModelMutation.mutateAsync({ model: selectedModel });
      setDirty(false);
      setSaveSuccess(true);
      // Убираем сообщение об успехе через 3 секунды
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (error) {
      // Ошибка отображается через updateModelMutation.error
    }
  };

  const fmt = (n: number) => n.toLocaleString('ru-RU');

  if (isIndexLoading || isModelLoading) {
    return <div className="set-content-inner"><div>Загрузка...</div></div>;
  }

  const isIndexing = indexStatus?.indexing === true;
  const canReindex = !readOnly && !isIndexing && !reindexMutation.isPending;

  const totalCandidates = indexStatus?.total_candidates || 0;
  const indexedCandidates = indexStatus?.indexed_candidates || 0;
  const pct = totalCandidates > 0 ? Math.round((indexedCandidates / totalCandidates) * 100) : 0;
  const pending = totalCandidates - indexedCandidates;

  return (
    <div className="set-content-inner">
      <PageHead
        title="Искусственный интеллект"
        subtitle="Семантический поиск по базе и модель, которая анализирует резюме"
        dirty={dirty}
        onSave={handleSave}
        saving={updateModelMutation.isPending}
      />

      {/* Семантический поиск */}
      <Card
        title="Семантический поиск по базе кандидатов"
        desc="Индексация резюме для умного поиска по смыслу, а не только по ключевым словам. Векторы резюме хранятся в системе и используются разделом «Умный подбор»."
      >
        <div className="ai-index">
          <div className="ai-index-stats">
            <div className="ai-stat">
              <div className="ai-stat-num t-mono">{fmt(totalCandidates)}</div>
              <div className="ai-stat-cap">Резюме в базе</div>
            </div>
            <div className="ai-stat-arrow">
              <Icon name="arrow-right" size={16} />
            </div>
            <div className="ai-stat">
              <div className="ai-stat-num t-mono">{fmt(indexedCandidates)}</div>
              <div className="ai-stat-cap">Проиндексировано · векторов</div>
            </div>
            <div className="ai-index-pillwrap">
              {pending === 0 ? (
                <span className="conn-pill ok">
                  <Icon name="check" size={12} />
                  Всё проиндексировано
                </span>
              ) : (
                <span className="conn-pill bad">
                  {isIndexing ? 'Индексируется…' : `${fmt(pending)} в очереди`}
                </span>
              )}
            </div>
          </div>

          <div className="ai-progress">
            <div className={`ai-progress-fill ${isIndexing ? 'busy' : ''}`} style={{ width: pct + '%' }} />
          </div>
          <div className="ai-progress-foot">
            <span className="t-mono">{pct}%</span>
            <span className="t-caption">
              {isIndexing ? 'Идёт переиндексация базы…' : 'Новые резюме индексируются автоматически'}
            </span>
          </div>

          <div className="ai-index-actions">
            <button
              className="btn btn-primary btn-sm"
              onClick={handleReindex}
              disabled={!canReindex}
              title={readOnly ? 'Только просмотр' : (!canReindex ? 'Индексация уже запущена' : undefined)}
            >
              <Icon name="refresh-cw" size={14} />
              {reindexMutation.isPending ? 'Запускается…' : isIndexing ? 'Переиндексация…' : 'Переиндексировать'}
            </button>
            <span className="t-caption">
              Новые резюме индексируются автоматически. Полная переиндексация нужна после смены настроек.
            </span>
          </div>
        </div>

        {reindexMutation.error && (
          <div className="error-banner" role="alert" style={{ marginTop: '16px' }}>
            {((reindexMutation.error as unknown as ApiError)?.error?.message) || 'Ошибка запуска индексации'}
          </div>
        )}

        <div className="ai-divider" />

        <div className="form-grid">
          <FormRow
            label="Модель эмбеддингов"
            hint="Преобразует текст резюме в векторы. Многоязычная модель, оптимизированная под русский язык. Зафиксирована."
          >
            <div className="ai-model-locked">
              <span className="ai-prov-ic" style={{ background: 'var(--ark-blue-50)', color: 'var(--ark-blue-700)' }}>
                <Icon name="database" size={16} />
              </span>
              <div className="ai-model-id t-mono">
                {indexStatus?.embed_model || 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'}
              </div>
              <span className="ai-soon-pill ai-soon-locked">
                <Icon name="lock" size={11} />
                Зафиксирована
              </span>
            </div>
          </FormRow>
        </div>
      </Card>

      {/* LLM модель */}
      <Card
        title="Модель LLM"
        desc="Настройка модели искусственного интеллекта для анализа резюме: квалификация откликов, оценка соответствия вакансии и саммари кандидата."
      >
        <div className="form-grid">
          <FormRow
            label="Основная модель"
            hint="Модель, которая оценивает резюме и квалифицирует отклики. Смена влияет на все новые анализы."
          >
            <div className="ai-model-select">
              <span className="ai-prov-ic" style={{ background: '#F3EEE7', color: '#B8551F' }}>
                <Icon name="cpu" size={16} />
              </span>
              <Select
                value={selectedModel}
                onChange={handleModelChange}
                options={aiModelData?.options || []}
                disabled={readOnly}
                placeholder="Загрузка..."
              />
            </div>
          </FormRow>
        </div>

        {/* Статус сохранения */}
        {saveSuccess && (
          <div style={{ marginTop: '16px', padding: '8px 12px', background: 'var(--success-bg)', border: '1px solid var(--success-border)', borderRadius: 'var(--radius-md)', color: 'var(--success-fg)', fontSize: '13px' }}>
            <Icon name="check" size={14} style={{ marginRight: '6px' }} />
            Модель сохранена
          </div>
        )}

        {updateModelMutation.error && (
          <div className="error-banner" role="alert" style={{ marginTop: '16px' }}>
            {((updateModelMutation.error as unknown as ApiError)?.error?.message) || 'Ошибка сохранения модели'}
          </div>
        )}
      </Card>
    </div>
  );
}