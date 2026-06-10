import { useState, useRef, useEffect, useMemo, Fragment } from 'react';
import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
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

// Поля для импорта (как в эталоне)
const IMP_FIELDS = [
  { id: 'name',       label: 'Имя',            req: true },
  { id: 'phone',      label: 'Телефон',        contact: true },
  { id: 'email',      label: 'Email',          contact: true },
  { id: 'city',       label: 'Город' },
  { id: 'age',        label: 'Возраст' },
  { id: 'salary',     label: 'Зарплата' },
  { id: 'source',     label: 'Источник' },
  { id: 'position',   label: 'Должность' },
  { id: 'company',    label: 'Компания' },
  { id: 'experience', label: 'Опыт' },
  { id: 'comment',    label: 'Комментарий' },
  { id: 'resume_url', label: 'Резюме-ссылка' },
];

const FIELD_LABEL: Record<string, string> = IMP_FIELDS.reduce((m, f) => (m[f.id] = f.label, m), { skip: 'Не импортировать' } as Record<string, string>);

type Step = 1 | 2 | 3 | 4;

export function ImportCandidatesWizard({ onClose, onDone }: Props) {
  // Состояние визарда
  const [currentStep, setCurrentStep] = useState<Step>(1);

  // Шаг 1: Загрузка файла
  const [file, setFile] = useState<File | null>(null);
  const [parseData, setParseData] = useState<ParseResponse | null>(null);
  const [uploadState, setUploadState] = useState<'idle' | 'parsing' | 'done' | 'error'>('idle');
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Шаг 2: Маппинг колонок
  const [mapping, setMapping] = useState<ColumnMapping>({});

  // Шаг 3: Превью
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [dedupMode, setDedupMode] = useState<DedupMode>('skip');
  const [detailCandidate, setDetailCandidate] = useState<PreviewRow | null>(null);

  // Вычисляемые значения для UI
  const mappedFields = useMemo(() => new Set(Object.values(mapping)), [mapping]);
  const hasName = mappedFields.has('name');
  const hasContact = mappedFields.has('phone') || mappedFields.has('email');
  const requiredOk = hasName && hasContact;

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
      setUploadState('error');
      setFileError('Поддерживаются только файлы .xlsx и .xls');
      return;
    }

    setFile(selectedFile);
    setUploadState('parsing');

    try {
      const result = await parseFile.mutateAsync(selectedFile);
      setParseData(result);
      setUploadState('done');

      // Инициализируем маппинг из auto_mapping
      setMapping(result.auto_mapping as ColumnMapping);
    } catch (error) {
      setFile(null);
      setParseData(null);
      setUploadState('error');
      setFileError('Не удалось прочитать файл');
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      handleFileSelect(droppedFile);
    }
  };

  const handleReplaceFile = () => {
    setFile(null);
    setParseData(null);
    setUploadState('idle');
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

  // Удаляем дублированную функцию, используем вычисляемые значения

  const handlePreview = async () => {
    if (!file || !requiredOk) return;
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
    setUploadState('idle');
    setDragging(false);
    setMapping({});
    setPreviewData(null);
    setDedupMode('skip');
    setDetailCandidate(null);
    setJobId(null);
    setFileError(null);
    setActionError(null);
  };

  // Форматирование чисел как в эталоне
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

  return (
    <div className="imp-page">
      {/* ===== Верхняя панель + индикатор шагов ===== */}
      <div className="imp-top">
        <div className="imp-top-row">
          <div className="imp-top-title">
            <Icon name="download" size={17}/>
            <span>Импорт кандидатов из файла</span>
          </div>
          <button className="icon-btn" onClick={onClose} title="Закрыть импорт"><Icon name="x" size={18}/></button>
        </div>
        <ImpStepper step={currentStep}/>
      </div>

      {/* ===== Тело ===== */}
      <div className="imp-body">
        <div className="imp-inner">
          {currentStep === 1 && (
            <ImpStepUpload
              uploadState={uploadState}
              dragging={dragging}
              setDragging={setDragging}
              onDrop={handleDrop}
              fileInputRef={fileInputRef}
              onPick={() => fileInputRef.current?.click()}
              onPickError={() => setUploadState('error')}
              onRetry={() => { setUploadState('idle'); setFileError(null); }}
              file={file}
              parseData={parseData}
              onReplaceFile={handleReplaceFile}
              fileError={fileError}
              onNext={() => setCurrentStep(2)}
            />
          )}

          {currentStep === 2 && parseData && (
            <ImpStepColumns
              parseData={parseData}
              mapping={mapping}
              setMapping={setMapping}
              hasName={hasName}
              hasContact={hasContact}
              onMappingChange={handleMappingChange}
              requiredOk={requiredOk}
              actionError={actionError}
              onPreview={handlePreview}
              previewLoading={previewImport.isPending}
              onBack={() => setCurrentStep(1)}
            />
          )}

          {currentStep === 3 && previewData && (
            <ImpStepPreview
              previewData={previewData}
              dedupMode={dedupMode}
              setDedupMode={setDedupMode}
              onRowClick={setDetailCandidate}
              actionError={actionError}
              onExecute={handleExecute}
              executeLoading={executeImport.isPending}
              onBack={() => setCurrentStep(2)}
            />
          )}

          {currentStep === 4 && (
            <ImpStepResult
              jobData={jobData}
              dedupMode={dedupMode}
              onDone={onDone}
              onAgain={reset}
            />
          )}
        </div>
      </div>

      {/* ===== Нижняя панель навигации ===== */}
      {currentStep === 1 && uploadState === 'done' && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={onClose}>Отмена</button>
          <div style={{flex:1}}/>
          <button className="btn btn-primary" onClick={() => setCurrentStep(2)}>
            Далее → Сопоставить колонки
          </button>
        </div>
      )}
      {currentStep === 2 && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={() => setCurrentStep(1)}>
            <Icon name="chevron-left" size={14}/> Назад
          </button>
          <div className="imp-foot-hint">
            {requiredOk
              ? <span className="imp-foot-ok"><Icon name="check" size={13}/> Обязательные поля сопоставлены</span>
              : <span className="imp-foot-warn"><Icon name="alert-triangle" size={13}/> Сопоставьте Имя и хотя бы один контакт</span>}
          </div>
          <button className="btn btn-primary" disabled={!requiredOk} onClick={() => requiredOk && setCurrentStep(3)}>
            Далее → Превью
          </button>
        </div>
      )}
      {currentStep === 3 && previewData && (
        <div className="imp-foot">
          <button className="btn btn-secondary" onClick={() => setCurrentStep(2)}>
            <Icon name="chevron-left" size={14}/> Назад к колонкам
          </button>
          <div style={{flex:1}}/>
          <button className="btn btn-primary imp-btn-import" onClick={handleExecute}>
            <Icon name="check" size={15}/> Импортировать {fmtIM(previewData.summary.new + (dedupMode === 'update' ? previewData.summary.duplicates : 0))}&nbsp;кандидатов
          </button>
        </div>
      )}

      {/* Попап резюме */}
      {detailCandidate && (
        <ImpResumeModal
          candidate={detailCandidate}
          onClose={() => setDetailCandidate(null)}
        />
      )}
    </div>
  );
}

