import { useState, useRef, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { SOURCE_CONFIG } from '@/lib/source-colors';
import {
  useParseFile,
  usePreviewImport,
  useExecuteImport,
  useImportJob,
  type ParseResponse,
  type PreviewResponse,
  type PreviewRow,
  type ColumnMapping,
  type FieldKey,
  type DedupMode,
} from '@/api/hooks/useCandidateImport';
import './ImportCandidates.css';

interface Props {
  onClose: () => void;
  onDone: () => void;
}

// RU-метки для полей
const FIELD_LABELS: Record<FieldKey, string> = {
  name: 'Имя*',
  phone: 'Телефон',
  email: 'Email',
  city: 'Город',
  age: 'Возраст',
  salary: 'Зарплата',
  source: 'Источник',
  position: 'Должность',
  company: 'Компания',
  experience: 'Опыт',
  comment: 'Комментарий',
  resume_url: 'Резюме-ссылка',
  skip: '— Не импортировать —',
};

const FIELD_OPTIONS: { id: FieldKey; label: string }[] = Object.entries(FIELD_LABELS).map(([id, label]) => ({
  id: id as FieldKey,
  label,
}));

type Step = 1 | 2 | 3 | 4;

export function ImportCandidatesWizard({ onClose, onDone }: Props) {
  // Состояние визарда
  const [currentStep, setCurrentStep] = useState<Step>(1);

  // Шаг 1: Загрузка файла
  const [file, setFile] = useState<File | null>(null);
  const [parseData, setParseData] = useState<ParseResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Шаг 2: Маппинг колонок
  const [mapping, setMapping] = useState<ColumnMapping>({});

  // Шаг 3: Превью
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [dedupMode, setDedupMode] = useState<DedupMode>('skip');
  const [detailCandidate, setDetailCandidate] = useState<PreviewRow | null>(null);

  // Шаг 4: Выполнение
  const [jobId, setJobId] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // API hooks
  const parseFile = useParseFile();
  const previewImport = usePreviewImport();
  const executeImport = useExecuteImport();
  const { data: jobData } = useImportJob(jobId, currentStep === 4);

  // Обработчики
  const handleFileSelect = async (selectedFile: File) => {
    setFileError(null);

    if (!selectedFile.name.match(/\.(xlsx?|xls)$/i)) {
      setFileError('Поддерживаются только файлы .xlsx и .xls');
      return;
    }

    setFile(selectedFile);

    try {
      const result = await parseFile.mutateAsync(selectedFile);
      setParseData(result);

      // Инициализируем маппинг из auto_mapping
      setMapping(result.auto_mapping as ColumnMapping);
    } catch (error) {
      setFile(null);
      setParseData(null);
      setFileError('Не удалось прочитать файл');
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect(droppedFile);
    }
  };

  const handleReplaceFile = () => {
    setFile(null);
    setParseData(null);
    setFileError(null);
    fileInputRef.current?.click();
  };

  const handleMappingChange = (column: string, fieldKey: FieldKey) => {
    setMapping(prev => {
      const newMapping = { ...prev };

      // Если назначаем поле, которое уже занято, освобождаем предыдущую колонку
      if (fieldKey !== 'skip') {
        Object.keys(newMapping).forEach(col => {
          if (newMapping[col] === fieldKey) {
            newMapping[col] = 'skip';
          }
        });
      }

      newMapping[column] = fieldKey;
      return newMapping;
    });
  };

  const isValidMapping = () => {
    const mappedFields = Object.values(mapping);
    const hasName = mappedFields.includes('name');
    const hasContact = mappedFields.includes('phone') || mappedFields.includes('email');
    return hasName && hasContact;
  };

  const handlePreview = async () => {
    if (!file || !isValidMapping()) return;
    setActionError(null);

    try {
      const result = await previewImport.mutateAsync({
        file,
        mapping,
        dedup_mode: dedupMode,
      });
      setPreviewData(result);
      setCurrentStep(3);
    } catch {
      setActionError('Не удалось построить превью. Проверьте файл и попробуйте ещё раз.');
    }
  };

  const handleExecute = async () => {
    if (!file) return;
    setActionError(null);

    try {
      const result = await executeImport.mutateAsync({
        file,
        mapping,
        dedup_mode: dedupMode,
      });
      setJobId(result.job_id);
      setCurrentStep(4);
    } catch {
      setActionError('Не удалось запустить импорт. Попробуйте ещё раз.');
    }
  };

  const reset = () => {
    setCurrentStep(1);
    setFile(null);
    setParseData(null);
    setMapping({});
    setPreviewData(null);
    setDedupMode('skip');
    setDetailCandidate(null);
    setJobId(null);
    setFileError(null);
    setActionError(null);
  };

  const getStepClass = (step: Step) => {
    if (step === currentStep) return 'current';
    if (step < currentStep) return 'completed';
    return 'upcoming';
  };

  return (
    <div className="import-wizard">
      {/* Шапка визарда */}
      <div className="iw-header">
        <div className="iw-header-left">
          <h1 className="iw-title">Импорт кандидатов из файла</h1>

          {/* Индикатор шагов */}
          <div className="iw-steps">
            <div className={`iw-step ${getStepClass(1)}`}>
              <div className="iw-step-circle">
                {currentStep > 1 ? <Icon name="check" size={12} /> : '1'}
              </div>
              <span className="iw-step-label">Загрузка</span>
            </div>
            <div className="iw-step-line" />
            <div className={`iw-step ${getStepClass(2)}`}>
              <div className="iw-step-circle">
                {currentStep > 2 ? <Icon name="check" size={12} /> : '2'}
              </div>
              <span className="iw-step-label">Колонки</span>
            </div>
            <div className="iw-step-line" />
            <div className={`iw-step ${getStepClass(3)}`}>
              <div className="iw-step-circle">
                {currentStep > 3 ? <Icon name="check" size={12} /> : '3'}
              </div>
              <span className="iw-step-label">Превью</span>
            </div>
            <div className="iw-step-line" />
            <div className={`iw-step ${getStepClass(4)}`}>
              <div className="iw-step-circle">4</div>
              <span className="iw-step-label">Готово</span>
            </div>
          </div>
        </div>

        <button className="iw-close" onClick={onClose}>
          <Icon name="x" size={20} />
        </button>
      </div>

      {/* Содержимое */}
      <div className="iw-content">
        {/* Шаг 1: Загрузка файла */}
        {currentStep === 1 && (
          <div className="iw-step-content">
            {!file && (
              <>
                <div
                  className="iw-dropzone"
                  onDrop={handleDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => fileInputRef.current?.click()}
                >
                  {parseFile.isPending ? (
                    <div className="iw-loading">
                      <div className="iw-brand-char">💃</div>
                      <p>Глафира читает файл…</p>
                    </div>
                  ) : (
                    <>
                      <Icon name="upload" size={48} style={{ color: 'var(--fg-3)' }} />
                      <h3>Перетащите Excel-файл с кандидатами</h3>
                      <p>или нажмите для выбора</p>
                      <div className="iw-hint">
                        Поддерживаются выгрузки из hh, Потока, Хантфлоу и других систем
                      </div>
                      <button className="btn btn-primary" type="button">
                        Выбрать файл
                      </button>
                    </>
                  )}
                </div>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={(e) => {
                    const selectedFile = e.target.files?.[0];
                    if (selectedFile) handleFileSelect(selectedFile);
                  }}
                  style={{ display: 'none' }}
                />
              </>
            )}

            {(parseFile.isError || fileError) && (
              <div className="iw-error-state">
                <Icon name="alert-triangle" size={36} style={{ color: 'var(--error-fg)' }} />
                <h3>Не удалось прочитать файл</h3>
                <p>{fileError || 'Поддерживаются только .xlsx и .xls'}</p>
                <button className="btn btn-secondary" onClick={() => {
                  setFileError(null);
                  fileInputRef.current?.click();
                }}>
                  Выбрать другой файл
                </button>
              </div>
            )}

            {file && parseData && (
              <div className="iw-file-card">
                <div className="iw-file-info">
                  <Icon name="file" size={24} style={{ color: 'var(--accent)' }} />
                  <div>
                    <div className="iw-file-name">{file.name}</div>
                    <div className="iw-file-stats">
                      Найдено {parseData.row_count} строк · {parseData.columns.length} колонок
                    </div>
                  </div>
                </div>

                <div className="iw-file-columns">
                  {parseData.columns.map((col, i) => (
                    <span key={i} className="iw-column-chip">{col}</span>
                  ))}
                </div>

                <div className="iw-file-actions">
                  <button className="btn btn-secondary btn-sm" onClick={handleReplaceFile}>
                    Заменить файл
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={() => setCurrentStep(2)}
                  >
                    Далее → Колонки
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Шаг 2: Сопоставление колонок */}
        {currentStep === 2 && parseData && (
          <div className="iw-step-content">
            <div className="iw-glafira-hint">
              <div className="iw-brand-char">💃</div>
              <p>Глафира распознала колонки автоматически — проверьте и поправьте, если нужно</p>
            </div>

            {/* Индикатор обязательных полей */}
            <div className="iw-required-fields">
              <div className={`iw-req-field ${Object.values(mapping).includes('name') ? 'valid' : 'invalid'}`}>
                Имя {Object.values(mapping).includes('name') && <Icon name="check" size={14} />}
              </div>
              <span>·</span>
              <div className={`iw-req-field ${
                Object.values(mapping).includes('phone') || Object.values(mapping).includes('email') ? 'valid' : 'invalid'
              }`}>
                Контакт (телефон/email) {(Object.values(mapping).includes('phone') || Object.values(mapping).includes('email')) && <Icon name="check" size={14} />}
              </div>
            </div>

            {/* Таблица сопоставления */}
            <div className="iw-mapping-table">
              {parseData.columns.map((column) => {
                const currentMapping = mapping[column] || 'skip';
                const isAutoMapped = parseData.auto_mapping[column] && parseData.auto_mapping[column] !== 'skip';
                const samples = parseData.samples[column] || [];

                return (
                  <div key={column} className="iw-mapping-row">
                    <div className="iw-column-info">
                      <div className="iw-column-name">{column}</div>
                      <div className="iw-column-samples">
                        {samples.slice(0, 3).map((sample, i) => (
                          <span key={i} className="iw-sample">{sample}</span>
                        ))}
                      </div>
                    </div>

                    <Icon name="arrow-right" size={16} style={{ color: 'var(--fg-3)' }} />

                    <div className="iw-field-select">
                      <select
                        value={currentMapping}
                        onChange={(e) => handleMappingChange(column, e.target.value as FieldKey)}
                        className={isAutoMapped && currentMapping !== 'skip' ? 'auto-mapped' : ''}
                      >
                        {FIELD_OPTIONS.map(option => {
                          const isOccupied = option.id !== 'skip' && option.id !== currentMapping && Object.values(mapping).includes(option.id);
                          return (
                            <option
                              key={option.id}
                              value={option.id}
                              disabled={isOccupied}
                            >
                              {option.label}{isOccupied ? ' (занято)' : ''}
                            </option>
                          );
                        })}
                      </select>
                      {isAutoMapped && currentMapping !== 'skip' && (
                        <div className="iw-auto-badge">
                          <Icon name="check" size={12} /> распознано
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>

            {!isValidMapping() && (
              <div className="iw-validation-hint">
                Сопоставьте Имя и хотя бы один контакт
              </div>
            )}

            {actionError && <div className="iw-validation-hint">{actionError}</div>}

            <div className="iw-step-actions">
              <button className="btn btn-secondary" onClick={() => setCurrentStep(1)}>
                ← Назад
              </button>
              <button
                className="btn btn-primary"
                onClick={handlePreview}
                disabled={!isValidMapping() || previewImport.isPending}
              >
                {previewImport.isPending ? 'Обработка…' : 'Далее → Превью'}
              </button>
            </div>
          </div>
        )}

        {/* Шаг 3: Превью */}
        {currentStep === 3 && previewData && (
          <div className="iw-step-content">
            {/* Статистика */}
            <div className="iw-stats-cards">
              <div className="iw-stat-card neutral">
                <div className="iw-stat-value">{previewData.summary.total}</div>
                <div className="iw-stat-label">Всего строк</div>
              </div>
              <div className="iw-stat-card success">
                <div className="iw-stat-value">{previewData.summary.new}</div>
                <div className="iw-stat-label">Новых кандидатов</div>
              </div>
              <div className="iw-stat-card warning">
                <div className="iw-stat-value">{previewData.summary.duplicates}</div>
                <div className="iw-stat-label">Дублей</div>
              </div>
              <div className="iw-stat-card error">
                <div className="iw-stat-value">{previewData.summary.errors}</div>
                <div className="iw-stat-label">С ошибками</div>
              </div>
            </div>

            {/* Тумблер дублей */}
            <div className="iw-dedup-control">
              <span>Дубли:</span>
              <div className="iw-segment-control">
                <button
                  className={dedupMode === 'skip' ? 'active' : ''}
                  onClick={() => setDedupMode('skip')}
                >
                  Пропустить
                </button>
                <button
                  className={dedupMode === 'update' ? 'active' : ''}
                  onClick={() => setDedupMode('update')}
                >
                  Обновить
                </button>
              </div>
            </div>

            {/* Таблица превью */}
            <div className="iw-preview-table">
              {previewData.rows.map((row) => (
                <div
                  key={row.index}
                  className={`iw-preview-row ${row.status} ${row.status !== 'error' ? 'clickable' : ''}`}
                  onClick={row.status !== 'error' ? () => setDetailCandidate(row) : undefined}
                >
                  <Avatar name={row.name} size="sm" />
                  <div className="iw-row-info">
                    <div className="iw-row-name">{row.name}</div>
                    <div className="iw-row-contacts">
                      {row.phone && <span>{row.phone}</span>}
                      {row.phone && row.email && <span>·</span>}
                      {row.email && <span>{row.email}</span>}
                    </div>
                  </div>
                  <div className="iw-row-details">
                    {row.city && <span>{row.city}</span>}
                    {row.source && (
                      <span
                        className="iw-source-chip"
                        style={{ backgroundColor: SOURCE_CONFIG[row.source]?.color || 'var(--fg-3)' }}
                      >
                        {SOURCE_CONFIG[row.source]?.label || row.source}
                      </span>
                    )}
                  </div>
                  <div className="iw-row-status">
                    {row.status === 'duplicate' && <span className="iw-badge warning">дубль</span>}
                    {row.status === 'error' && <span className="iw-badge error">{row.error}</span>}
                  </div>
                </div>
              ))}
            </div>

            {previewData.remaining > 0 && (
              <div className="iw-remaining">
                и ещё <strong>{previewData.remaining}</strong> строк будут обработаны при импорте
              </div>
            )}

            {actionError && <div className="iw-validation-hint">{actionError}</div>}

            <div className="iw-step-actions">
              <button className="btn btn-secondary" onClick={() => setCurrentStep(2)}>
                ← Назад
              </button>
              <button
                className="btn btn-primary"
                onClick={handleExecute}
                disabled={executeImport.isPending}
              >
                {executeImport.isPending ? 'Запуск…' : `✓ Импортировать ${previewData.summary.new + (dedupMode === 'update' ? previewData.summary.duplicates : 0)} кандидатов`}
              </button>
            </div>
          </div>
        )}

        {/* Шаг 4: Выполнение и результат */}
        {currentStep === 4 && (
          <div className="iw-step-content">
            {jobData?.status === 'running' && (
              <div className="iw-progress-state">
                <div className="iw-brand-char">💃</div>
                <h3>Импорт в процессе</h3>
                <div className="iw-progress-bar">
                  <div
                    className="iw-progress-fill"
                    style={{ width: `${Math.round((jobData.processed / jobData.total) * 100)}%` }}
                  />
                </div>
                <p>
                  Импортировано <strong>{jobData.processed}</strong> из <strong>{jobData.total}</strong>
                  <span className="t-mono"> ({Math.round((jobData.processed / jobData.total) * 100)}%)</span>
                </p>
              </div>
            )}

            {jobData?.status === 'done' && (
              <div className="iw-done-state">
                <div className="iw-success-icon">
                  <Icon name="check-circle" size={48} style={{ color: 'var(--status-success)' }} />
                </div>
                <h3>Импорт завершён</h3>

                <div className="iw-result-stats">
                  <div className="iw-result-card">
                    <div className="iw-result-value">{jobData.created}</div>
                    <div className="iw-result-label">Создано</div>
                  </div>
                  <div className="iw-result-card">
                    <div className="iw-result-value">{dedupMode === 'update' ? jobData.updated : jobData.skipped}</div>
                    <div className="iw-result-label">{dedupMode === 'update' ? 'Обновлено' : 'Пропущено'}</div>
                  </div>
                  <div className="iw-result-card">
                    <div className="iw-result-value">{jobData.errors}</div>
                    <div className="iw-result-label">Ошибок</div>
                  </div>
                </div>

                <div className="iw-done-actions">
                  <button className="btn btn-primary" onClick={onDone}>
                    Смотреть в базе
                  </button>
                  <button className="btn btn-secondary" onClick={reset}>
                    Импортировать ещё
                  </button>
                </div>
              </div>
            )}

            {jobData?.status === 'error' && (
              <div className="iw-error-state">
                <Icon name="alert-triangle" size={36} style={{ color: 'var(--error-fg)' }} />
                <h3>Ошибка импорта</h3>
                <p>{jobData.error || 'Произошла неизвестная ошибка'}</p>
                <button className="btn btn-secondary" onClick={reset}>
                  Попробовать ещё раз
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Попап резюме */}
      {detailCandidate && (
        <ResumeModal
          candidate={detailCandidate}
          onClose={() => setDetailCandidate(null)}
        />
      )}
    </div>
  );
}

// Попап резюме (идиом SSCandidateDetail/iw-modal-*)
function ResumeModal({ candidate, onClose }: { candidate: PreviewRow; onClose: () => void }) {
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  return (
    <div className="iw-modal-backdrop" onClick={handleBackdropClick}>
      <div className="iw-modal-content resume-modal">
        <div className="iw-modal-header">
          <div className="iw-modal-title-group">
            <Avatar name={candidate.name} size="md" />
            <div>
              <h2 className="iw-modal-title">{candidate.name}</h2>
            </div>
          </div>
          <button className="iw-modal-close" onClick={onClose}>
            <Icon name="x" size={20} />
          </button>
        </div>

        <div className="iw-modal-body">
          <div className="resume-chips">
            <span className="resume-chip">Резюме из Потока</span>
            {candidate.source && (
              <span
                className="resume-chip source"
                style={{ backgroundColor: SOURCE_CONFIG[candidate.source]?.color || 'var(--fg-3)' }}
              >
                {SOURCE_CONFIG[candidate.source]?.label || candidate.source}
              </span>
            )}
            {candidate.detail.position && (
              <span className="resume-chip">{candidate.detail.position}</span>
            )}
          </div>

          <div className="resume-card">
            {candidate.detail.position && (
              <div className="resume-section">
                <h4>Желаемая позиция</h4>
                <p>{candidate.detail.position}</p>
              </div>
            )}

            <div className="resume-meta">
              {candidate.detail.experience && <span>{candidate.detail.experience}</span>}
              {candidate.detail.experience && candidate.detail.city && <span>·</span>}
              {candidate.detail.city && <span>{candidate.detail.city}</span>}
              {(candidate.detail.experience || candidate.detail.city) && candidate.detail.company && <span>·</span>}
              {candidate.detail.company && <span>{candidate.detail.company}</span>}
            </div>

            <div className="resume-contacts">
              {candidate.detail.phone && (
                <div className="resume-contact">
                  <Icon name="user" size={14} />
                  <span>{candidate.detail.phone}</span>
                </div>
              )}
              {candidate.detail.email && (
                <div className="resume-contact">
                  <Icon name="mail" size={14} />
                  <span>{candidate.detail.email}</span>
                </div>
              )}
            </div>

            {candidate.detail.comment && (
              <div className="resume-section">
                <h4>О кандидате</h4>
                <p>{candidate.detail.comment}</p>
              </div>
            )}

            {candidate.detail.resume_url && (
              <div className="resume-section">
                <h4>Ссылка на резюме</h4>
                <a href={candidate.detail.resume_url} target="_blank" rel="noopener noreferrer">
                  {candidate.detail.resume_url}
                  <Icon name="external-link" size={14} />
                </a>
              </div>
            )}
          </div>

          <div className="resume-honesty">
            Резюме и биография забраны из исходной системы. Ссылка сохранится в карточке,
            но сам файл резюме недоступен вне неё.
          </div>
        </div>
      </div>
    </div>
  );
}