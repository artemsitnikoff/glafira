import { useState } from 'react';
import { useSmartBaseIndexStatus, useReindexBase } from '@/api/hooks/useSmartSearch';
import { useAiModel, useAiModelSearch, useUpdateAiModel } from '@/api/hooks/useAiModel';
import type { AiModelOption, UpdateAiModelRequest } from '@/api/hooks/useAiModel';
import { useDebounce } from '@/hooks/useDebounce';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card, FormRow } from '../components/FormComponents';
import type { ApiError } from '@/api/aliases';
import './SettingsAI.css';

interface SettingsAIProps {
  readOnly?: boolean;
}

/** Рубли: мелкие суммы — с большей точностью, чтобы не схлопнуть в «0». */
function formatRub(v: number): string {
  const digits = v < 1 ? 3 : 2;
  return v.toLocaleString('ru-RU', { maximumFractionDigits: digits });
}

/** Человеческая подпись размера контекстного окна. */
function ctxLabel(n: number): string {
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    const s = Number.isInteger(m) ? String(m) : m.toFixed(1).replace(/\.0$/, '');
    return `${s}M контекст`;
  }
  return `${Math.round(n / 1000)}k контекст`;
}

/** Строка одной модели: радио-метка + цена-за-резюме + контекст. */
function ModelOption({
  opt,
  selected,
  onSelect,
  disabled,
}: {
  opt: AiModelOption;
  selected: boolean;
  onSelect: () => void;
  disabled?: boolean;
}) {
  const hasPrice = opt.cost_rub != null;
  const showId = opt.value !== opt.label;
  const showCtx = opt.context_length != null;

  return (
    <label
      className={`ai-mo ${selected ? 'on' : ''} ${disabled ? 'disabled' : ''}`}
      onClick={() => !disabled && onSelect()}
    >
      <span className={`rd ${selected ? 'on' : ''}`}>
        <span />
      </span>
      <div className="ai-mo-main">
        <div className="ai-mo-label">{opt.label}</div>
        {(showId || showCtx) && (
          <div className="ai-mo-sub">
            {showId && <span className="ai-mo-id t-mono">{opt.value}</span>}
            {showCtx && <span className="ai-mo-ctx">{ctxLabel(opt.context_length as number)}</span>}
          </div>
        )}
      </div>
      <div className="ai-mo-price">
        {hasPrice ? (
          <>
            <span className="ai-mo-price-val">≈ {formatRub(opt.cost_rub as number)} ₽</span>
            <span className="ai-mo-price-cap">за резюме</span>
          </>
        ) : (
          <span className="ai-mo-price-na">цена недоступна</span>
        )}
      </div>
    </label>
  );
}