// =====================================================================
// Индикатор шагов
// =====================================================================
function ImpStepper({ step }: { step: Step }) {
  const steps = ['Загрузка', 'Колонки', 'Превью', 'Готово'];
  return (
    <div className="imp-stepper">
      {steps.map((s, i) => {
        const n = i + 1;
        const state = step > n ? 'done' : step === n ? 'current' : 'upcoming';
        return (
          <Fragment key={s}>
            <div className={`imp-step ${state}`}>
              <span className="imp-step-dot">{step > n ? <Icon name="check" size={14}/> : n}</span>
              <span className="imp-step-label">{s}</span>
            </div>
            {i < steps.length - 1 && <span className={`imp-step-line ${step > n ? 'done' : ''}`}/>}
          </Fragment>
        );
      })}
    </div>
  );
}

// =====================================================================
// ШАГ 1 — Загрузка файла
// =====================================================================
interface ImpStepUploadProps {
  uploadState: 'idle' | 'parsing' | 'done' | 'error';
  dragging: boolean;
  setDragging: (dragging: boolean) => void;
  onDrop: (e: React.DragEvent) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onPick: () => void;
  onPickError: () => void;
  onRetry: () => void;
  file: File | null;
  parseData: ParseResponse | null;
  onReplaceFile: () => void;
  fileError: string | null;
  onNext: () => void;
}

