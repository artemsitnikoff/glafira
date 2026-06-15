import { useState, useRef, useEffect, useMemo, Fragment } from 'react';
import { Icon, type IconName } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import {
  useParseFile,
  usePreviewImport,
  useExecuteImport,
  usePreviewPotokImport,
  useExecutePotokImport,
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
  { id: 'name',       label: 'ФИО',            req: true },
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

// Фазы для развилки источников
type Phase = 'source' | 'upload' | 'columns' | 'token' | 'preview' | 'result';
type Source = 'file' | 'potok' | null;

// Потоки шагов по источнику (для индикатора)
const IMP_FLOWS = {
  file: ['upload', 'columns', 'preview', 'result'] as const,
  potok: ['token', 'preview', 'result'] as const,
};

const IMP_PHASE_LABEL = {
  upload: 'Загрузка',
  columns: 'Колонки',
  token: 'Токен Потока',
  preview: 'Превью',
  result: 'Готово',
};

export function ImportCandidatesWizard({ onClose, onDone }: Props) {
  // Состояние визарда - теперь через фазы и источник
  const [phase, setPhase] = useState<Phase>('source');
  const [source, setSource] = useState<Source>(null);

  // Шаг загрузки файла
  const [file, setFile] = useState<File | null>(null);
  const [parseData, setParseData] = useState<ParseResponse | null>(null);
  const [uploadState, setUploadState] = useState<'idle' | 'parsing' | 'done' | 'error'>('idle');
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Шаг токена Потока
  const [tokenVal, setTokenVal] = useState('');
  const [tokenState, setTokenState] = useState<'idle' | 'connecting'>('idle');

  // Шаг маппинг колонок
  const [mapping, setMapping] = useState<ColumnMapping>({});

  // Шаг превью
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [dedupMode, setDedupMode] = useState<DedupMode>('skip');
  const [detailCandidate, setDetailCandidate] = useState<PreviewRow | null>(null);

  // Вычисляемые значения для UI
  const mappedFields = useMemo(() => new Set(Object.values(mapping)), [mapping]);
  const hasName = mappedFields.has('name');
  const hasContact = mappedFields.has('phone') || mappedFields.has('email');
  const requiredOk = hasName && hasContact;

  // Шаг выполнения
  const [jobId, setJobId] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // API hooks
  const parseFile = useParseFile();
  const previewImport = usePreviewImport();
  const executeImport = useExecuteImport();
  const previewPotokImport = usePreviewPotokImport();
  const executePotokImport = useExecutePotokImport();
  const { data: jobData } = useImportJob(jobId, phase === 'result');

  // Выбор источника
  const pickSource = (s: 'file' | 'potok') => {
    setSource(s);
    setPhase(s === 'file' ? 'upload' : 'token');
  };

  // Подключение к Потоку
  const connectPotok = async () => {
    if (!tokenVal.trim()) return;
    setActionError(null);
    setTokenState('connecting');

    try {
      const result = await previewPotokImport.mutateAsync({
        token: tokenVal,
        dedup_mode: dedupMode,
      });
      setPreviewData(result);
      setTokenState('idle');
      setPhase('preview');
    } catch (error: any) {
      setTokenState('idle');
      // Показываем человекочитаемое сообщение об ошибке
      const errorMsg = error?.response?.data?.error?.message || 'Не удалось подключиться к Потоку';
      setActionError(errorMsg);
    }
  };

  // Обработчики файлов
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
      setPhase('preview');
    } catch {
      setActionError('Не удалось построить превью. Проверьте файл и попробуйте ещё раз.');
    }
  };

  const handleExecute = async () => {
    setActionError(null);

    try {
      const result = source === 'potok'
        ? await executePotokImport.mutateAsync({ token: tokenVal, dedup_mode: dedupMode })
        : await executeImport.mutateAsync({ file: file!, mapping, dedup_mode: dedupMode });

      setJobId(result.job_id);
      setPhase('result');
    } catch {
      setActionError('Не удалось запустить импорт. Попробуйте ещё раз.');
    }
  };

  // Обработка изменения режима дедупликации (для Потока)
  const handleDedupModeChange = async (newMode: DedupMode) => {
    setDedupMode(newMode);

    // Если мы в Потоке и в превью, перезапрашиваем превью с новым режимом
    if (source === 'potok' && phase === 'preview' && tokenVal) {
      try {
        const result = await previewPotokImport.mutateAsync({
          token: tokenVal,
          dedup_mode: newMode,
        });
        setPreviewData(result);
      } catch {
        // При ошибке оставляем как есть
      }
    }
  };

  const reset = () => {
    setPhase('source');
    setSource(null);
    setFile(null);
    setParseData(null);
    setUploadState('idle');
    setDragging(false);
    setTokenVal('');
    setTokenState('idle');
    setMapping({});
    setPreviewData(null);
    setDedupMode('skip');
    setDetailCandidate(null);
    setJobId(null);
    setFileError(null);
    setActionError(null);
  };

  // Форматирование чисел как в эталоне
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

  return (
    <div className="imp-page">
      {/* ===== Верхняя панель + индикатор шагов ===== */}
      <div className="imp-top">
        <div className="imp-top-row">
          <div className="imp-top-title">
            <Icon name="download" size={17}/>
            <span>Импорт кандидатов</span>
          </div>
          <button className="icon-btn" onClick={onClose} title="Закрыть импорт"><Icon name="x" size={18}/></button>
        </div>
        <ImpStepper source={source} phase={phase}/>
      </div>

      {/* ===== Тело ===== */}
      <div className="imp-body">
        <div className="imp-inner">
          {phase === 'source' && (
            <ImpStepSource onPick={pickSource}/>
          )}

          {phase === 'upload' && (
            <ImpStepUpload
              uploadState={uploadState}
              dragging={dragging}
              setDragging={setDragging}
              onDrop={handleDrop}
              fileInputRef={fileInputRef}
              onPick={() => fileInputRef.current?.click()}
              onFileSelect={handleFileSelect}
              onPickError={() => setUploadState('error')}
              onRetry={() => { setUploadState('idle'); setFileError(null); }}
              file={file}
              parseData={parseData}
              onReplaceFile={handleReplaceFile}
              fileError={fileError}
            />
          )}

          {phase === 'token' && (
            <ImpStepToken
              tokenVal={tokenVal}
              setTokenVal={setTokenVal}
              tokenState={tokenState}
              onConnect={connectPotok}
              actionError={actionError}
            />
          )}

          {phase === 'columns' && parseData && (
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
            />
          )}

          {phase === 'preview' && previewData && (
            <ImpStepPreview
              previewData={previewData}
              dedupMode={dedupMode}
              setDedupMode={handleDedupModeChange}
              onRowClick={setDetailCandidate}
              actionError={actionError}
              onExecute={handleExecute}
              executeLoading={executeImport.isPending || executePotokImport.isPending}
              source={source}
            />
          )}

          {phase === 'result' && (
            <ImpStepResult
              jobData={jobData}
              dedupMode={dedupMode}
              onDone={onDone}
              onAgain={reset}
              source={source}
            />
          )}
        </div>
      </div>

      {/* ===== Нижняя панель навигации ===== */}
      {phase === 'upload' && uploadState === 'idle' && (
        <div className="imp-foot">
          <button className="btn btn-secondary btn-sm" onClick={() => { setSource(null); setPhase('source'); }}>
            <Icon name="chevL" size={13}/> Назад
          </button>
        </div>
      )}
      {phase === 'upload' && uploadState === 'done' && (
        <div className="imp-foot">
          <button className="btn btn-secondary btn-sm" onClick={() => { setSource(null); setPhase('source'); setUploadState('idle'); }}>
            <Icon name="chevL" size={13}/> Назад
          </button>
          <div style={{flex:1}}/>
          <button className="btn btn-primary btn-sm" onClick={() => setPhase('columns')}>
            <Icon name="arrowRight" size={14}/> Сопоставить колонки
          </button>
        </div>
      )}
      {phase === 'token' && tokenState === 'idle' && (
        <div className="imp-foot">
          <button className="btn btn-secondary btn-sm" onClick={() => { setSource(null); setPhase('source'); }}>
            <Icon name="chevL" size={13}/> Назад
          </button>
          <div className="imp-foot-hint">
            {actionError
              ? <span className="imp-foot-warn"><Icon name="alert-triangle" size={13}/> {actionError}</span>
              : tokenVal.trim()
              ? <span className="imp-foot-ok"><Icon name="check" size={13}/> Токен введён</span>
              : <span className="imp-foot-warn"><Icon name="alert-triangle" size={13}/> Вставьте API-токен Потока</span>}
          </div>
          <button className="btn btn-primary btn-sm" disabled={!tokenVal.trim() || previewPotokImport.isPending} onClick={() => tokenVal.trim() && connectPotok()}>
            {previewPotokImport.isPending ? 'Подключаемся…' : <><Icon name="arrowRight" size={14}/> Подключиться и загрузить</>}
          </button>
        </div>
      )}
      {phase === 'columns' && (
        <div className="imp-foot">
          <button className="btn btn-secondary btn-sm" onClick={() => setPhase('upload')}>
            <Icon name="chevL" size={13}/> Назад
          </button>
          <div className="imp-foot-hint">
            {actionError
              ? <span className="imp-foot-warn"><Icon name="alert-triangle" size={13}/> {actionError}</span>
              : requiredOk
              ? <span className="imp-foot-ok"><Icon name="check" size={13}/> Обязательные поля сопоставлены</span>
              : <span className="imp-foot-warn"><Icon name="alert-triangle" size={13}/> Сопоставьте ФИО и хотя бы один контакт</span>}
          </div>
          <button className="btn btn-primary btn-sm" disabled={!requiredOk || previewImport.isPending} onClick={handlePreview}>
            {previewImport.isPending ? 'Обработка…' : <><Icon name="arrowRight" size={14}/> Превью</>}
          </button>
        </div>
      )}
      {phase === 'preview' && previewData && (
        <div className="imp-foot">
          <button className="btn btn-secondary btn-sm" onClick={() => setPhase(source === 'potok' ? 'token' : 'columns')}>
            <Icon name="chevL" size={13}/> Назад{source === 'potok' ? '' : ' к колонкам'}
          </button>
          <div style={{flex:1}}/>
          <button className="btn btn-primary btn-sm imp-btn-import" onClick={handleExecute}>
            <Icon name="check" size={15}/> Импортировать {fmtIM(previewData.summary.new + (dedupMode === 'update' ? previewData.summary.duplicates : 0))}&nbsp;кандидатов
          </button>
        </div>
      )}

      {/* Попап резюме */}
      {detailCandidate && (
        <ImpResumeModal
          candidate={detailCandidate}
          source={source}
          onClose={() => setDetailCandidate(null)}
        />
      )}
    </div>
  );
}