export function SettingsAI({ readOnly = false }: SettingsAIProps) {
  const [selectedModel, setSelectedModel] = useState<string>('');
  // Метаданные модели, выбранной ВНЕ рекомендованного шорт-листа (из поиска).
  const [selectedExtra, setSelectedExtra] = useState<AiModelOption | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [search, setSearch] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Хуки для индексации
  const { data: indexStatus, isLoading: isIndexLoading } = useSmartBaseIndexStatus();
  const reindexMutation = useReindexBase();

  // Хуки для LLM модели
  const { data: aiModelData, isLoading: isModelLoading } = useAiModel();
  const updateModelMutation = useUpdateAiModel();

  // Поиск по всем моделям OpenRouter (debounce 300мс)
  const debouncedSearch = useDebounce(search, 300);
  const searchQuery = useAiModelSearch(debouncedSearch);

  // Инициализация выбранной модели из текущей
  if (!selectedModel && aiModelData?.current) {
    setSelectedModel(aiModelData.current);
  }

  const options = aiModelData?.options ?? [];
  const current = aiModelData?.current ?? '';
  const inShortlist = options.some((o) => o.value === selectedModel);

  const modelChanged = !!selectedModel && selectedModel !== current;
  const keyChanged = apiKey.trim().length > 0;
  const dirty = modelChanged || keyChanged;

  const handleReindex = async () => {
    if (readOnly || isIndexing || reindexMutation.isPending) return;
    try {
      await reindexMutation.mutateAsync();
    } catch {
      // Ошибка отображается через reindexMutation.error в UI
    }
  };

  const selectModel = (opt: AiModelOption) => {
    if (readOnly) return;
    setSelectedModel(opt.value);
    setSaveSuccess(false);
    // Если модели нет в шорт-листе — запоминаем её метаданные для отдельной строки.
    setSelectedExtra(options.some((o) => o.value === opt.value) ? null : opt);
  };

  const handleSave = async () => {
    if (!dirty || !selectedModel || updateModelMutation.isPending) return;

    const body: UpdateAiModelRequest = { model: selectedModel };
    if (apiKey.trim()) body.openrouter_api_key = apiKey.trim();

    try {
      await updateModelMutation.mutateAsync(body);
      setApiKey('');
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch {
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

  // Строка «выбрана другая модель» — для выбора вне шорт-листа.
  const customOption: AiModelOption | null =
    !inShortlist && selectedModel
      ? selectedExtra && selectedExtra.value === selectedModel
        ? selectedExtra
        : { value: selectedModel, label: selectedModel }
      : null;

  const searchReady = debouncedSearch.trim().length >= 2;
  const searchResults = searchQuery.data?.options ?? [];

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
        <FormRow
          label="Основная модель"
          hint="Модель, которая оценивает резюме и квалифицирует отклики. Смена влияет на все новые анализы."
        >
          {options.length > 0 ? (
            <div className="ai-model-list">
              {options.map((o) => (
                <ModelOption
                  key={o.value}
                  opt={o}
                  selected={selectedModel === o.value}
                  onSelect={() => selectModel(o)}
                  disabled={readOnly}
                />
              ))}
            </div>
          ) : (
            <div className="t-caption">Рекомендованные модели недоступны. Задайте ключ OpenRouter или найдите модель поиском ниже.</div>
          )}
        </FormRow>

        {customOption && (
          <div className="ai-custom-pick">
            <div className="ai-custom-pick-cap">Выбрана другая модель</div>
            <div className="ai-model-list">
              <ModelOption opt={customOption} selected onSelect={() => {}} />
            </div>
          </div>
        )}

        {/* Честная оговорка по оценке стоимости (§0) */}
        <div className="ai-cost-note">
          <Icon name="info" size={13} />
          <span>
            ≈ оценка при ~4500 входных и ~900 выходных токенах и курсе ~100 ₽/$. Это ориентир, а не точный
            биллинг: фактическая стоимость зависит от длины резюме и тарифов OpenRouter.
          </span>
        </div>

        {/* Поиск по всем моделям OpenRouter */}
        <div className="ai-other">
          <div className="ai-other-head">Другая модель</div>
          <div className="ai-other-sub">Найдите любую модель OpenRouter по названию и выберите её.</div>

          <div className="txt ai-search">
            <Icon name="search" size={14} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Например: gpt-4o, gemini, llama, deepseek…"
              disabled={readOnly}
            />
            {searchQuery.isFetching && <Icon name="loader" size={14} className="ai-search-spin" />}
          </div>

          {searchReady && (
            <div className="ai-search-results">
              {searchQuery.isLoading ? (
                <div className="ai-search-note">Поиск…</div>
              ) : searchQuery.error ? (
                <div className="error-banner" role="alert">
                  {((searchQuery.error as unknown as ApiError)?.error?.message) || 'Ошибка поиска моделей'}
                </div>
              ) : searchResults.length === 0 ? (
                <div className="ai-search-note">Ничего не найдено</div>
              ) : (
                <div className="ai-model-list">
                  {searchResults.map((o) => (
                    <ModelOption
                      key={o.value}
                      opt={o}
                      selected={selectedModel === o.value}
                      onSelect={() => selectModel(o)}
                      disabled={readOnly}
                    />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="ai-divider" />

        {/* Ключ OpenRouter */}
        <FormRow
          label="Ключ OpenRouter API"
          hint="Нужен для live-цен и работы моделей. Оставьте поле пустым — текущий ключ не изменится."
        >
          <div className="ai-key-row">
            <div className="txt ai-key-input">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setSaveSuccess(false);
                }}
                placeholder={aiModelData?.has_openrouter_key ? '•••••••• (ключ задан)' : 'sk-or-…'}
                disabled={readOnly}
                autoComplete="off"
              />
            </div>
            {aiModelData?.has_openrouter_key ? (
              <span className="conn-pill ok">
                <Icon name="check" size={12} />
                Ключ задан
              </span>
            ) : (
              <span className="conn-pill bad">Ключ не задан</span>
            )}
          </div>
        </FormRow>

        {/* Статус сохранения */}
        {saveSuccess && (
          <div className="ai-save-ok">
            <Icon name="check" size={14} />
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