function ImpStepUpload({
  uploadState,
  dragging,
  setDragging,
  onDrop,
  fileInputRef,
  onPick,
  onPickError,
  onRetry,
  file,
  parseData,
  onReplaceFile
}: ImpStepUploadProps) {
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

  if (uploadState === 'parsing') {
    return (
      <div className="imp-parse">
        <div className="imp-parse-dancer">💃</div>
        <div className="imp-parse-text">Глафира читает файл<span className="cd-load-dots"></span></div>
        <div className="imp-parse-sub">Распознаём строки и колонки</div>
      </div>
    );
  }

  if (uploadState === 'error') {
    return (
      <div className="imp-stage-wrap">
        <div className="imp-drop imp-drop-error">
          <div className="imp-drop-ic imp-drop-ic-error"><Icon name="alert-triangle" size={30}/></div>
          <div className="imp-drop-title">Не удалось прочитать файл</div>
          <div className="imp-drop-sub">Поддерживаются только таблицы Excel — <b>.xlsx</b> и <b>.xls</b>. Проверьте формат и попробуйте ещё раз.</div>
          <div className="imp-drop-actions">
            <button className="btn btn-primary" onClick={onRetry}><Icon name="refresh" size={14}/> Выбрать другой файл</button>
          </div>
        </div>
      </div>
    );
  }

  if (uploadState === 'done' && file && parseData) {
    return (
      <div className="imp-stage-wrap">
        {/* Карточка-итог файла */}
        <div className="imp-file-card">
          <div className="imp-file-head">
            <div className="imp-file-ic"><Icon name="download" size={20}/></div>
            <div className="imp-file-main">
              <div className="imp-file-name">{file.name}</div>
              <div className="imp-file-meta">
                Найдено <b className="t-mono">{fmtIM(parseData.row_count)}</b> строк ·
                <b className="t-mono"> {parseData.columns.length}</b> колонок
              </div>
            </div>
            <span className="imp-file-ok"><Icon name="check" size={13}/> Файл прочитан</span>
            <button className="imp-file-replace" onClick={onReplaceFile} title="Заменить файл"><Icon name="refresh" size={14}/></button>
          </div>
          <div className="imp-file-cols">
            <div className="imp-file-cols-label">Распознанные колонки</div>
            <div className="imp-chip-row">
              {parseData.columns.map(c => (
                <span key={c} className="imp-col-chip">{c}</span>
              ))}
            </div>
          </div>
        </div>
        <div className="imp-next-hint">
          Глафира уже сопоставила колонки автоматически — на следующем шаге проверьте и поправьте маппинг.
        </div>
      </div>
    );
  }

  // idle
  return (
    <div className="imp-stage-wrap">
      <div
        className={`imp-drop ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => onPick()}
      >
        <input ref={fileInputRef} type="file" accept=".xlsx,.xls" style={{display:'none'}}
               onChange={() => onPick()}/>
        <div className="imp-drop-ic"><Icon name="download" size={30}/></div>
        <div className="imp-drop-title">Перетащите Excel-файл с кандидатами<br/>или нажмите для выбора</div>
        <div className="imp-drop-sub">Поддерживаются выгрузки из hh, Потока, Хантфлоу и других систем · форматы <b>.xlsx</b>, <b>.xls</b></div>
        <button className="btn btn-primary imp-drop-btn" onClick={(e) => { e.stopPropagation(); onPick(); }}>
          <Icon name="download" size={14}/> Выбрать файл
        </button>
      </div>
      <button className="imp-demo-link" onClick={onPickError}>
        Что будет, если файл не Excel? →
      </button>
    </div>
  );
}

// =====================================================================
// ШАГ 2 — Сопоставление колонок
// =====================================================================
interface ImpStepColumnsProps {
  parseData: ParseResponse;
  mapping: ColumnMapping;
  setMapping: (mapping: ColumnMapping) => void;
  hasName: boolean;
  hasContact: boolean;
  onMappingChange: (column: string, fieldKey: FieldKey) => void;
  requiredOk: boolean;
  actionError: string | null;
  onPreview: () => void;
  previewLoading: boolean;
  onBack: () => void;
}

function ImpStepColumns({
  parseData,
  mapping,
  hasName,
  hasContact,
  onMappingChange
}: ImpStepColumnsProps) {
  const [openDrop, setOpenDrop] = useState<string | null>(null);

  return (
    <div className="imp-cols">
      <h2 className="imp-h2">Сопоставьте колонки</h2>
      <div className="imp-glafira-note">
        <span className="imp-em">💃</span>
        Глафира распознала колонки автоматически — проверьте и поправьте, если нужно.
      </div>

      {/* индикатор обязательных полей */}
      <div className="imp-req-row">
        <span className="imp-req-label">Обязательные поля:</span>
        <span className={`imp-req-chip ${hasName ? 'ok' : 'bad'}`}>
          <Icon name={hasName ? 'check' : 'x'} size={12}/> Имя
        </span>
        <span className={`imp-req-chip ${hasContact ? 'ok' : 'bad'}`}>
          <Icon name={hasContact ? 'check' : 'x'} size={12}/> Контакт (телефон / email)
        </span>
      </div>

      {/* таблица сопоставления */}
      <div className="imp-map-table">
        <div className="imp-map-thead">
          <div className="imp-mt-col">Колонка из файла</div>
          <div className="imp-mt-arrow"/>
          <div className="imp-mt-field">Поле кандидата</div>
        </div>
        {parseData.columns.map(c => {
          const val = mapping[c] || 'skip';
          const auto = parseData.auto_mapping[c] && val === parseData.auto_mapping[c];
          const unmapped = val === 'skip';
          const needsManual = !parseData.auto_mapping[c] && unmapped;
          const samples = parseData.samples[c] || [];

          return (
            <div key={c} className={`imp-map-row ${needsManual ? 'needs' : ''}`}>
              <div className="imp-mt-col">
                <div className="imp-col-name">
                  {c}
                  {auto && <span className="imp-auto-tag"><Icon name="check" size={11}/> распознано</span>}
                  {needsManual && <span className="imp-manual-tag">выберите вручную</span>}
                </div>
                <div className="imp-col-samples">
                  {samples.slice(0, 3).map((s, i) => <span key={i} className="imp-sample">{s}</span>)}
                </div>
              </div>
              <div className="imp-mt-arrow"><Icon name="arrow-right" size={16}/></div>
              <div className="imp-mt-field">
                <ImpFieldSelect
                  colId={c}
                  value={val}
                  open={openDrop === c}
                  onToggle={() => setOpenDrop(openDrop === c ? null : c)}
                  onPick={(fid) => { onMappingChange(c, fid); setOpenDrop(null); }}
                  usedFields={Object.entries(mapping).filter(([k]) => k !== c).map(([, v]) => v)}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// дропдаун выбора поля
interface ImpFieldSelectProps {
  colId: string;
  value: FieldKey;
  open: boolean;
  onToggle: () => void;
  onPick: (fieldId: FieldKey) => void;
  usedFields: FieldKey[];
}

function ImpFieldSelect({ value, open, onToggle, onPick, usedFields }: ImpFieldSelectProps) {
  const isSkip = value === 'skip';
  return (
    <div className={`imp-sel-wrap ${open ? 'open' : ''}`}>
      <button className={`imp-sel ${isSkip ? 'skip' : ''}`} onClick={onToggle}>
        <span className="imp-sel-val">{FIELD_LABEL[value]}</span>
        <Icon name="chevron-down" size={14} className="imp-sel-chev"/>
      </button>
      {open && (
        <>
          <div className="imp-sel-backdrop" onClick={onToggle}/>
          <div className="imp-sel-menu">
            {IMP_FIELDS.map(f => {
              const used = usedFields.includes(f.id as FieldKey) && f.id !== value;
              return (
                <button key={f.id}
                        className={`imp-sel-opt ${value === f.id ? 'sel' : ''} ${used ? 'used' : ''}`}
                        onClick={() => onPick(f.id as FieldKey)}>
                  <span className="imp-sel-opt-label">
                    {f.label}
                    {f.req && <span className="imp-sel-opt-req">обяз.</span>}
                  </span>
                  {used && <span className="imp-sel-opt-used">занято</span>}
                  {value === f.id && <Icon name="check" size={14}/>}
                </button>
              );
            })}
            <div className="imp-sel-sep"/>
            <button className={`imp-sel-opt imp-sel-skip ${value === 'skip' ? 'sel' : ''}`}
                    onClick={() => onPick('skip')}>
              <span className="imp-sel-opt-label">Не импортировать</span>
              {value === 'skip' && <Icon name="check" size={14}/>}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// =====================================================================
// ШАГ 3 — Превью импорта
// =====================================================================
interface ImpStepPreviewProps {
  previewData: PreviewResponse;
  dedupMode: DedupMode;
  setDedupMode: (mode: DedupMode) => void;
  onRowClick: (row: PreviewRow) => void;
  actionError: string | null;
  onExecute: () => void;
  executeLoading: boolean;
  onBack: () => void;
}

function ImpStepPreview({
  previewData,
  dedupMode,
  setDedupMode,
  onRowClick
}: ImpStepPreviewProps) {
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

  // Источники кандидатов (упрощённый маппинг)
  const SRC_LABEL: Record<string, string> = {
    hh: 'hh.ru',
    avito: 'Авито',
    telegram: 'Telegram',
    tg: 'Telegram'
  };

  return (
    <div className="imp-preview">
      <h2 className="imp-h2">Превью импорта</h2>

      {/* сводка-полоса */}
      <div className="imp-stat-row">
        <div className="imp-stat">
          <div className="imp-stat-num t-mono">{fmtIM(previewData.summary.total)}</div>
          <div className="imp-stat-lbl">Всего строк</div>
        </div>
        <div className="imp-stat is-new">
          <div className="imp-stat-num t-mono">{fmtIM(previewData.summary.new)}</div>
          <div className="imp-stat-lbl">Новых кандидатов</div>
        </div>
        <div className="imp-stat is-dup">
          <div className="imp-stat-num t-mono">{fmtIM(previewData.summary.duplicates)}</div>
          <div className="imp-stat-lbl">Дублей <span className="imp-stat-cap">уже в базе</span></div>
        </div>
        <div className="imp-stat is-err">
          <div className="imp-stat-num t-mono">{fmtIM(previewData.summary.errors)}</div>
          <div className="imp-stat-lbl">С ошибками <span className="imp-stat-cap">пропустятся</span></div>
        </div>
      </div>

      {/* тумблер дублей */}
      <div className="imp-preview-controls">
        <div className="imp-dup-ctrl">
          <span className="imp-dup-label">Дубли:</span>
          <div className="imp-seg">
            <button className={`imp-seg-btn ${dedupMode === 'skip' ? 'active' : ''}`} onClick={() => setDedupMode('skip')}>Пропустить</button>
            <button className={`imp-seg-btn ${dedupMode === 'update' ? 'active' : ''}`} onClick={() => setDedupMode('update')}>Обновить</button>
          </div>
          <span className="imp-dup-hint">
            {dedupMode === 'skip' ? 'Совпавшие с базой — не тронем' : 'Совпавшим обновим контакты и поля из файла'}
          </span>
        </div>
        <div className="imp-preview-count">
          Показаны первые <b className="t-mono">{previewData.shown}</b> · и ещё <b className="t-mono">{fmtIM(previewData.remaining)}</b> строк
        </div>
      </div>

      <div className="imp-pv-tip">
        <Icon name="external-link" size={13}/> Нажмите на кандидата, чтобы посмотреть детали
      </div>

      {/* таблица превью */}
      <div className="imp-pv-table">
        <div className="imp-pv-head">
          <div className="imp-pv-c-name">Кандидат</div>
          <div className="imp-pv-c-phone">Телефон</div>
          <div className="imp-pv-c-email">Email</div>
          <div className="imp-pv-c-city">Город</div>
          <div className="imp-pv-c-src">Источник</div>
        </div>
        <div className="imp-pv-body">
          {previewData.rows.map((r) => {
            const skip = r.status === 'error' || (r.status === 'duplicate' && dedupMode === 'skip');
            const clickable = r.status !== 'error';
            return (
              <div key={r.index}
                   className={`imp-pv-row ${r.status === 'error' ? 'err' : ''} ${r.status === 'duplicate' ? 'dup' : ''} ${skip ? 'skip' : ''} ${clickable ? 'clickable' : ''}`}
                   onClick={() => clickable && onRowClick(r)}>
                <div className="imp-pv-c-name">
                  {r.status === 'error' && !r.name
                    ? <span className="imp-pv-avatar-x"><Icon name="x" size={13}/></span>
                    : <Avatar name={r.name || '?'} size="sm"/>}
                  <div className="imp-pv-name-wrap">
                    <span className={`imp-pv-name ${!r.name ? 'empty' : ''}`}>{r.name || 'нет имени'}</span>
                    <div className="imp-pv-badges">
                      {r.status === 'duplicate' && <span className="imp-badge-dup">дубль</span>}
                      {r.status === 'error' && <span className="imp-badge-err"><Icon name="alert-triangle" size={10}/> {r.error}</span>}
                      {r.detail.resume_url && r.status !== 'error' && (
                        <span className="imp-badge-resume" title="Ссылка на резюме сохранится в карточке">
                          <Icon name="external-link" size={10}/> резюме-ссылка
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="imp-pv-c-phone t-mono">{r.phone || '—'}</div>
                <div className="imp-pv-c-email">{r.email || '—'}</div>
                <div className="imp-pv-c-city">{r.city || '—'}</div>
                <div className="imp-pv-c-src">
                  {r.source ? (
                    <span className={`src-pill src-${r.source}`}>{SRC_LABEL[r.source] || r.source}</span>
                  ) : '—'}
                </div>
                {clickable && <Icon name="chevron-right" size={15} className="imp-pv-open"/>}
              </div>
            );
          })}
        </div>
        {previewData.remaining > 0 && (
          <div className="imp-pv-more">
            <Icon name="more" size={16}/> и ещё <b className="t-mono">{fmtIM(previewData.remaining)}</b> строк будут обработаны при импорте
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ 4 — Импорт и результат
// =====================================================================
interface ImpStepResultProps {
  jobData: any;
  dedupMode: DedupMode;
  onDone: () => void;
  onAgain: () => void;
}

function ImpStepResult({ jobData, dedupMode, onDone, onAgain }: ImpStepResultProps) {
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

  if (!jobData || jobData.status === 'running') {
    const pct = jobData ? Math.round((jobData.processed / jobData.total) * 100) : 0;
    const imported = jobData?.processed || 0;
    const total = jobData?.total || 0;

    return (
      <div className="imp-run">
        <div className="imp-run-dancer">💃</div>
        <div className="imp-run-phase">Импортируем кандидатов в базу…</div>
        <div className="imp-run-detail">
          Импортировано <b className="t-mono">{fmtIM(imported)}</b> из <b className="t-mono">{fmtIM(total)}</b>
        </div>
        <div className="imp-run-bar"><span style={{width: `${pct}%`}}/></div>
        <div className="imp-run-pct t-mono">{pct}%</div>
      </div>
    );
  }

  if (jobData.status === 'error') {
    return (
      <div className="imp-result">
        <div className="imp-result-check" style={{ background: 'var(--error-bg)', color: 'var(--error-fg)' }}>
          <Icon name="alert-triangle" size={28}/>
        </div>
        <h2 className="imp-result-title">Ошибка импорта</h2>
        <div className="imp-result-sub">{jobData.error || 'Произошла неизвестная ошибка'}</div>

        <div className="imp-result-actions">
          <button className="btn btn-secondary" onClick={onAgain}>
            <Icon name="refresh" size={14}/> Попробовать ещё раз
          </button>
        </div>
      </div>
    );
  }

  // result (done)
  const created = jobData.created || 0;
  const updated = jobData.updated || 0;
  const skipped = jobData.skipped || 0;
  const errors = jobData.errors || 0;

  return (
    <div className="imp-result">
      <div className="imp-result-check"><Icon name="check" size={28}/></div>
      <h2 className="imp-result-title">Импорт завершён</h2>
      <div className="imp-result-sub">Кандидаты из файла добавлены в общую базу</div>

      <div className="imp-result-stats">
        <div className="imp-rstat is-new">
          <div className="num t-mono">{fmtIM(created)}</div>
          <div className="lbl">Создано кандидатов</div>
        </div>
        <div className="imp-rstat is-dup">
          <div className="num t-mono">{fmtIM(dedupMode === 'update' ? updated : skipped)}</div>
          <div className="lbl">{dedupMode === 'update' ? 'Дублей обновлено' : 'Пропущено дублей'}</div>
        </div>
        <div className="imp-rstat is-err">
          <div className="num t-mono">{fmtIM(errors)}</div>
          <div className="lbl">Ошибок (пропущены)</div>
        </div>
      </div>

      <div className="imp-result-actions">
        <button className="btn btn-primary" onClick={onDone}>
          <Icon name="users" size={15}/> Смотреть в базе
        </button>
        <button className="btn btn-secondary" onClick={onAgain}>
          <Icon name="refresh" size={14}/> Импортировать ещё
        </button>
      </div>

      {errors > 0 && (
        <div className="imp-result-note">
          <Icon name="alert-triangle" size={13}/>
          {fmtIM(errors)} строк пропущено из-за отсутствия имени или контакта — их можно поправить в файле и загрузить повторно.
        </div>
      )}
    </div>
  );
}

// ====== Центральный попап резюме ======
interface ImpResumeModalProps {
  candidate: PreviewRow;
  onClose: () => void;
}

function ImpResumeModal({ candidate, onClose }: ImpResumeModalProps) {
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  const SRC_LABEL: Record<string, string> = {
    hh: 'hh.ru',
    avito: 'Авито',
    telegram: 'Telegram',
    tg: 'Telegram'
  };

  return (
    <div className="imp-modal-overlay" onClick={onClose}>
      <div className="imp-modal" role="dialog" aria-label="Резюме кандидата" onClick={e => e.stopPropagation()}>
        <button className="icon-btn imp-modal-close" onClick={onClose} title="Закрыть"><Icon name="x" size={18}/></button>

        <div className="imp-modal-head">
          <div className="imp-modal-id">
            <Avatar name={candidate.name} size="md"/>
            <h2 className="imp-modal-name">{candidate.name}</h2>
          </div>
          <div className="imp-modal-chips">
            <span className="imp-resume-from"><span className="imp-resume-from-dot"/> Резюме из файла</span>
            {candidate.source && (
              <span className={`src-pill src-${candidate.source}`}>{SRC_LABEL[candidate.source] || candidate.source}</span>
            )}
            {candidate.detail.position && (
              <span className="imp-modal-role">{candidate.detail.position}</span>
            )}
          </div>
        </div>

        <div className="imp-modal-body">
          <div className="imp-modal-seclabel">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>
            </svg>
            Резюме
          </div>

          <div className="imp-resume-card">
            {candidate.detail.position && (
              <div className="imp-rcard-title">{candidate.detail.position}</div>
            )}
            <div className="imp-rcard-meta">
              {candidate.detail.experience && <span>Опыт: <b>{candidate.detail.experience}</b></span>}
              {candidate.detail.experience && candidate.city && <span className="imp-rcard-sep">·</span>}
              {candidate.city && <span>Город: <b>{candidate.city}</b></span>}
              {(candidate.detail.experience || candidate.city) && candidate.detail.company && <span className="imp-rcard-sep">·</span>}
              {candidate.detail.company && <span>Компания: <b>{candidate.detail.company}</b></span>}
            </div>

            <div className="imp-resume-contacts">
              {candidate.phone && (
                <div className="imp-rc-row"><Icon name="user" size={14}/><span className="t-mono">{candidate.phone}</span></div>
              )}
              {candidate.email && (
                <div className="imp-rc-row"><Icon name="mail" size={14}/><span>{candidate.email}</span></div>
              )}
            </div>

            <div className="imp-resume-note">
              <Icon name="alert-triangle" size={13}/>
              Резюме забрано из исходного файла. Ссылка сохранится в карточке, но детальные данные ограничены файлом импорта.
            </div>

            {candidate.detail.comment && (
              <>
                <h3 className="imp-resume-sec">О кандидате</h3>
                <p className="imp-resume-bio">{candidate.detail.comment}</p>
              </>
            )}

            {candidate.detail.resume_url && (
              <>
                <h3 className="imp-resume-sec">Ссылка на резюме</h3>
                <div className="imp-resume-extra">
                  <div><span className="imp-re-k">Ссылка:</span> <a href={candidate.detail.resume_url} target="_blank" rel="noopener">{candidate.detail.resume_url}</a></div>
                </div>
              </>
            )}

            <h3 className="imp-resume-sec">Дополнительно</h3>
            <div className="imp-resume-extra">
              {candidate.source && (
                <div><span className="imp-re-k">Источник:</span> {SRC_LABEL[candidate.source] || candidate.source}</div>
              )}
              {candidate.detail.age && (
                <div><span className="imp-re-k">Возраст:</span> {candidate.detail.age}</div>
              )}
              {candidate.detail.salary && (
                <div><span className="imp-re-k">Зарплата:</span> {candidate.detail.salary}</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}