// =====================================================================
// Индикатор шагов
// =====================================================================
function ImpStepper({ source, phase }: { source: Source; phase: Phase }) {
  const flow = source ? IMP_FLOWS[source] : IMP_FLOWS.file;
  const phases = ['source', ...flow];
  const labels = ['Источник', ...flow.map(p => IMP_PHASE_LABEL[p])];
  const activeIdx = phases.indexOf(phase);

  return (
    <div className="imp-stepper">
      {labels.map((s, i) => {
        const state = activeIdx > i ? 'done' : activeIdx === i ? 'current' : 'upcoming';
        return (
          <Fragment key={s}>
            <div className={`imp-step ${state}`}>
              <span className="imp-step-dot">{activeIdx > i ? <Icon name="check" size={14}/> : i + 1}</span>
              <span className="imp-step-label">{s}</span>
            </div>
            {i < labels.length - 1 && <span className={`imp-step-line ${activeIdx > i ? 'done' : ''}`}/>}
          </Fragment>
        );
      })}
    </div>
  );
}

// =====================================================================
// ШАГ «Источник» — ХАБ ИСТОЧНИКОВ: импортируйте кандидатов отовсюду
// 4 секции, ~15 источников. Работают: Файл, Поток. Остальные — «Скоро».
// =====================================================================
type SourceItem = {
  key: string;
  icon?: IconName;
  av?: string;
  avBg: string;
  name: string;
  desc: string;
  status: 'live' | 'soon';
  api: 'live' | 'info' | null;
  action?: 'file' | 'potok';
  cap?: string;
};

type SourceSection = {
  id: string;
  label: string;
  sub: string | null;
  items: SourceItem[];
};

const IMP_SOURCES: SourceSection[] = [
  {
    id: 'file',
    label: 'Файл',
    sub: null,
    items: [
      {
        key: 'file',
        icon: 'download',
        avBg: '#1F8A5B',
        name: 'Excel-файл',
        desc: 'Загрузите выгрузку из любой системы',
        status: 'live',
        api: null,
        action: 'file'
      }
    ]
  },
  {
    id: 'ats',
    label: 'Из другой ATS',
    sub: 'Переезжайте — перенесём кандидатов',
    items: [
      {
        key: 'potok',
        av: 'П',
        avBg: '#E8543C',
        name: 'Поток',
        desc: 'Импорт по API-токену',
        status: 'live',
        api: 'live',
        action: 'potok'
      },
      {
        key: 'huntflow',
        av: 'Х',
        avBg: '#1FA07A',
        name: 'Хантфлоу',
        desc: 'Перенос кандидатов и резюме',
        status: 'soon',
        api: null
      },
      {
        key: 'talantix',
        av: 'T',
        avBg: '#2F5FD0',
        name: 'Talantix',
        desc: 'Перенос кандидатов и резюме',
        status: 'soon',
        api: null
      },
      {
        key: 'sber',
        av: 'С',
        avBg: '#21A038',
        name: 'СберПодбор',
        desc: 'Перенос кандидатов и резюме',
        status: 'soon',
        api: null,
        cap: 'есть экспорт CSV'
      }
    ]
  },
  {
    id: 'boards',
    label: 'С джоб-бордов',
    sub: 'Отклики и резюме с площадок',
    items: [
      {
        key: 'superjob',
        av: 'SJ',
        avBg: '#E63329',
        name: 'SuperJob',
        desc: 'Отклики и база резюме',
        status: 'soon',
        api: 'info'
      },
      {
        key: 'avito',
        av: 'А',
        avBg: '#0AA3F5',
        name: 'Авито Работа',
        desc: 'Отклики с площадки',
        status: 'soon',
        api: 'info'
      },
      {
        key: 'rabota',
        av: 'Р',
        avBg: '#E2231A',
        name: 'Работа.ру',
        desc: 'Отклики и резюме',
        status: 'soon',
        api: 'info'
      },
      {
        key: 'zarplata',
        av: 'З',
        avBg: '#F26A21',
        name: 'Зарплата.ру',
        desc: 'Отклики и резюме',
        status: 'soon',
        api: 'info'
      },
      {
        key: 'habr',
        av: 'ХК',
        avBg: '#5F8FA8',
        name: 'Хабр Карьера',
        desc: 'Отклики и резюме',
        status: 'soon',
        api: 'info',
        cap: 'IT-специалисты'
      }
    ]
  },
  {
    id: 'niche',
    label: 'Нишевые источники',
    sub: 'Специалисты по отраслям',
    items: [
      {
        key: 'profi',
        av: 'П',
        avBg: '#E3A008',
        name: 'Профи.ру',
        desc: 'Специалисты услуг',
        status: 'soon',
        api: 'info',
        cap: '3 млн+ специалистов услуг'
      },
      {
        key: 'prodoctorov',
        av: 'ПД',
        avBg: '#2BAE9D',
        name: 'ПроДокторов',
        desc: 'Врачи и медперсонал',
        status: 'soon',
        api: null,
        cap: 'медицина · в проработке'
      },
      {
        key: 'geekjob',
        av: 'G',
        avBg: '#5B6AD0',
        name: 'Geekjob',
        desc: 'IT-специалисты',
        status: 'soon',
        api: null,
        cap: 'IT'
      },
      {
        key: 'getmatch',
        av: 'gm',
        avBg: '#00B894',
        name: 'getmatch',
        desc: 'IT-разработчики',
        status: 'soon',
        api: null,
        cap: 'IT middle+'
      },
      {
        key: 'pomogatel',
        av: 'П',
        avBg: '#F08C2E',
        name: 'Помогатель.ру',
        desc: 'Бытовой персонал',
        status: 'soon',
        api: null,
        cap: 'домашний персонал'
      }
    ]
  }
];

function ImpSourceCard({ item, onPick }: { item: SourceItem; onPick: (source: 'file' | 'potok') => void }) {
  const live = item.status === 'live';
  const handle = live && item.action ? () => onPick(item.action!) : undefined;

  return (
    <div
      className={`src-card ${live ? 'is-live' : 'is-soon'}`}
      onClick={handle}
      role={live ? 'button' : undefined}
      tabIndex={live ? 0 : undefined}
      onKeyDown={live ? (e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handle?.();
        }
      }) : undefined}
      aria-disabled={live ? undefined : 'true'}
    >
      <div className="src-card-top">
        <div className="src-card-av" style={{ background: item.avBg }}>
          {item.icon ? <Icon name={item.icon} size={20} /> : item.av}
        </div>
        <div className="src-card-badges">
          {item.api === 'info' && <span className="src-bdg api">API</span>}
          {item.api === 'live' && <span className="src-bdg live">API</span>}
          {item.status === 'live' && !item.api && (
            <span className="src-bdg live">
              <span className="src-bdg-dot" />
              Доступно
            </span>
          )}
          {item.status === 'soon' && <span className="src-bdg soon">Скоро</span>}
        </div>
      </div>
      <div className="src-card-name">{item.name}</div>
      <div className="src-card-desc">{item.desc}</div>
      {item.cap && <div className="src-card-cap">{item.cap}</div>}
      {live ? (
        <span className="src-card-go">
          {item.action === 'file' ? 'Выбрать файл' : 'Подключить'} <Icon name="chevron-right" size={13} />
        </span>
      ) : (
        <span className="src-tip">
          Интеграция готовится. Хотите раньше — <b>напишите нам</b>
        </span>
      )}
    </div>
  );
}

function ImpStepSource({ onPick }: { onPick: (source: 'file' | 'potok') => void }) {
  return (
    <div className="imp-hub">
      <h2 className="imp-h2">Откуда импортируем?</h2>
      <div className="imp-glafira-note">
        <span className="imp-em">💃</span>
        Глафира умеет забирать кандидатов отовсюду — из файлов, других ATS и с площадок.
      </div>

      {/* легенда бейджей */}
      <div className="src-legend">
        <span className="src-legend-item">
          <span className="src-bdg live">
            <span className="src-bdg-dot" />
            Доступно
          </span>
          работает сейчас
        </span>
        <span className="src-legend-item">
          <span className="src-bdg api">API</span>
          канал данных подтверждён, интеграция готовится
        </span>
        <span className="src-legend-item">
          <span className="src-bdg soon">Скоро</span>
          в плане
        </span>
      </div>

      {IMP_SOURCES.map(sec => (
        <section className="src-sec" key={sec.id}>
          <div className="src-sec-head">
            <span className="src-sec-label">{sec.label}</span>
            {sec.sub && <span className="src-sec-sub">{sec.sub}</span>}
          </div>
          <div className="src-grid">
            {sec.items.map(it => (
              <ImpSourceCard key={it.key} item={it} onPick={onPick} />
            ))}
          </div>
        </section>
      ))}

      {/* CTA — нет своей системы */}
      <div className="src-cta">
        <span className="src-cta-q">Не нашли свою систему?</span>
        <button className="src-cta-link" type="button">
          <Icon name="message-circle" size={14} />
          Напишите нам — добавим источник
        </button>
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ «Токен» — подключение к Потоку по API-токену
// =====================================================================
interface ImpStepTokenProps {
  tokenVal: string;
  setTokenVal: (val: string) => void;
  tokenState: 'idle' | 'connecting';
  onConnect: () => void;
  actionError: string | null;
}

function ImpStepToken({ tokenVal, setTokenVal, tokenState, onConnect, actionError }: ImpStepTokenProps) {
  if (tokenState === 'connecting') {
    return (
      <div className="imp-parse">
        <div className="imp-parse-dancer">💃</div>
        <div className="imp-parse-text">Глафира подключается к Потоку<span className="cd-load-dots"></span></div>
        <div className="imp-parse-sub">Забираем кандидатов и резюме по API</div>
      </div>
    );
  }

  return (
    <div className="imp-token">
      <h2 className="imp-h2">Подключение к Потоку</h2>
      <div className="imp-glafira-note">
        <span className="imp-em">💃</span>
        Вставьте API-токен из Потока — Глафира подключится и сразу покажет превью кандидатов.
      </div>

      <div className="imp-token-card">
        <label className="imp-token-label" htmlFor="imp-token-input">API-токен Потока</label>
        <div className="imp-token-input-row">
          <Icon name="key" size={16}/>
          <input
            id="imp-token-input"
            className="imp-token-input"
            type="text"
            placeholder="32-значный токен, напр. 0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d"
            value={tokenVal}
            onChange={e => setTokenVal(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && tokenVal.trim()) onConnect(); }}
          />
        </div>
        {actionError && (
          <div className="imp-token-error">
            <Icon name="alert-triangle" size={13}/>
            {actionError}
          </div>
        )}
        <div className="imp-token-help">
          <Icon name="info" size={13}/>
          Токен можно создать в Потоке: <b>Настройки → API → Создать токен</b>. Достаточно доступа на чтение кандидатов.
        </div>
      </div>

      <div className="imp-token-steps">
        <div className="imp-token-step"><span className="imp-token-step-n">1</span> Глафира подключится к вашему аккаунту Потока</div>
        <div className="imp-token-step"><span className="imp-token-step-n">2</span> Заберёт кандидатов и их резюме</div>
        <div className="imp-token-step"><span className="imp-token-step-n">3</span> Покажет превью перед заливкой в базу</div>
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ «Загрузка файла» (сохраняем как есть)
// =====================================================================
interface ImpStepUploadProps {
  uploadState: 'idle' | 'parsing' | 'done' | 'error';
  dragging: boolean;
  setDragging: (dragging: boolean) => void;
  onDrop: (e: React.DragEvent) => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  onPick: () => void;
  onFileSelect: (file: File) => void;
  onPickError: () => void;
  onRetry: () => void;
  file: File | null;
  parseData: ParseResponse | null;
  onReplaceFile: () => void;
  fileError: string | null;
}

function ImpStepUpload({
  uploadState,
  dragging,
  setDragging,
  onDrop,
  fileInputRef,
  onPick,
  onFileSelect,
  onRetry,
  file,
  parseData
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
            <button className="btn btn-primary" onClick={onRetry}><Icon name="refresh-cw" size={14}/> Выбрать другой файл</button>
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
            <button className="imp-file-replace" onClick={() => fileInputRef.current?.click()} title="Заменить файл"><Icon name="refresh-cw" size={14}/></button>
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
               onChange={(e) => { const f = e.target.files?.[0]; if (f) onFileSelect(f); e.target.value = ''; }}/>
        <div className="imp-drop-ic"><Icon name="download" size={30}/></div>
        <div className="imp-drop-title">Перетащите Excel-файл с кандидатами<br/>или нажмите для выбора</div>
        <div className="imp-drop-sub">Поддерживаются выгрузки из hh, Потока, Хантфлоу и других систем · форматы <b>.xlsx</b>, <b>.xls</b></div>
        <button className="btn btn-primary imp-drop-btn" onClick={(e) => { e.stopPropagation(); onPick(); }}>
          <Icon name="download" size={14}/> Выбрать файл
        </button>
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ «Сопоставление колонок» (сохраняем как есть, упрощаем интерфейс)
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
          <Icon name={hasName ? 'check' : 'x'} size={12}/> ФИО
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
// ШАГ «Превью импорта» (добавляем поддержку источника)
// =====================================================================
interface ImpStepPreviewProps {
  previewData: PreviewResponse;
  dedupMode: DedupMode;
  setDedupMode: (mode: DedupMode) => void;
  onRowClick: (row: PreviewRow) => void;
  actionError: string | null;
  onExecute: () => void;
  executeLoading: boolean;
  source: Source;
}

function ImpStepPreview({
  previewData,
  dedupMode,
  setDedupMode,
  onRowClick,
  source
}: ImpStepPreviewProps) {
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');

  // Источники кандидатов (упрощённый маппинг)
  const SRC_LABEL: Record<string, string> = {
    hh: 'hh.ru',
    avito: 'Авито',
    telegram: 'Telegram',
    tg: 'Telegram',
    potok: 'Поток'
  };

  const fromPotok = source === 'potok';

  return (
    <div className="imp-preview">
      <h2 className="imp-h2">Превью импорта</h2>
      <div className="imp-preview-from">
        {fromPotok
          ? <><span className="imp-em">💃</span> Глафира забрала кандидатов из <b>Потока</b> по API — проверьте перед заливкой в базу.</>
          : <><Icon name="download" size={14}/> Кандидаты из файла — проверьте перед заливкой в базу.</>}
      </div>

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
            {dedupMode === 'skip' ? 'Совпавшие с базой — не тронем' : 'Совпавшим обновим контакты и поля из источника'}
          </span>
        </div>
        <div className="imp-preview-count">
          Показаны первые <b className="t-mono">{previewData.shown}</b> · и ещё <b className="t-mono">{fmtIM(previewData.remaining)}</b> строк
        </div>
      </div>

      <div className="imp-pv-tip">
        <Icon name="external-link" size={13}/> Нажмите на кандидата, чтобы посмотреть {fromPotok ? 'резюме, забранное из Потока' : 'детали'}
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
                      {(r.detail.resume_url || r.detail.source_url) && r.status !== 'error' && (
                        <span className="imp-badge-resume" title={fromPotok ? "Ссылка на резюме из Потока сохранится в карточке, но сам файл недоступен вне Потока" : "Ссылка на резюме сохранится в карточке"}>
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
            <Icon name="more-horizontal" size={16}/> и ещё <b className="t-mono">{fmtIM(previewData.remaining)}</b> строк будут обработаны при импорте
          </div>
        )}
      </div>
    </div>
  );
}

// =====================================================================
// ШАГ «Импорт и результат» (добавляем поддержку источника)
// =====================================================================
interface ImpStepResultProps {
  jobData: any;
  dedupMode: DedupMode;
  onDone: () => void;
  onAgain: () => void;
  source: Source;
}

function ImpStepResult({ jobData, dedupMode, onDone, onAgain, source }: ImpStepResultProps) {
  const fmtIM = (n: number) => n.toLocaleString('ru-RU').replace(/,/g, ' ');
  const fromPotok = source === 'potok';

  if (!jobData || jobData.status === 'running') {
    const processed = jobData?.processed || 0;
    const total = jobData?.total || 0;
    const created = jobData?.created || 0;
    const updated = jobData?.updated || 0;
    const skipped = jobData?.skipped || 0;
    const errors = jobData?.errors || 0;

    // total === 0 → ещё грузим список из источника (Поток пагинирует API); иначе уже импортируем.
    const loading = total === 0;
    const pct = total > 0 ? Math.round((processed / total) * 100) : 0;  // guard NaN

    return (
      <div className="imp-run">
        <div className="imp-run-dancer">💃</div>
        <div className="imp-run-phase">
          {loading
            ? (fromPotok ? 'Загружаем кандидатов из Потока…' : 'Готовим импорт…')
            : 'Импортируем кандидатов в базу…'}
        </div>
        <div className="imp-run-detail">
          {loading
            ? 'Получаем список, это может занять время…'
            : <>Обработано <b className="t-mono">{fmtIM(processed)}</b> из <b className="t-mono">{fmtIM(total)}</b></>}
        </div>
        <div className={`imp-run-bar ${loading ? 'is-indet' : ''}`}>
          <span style={{ width: loading ? undefined : `${pct}%` }}/>
        </div>
        {!loading && <div className="imp-run-pct t-mono">{pct}%</div>}

        {/* Живой журнал — счётчики обновляются на каждом поллинге */}
        <div className="imp-run-journal">
          <span>Создано: <b>{fmtIM(created)}</b></span>
          <span>{dedupMode === 'update' ? <>Обновлено: <b>{fmtIM(updated)}</b></> : <>Пропущено: <b>{fmtIM(skipped)}</b></>}</span>
          <span>Ошибок: <b>{fmtIM(errors)}</b></span>
        </div>
      </div>
    );
  }

  if (jobData.status === 'error') {
    return (
      <div className="imp-result">
        <div className="imp-result-check" style={{ background: 'var(--ark-red-100)', color: 'var(--ark-red-600)' }}>
          <Icon name="alert-triangle" size={28}/>
        </div>
        <h2 className="imp-result-title">Ошибка импорта</h2>
        <div className="imp-result-sub">{jobData.error || 'Произошла неизвестная ошибка'}</div>

        <div className="imp-result-actions">
          <button className="btn btn-secondary" onClick={onAgain}>
            <Icon name="refresh-cw" size={14}/> Попробовать ещё раз
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
      <div className="imp-result-sub">{fromPotok ? 'Кандидаты из Потока добавлены в общую базу' : 'Кандидаты из файла добавлены в общую базу'}</div>

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
          <Icon name="refresh-cw" size={14}/> Импортировать ещё
        </button>
      </div>

      {errors > 0 && (
        <div className="imp-result-note">
          <Icon name="alert-triangle" size={13}/>
          {fmtIM(errors)} строк пропущено из-за отсутствия имени или контакта — {fromPotok ? 'их можно поправить в Потоке и подключиться повторно.' : 'их можно поправить в файле и загрузить повторно.'}
        </div>
      )}
    </div>
  );
}

// ====== Центральный попап резюме (обновляем для поддержки источника) ======
interface ImpResumeModalProps {
  candidate: PreviewRow;
  source: Source;
  onClose: () => void;
}

function ImpResumeModal({ candidate, source, onClose }: ImpResumeModalProps) {
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
    tg: 'Telegram',
    potok: 'Поток'
  };

  const fromPotok = source === 'potok';

  // detail приходит в двух формах: «Файл» (Excel, плоские поля) и «Поток» (структура из API).
  // Нормализуем, чтобы не показывать пустоту/«[object Object]» (experience у Потока — список).
  const d = candidate.detail;
  const title = fromPotok ? (d.last_position || null) : (d.position || null);
  const expList = Array.isArray(d.experience) ? d.experience : null;
  const expString = typeof d.experience === 'string' ? d.experience : null;
  const lastCompany = fromPotok ? (expList && expList[0]?.company) || null : (d.company || null);
  const about = fromPotok ? (d.resume_summary || null) : (d.comment || null);
  const resumeLink = fromPotok ? (d.source_url || null) : (d.resume_url || null);
  const skills = fromPotok && Array.isArray(d.skills) ? d.skills : null;
  const education = fromPotok && Array.isArray(d.education) ? d.education : null;
  const languages = fromPotok && Array.isArray(d.languages) ? d.languages : null;
  const salaryVal = fromPotok ? d.salary_expectation : d.salary;

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
            <span className="imp-resume-from">
              <span className="imp-resume-from-dot"/>
              {fromPotok ? 'Резюме из Потока' : 'Резюме из файла'}
            </span>
            {candidate.source && (
              <span className={`src-pill src-${candidate.source}`}>{SRC_LABEL[candidate.source] || candidate.source}</span>
            )}
            {title && (
              <span className="imp-modal-role">{title}</span>
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
            {title && (
              <div className="imp-rcard-title">{title}</div>
            )}
            <div className="imp-rcard-meta">
              {expString && <span>Опыт: <b>{expString}</b></span>}
              {expString && candidate.city && <span className="imp-rcard-sep">·</span>}
              {candidate.city && <span>Город: <b>{candidate.city}</b></span>}
              {(expString || candidate.city) && lastCompany && <span className="imp-rcard-sep">·</span>}
              {lastCompany && <span>{fromPotok ? 'Последнее место' : 'Компания'}: <b>{lastCompany}</b></span>}
            </div>

            <div className="imp-resume-contacts">
              {candidate.phone && (
                <div className="imp-rc-row"><Icon name="phone" size={14}/><span className="t-mono">{candidate.phone}</span></div>
              )}
              {candidate.email && (
                <div className="imp-rc-row"><Icon name="mail" size={14}/><span>{candidate.email}</span></div>
              )}
            </div>

            <div className="imp-resume-note">
              <Icon name="alert-triangle" size={13}/>
              {fromPotok
                ? 'Резюме и биография забраны из Потока. Ссылка на исходный файл сохранится в карточке, но сам PDF-файл резюме недоступен вне Потока.'
                : 'Резюме забрано из исходного файла. Ссылка сохранится в карточке, но детальные данные ограничены файлом импорта.'}
            </div>

            {about && (
              <>
                <h3 className="imp-resume-sec">О кандидате</h3>
                <p className="imp-resume-bio">{about}</p>
              </>
            )}

            {expList && expList.length > 0 && (
              <>
                <h3 className="imp-resume-sec">Опыт работы</h3>
                {expList.map((j, k) => (
                  <div key={k} className="imp-job">
                    <div className="imp-job-head">
                      <div>
                        <div className="imp-job-title">{j.position}</div>
                        {j.company && <div className="imp-job-co">{j.company}</div>}
                      </div>
                      {j.period && <div className="imp-job-period">{j.period}</div>}
                    </div>
                    {j.description && <div className="imp-job-desc">{j.description}</div>}
                  </div>
                ))}
              </>
            )}

            {skills && skills.length > 0 && (
              <>
                <h3 className="imp-resume-sec">Навыки</h3>
                <div className="imp-skill-row">
                  {skills.map((s, k) => <span key={k} className="imp-skill-chip">{s.skill}</span>)}
                </div>
              </>
            )}

            {education && education.length > 0 && (
              <>
                <h3 className="imp-resume-sec">Образование</h3>
                {education.map((e, k) => (
                  <div key={k} className="imp-edu-row">
                    <div>
                      <div className="imp-job-title">{e.institution}</div>
                      {e.specialty && <div className="imp-job-co">{e.specialty}</div>}
                    </div>
                    {e.years && <div className="imp-job-period">{e.years}</div>}
                  </div>
                ))}
              </>
            )}

            {resumeLink && (
              <>
                <h3 className="imp-resume-sec">Ссылка на резюме</h3>
                <div className="imp-resume-extra">
                  <div><span className="imp-re-k">Ссылка:</span> <a href={resumeLink} target="_blank" rel="noopener">{resumeLink}</a></div>
                </div>
              </>
            )}

            <h3 className="imp-resume-sec">Дополнительно</h3>
            <div className="imp-resume-extra">
              {candidate.source && (
                <div><span className="imp-re-k">Источник:</span> {SRC_LABEL[candidate.source] || candidate.source}</div>
              )}
              {languages && languages.length > 0 && (
                <div><span className="imp-re-k">Языки:</span> {languages.join(', ')}</div>
              )}
              {!fromPotok && candidate.detail.age && (
                <div><span className="imp-re-k">Возраст:</span> {candidate.detail.age}</div>
              )}
              {salaryVal && (
                <div><span className="imp-re-k">Зарплата:</span> {salaryVal}</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}