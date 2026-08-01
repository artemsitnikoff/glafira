import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useParams } from 'react-router-dom';
import { publicClient } from '@/api/publicClient';
import { MatrixCell } from './MatrixCell';
import type { CellParams } from './MatrixCell';
import './TestPage.css';

// ---------------------------------------------------------------------------
// Типы публичного экзамен-API (openapi.json протух — локальные типы + as-cast,
// сверено с backend/app/schemas/public_test.py). Правильного ответа тут НЕТ нигде.
// ---------------------------------------------------------------------------
type TestStatus = 'sent' | 'started' | 'completed' | 'expired';

interface TestBlockInfo {
  index: number;
  key: string;
  title: string;
  item_count: number;
  duration_min: number;
}

interface TestInfo {
  status: TestStatus;
  company_name: string;
  test_name: string;
  kind: 'single' | 'blocked';
  instruction: string;
  item_count: number;
  duration_min?: number | null;
  blocks: TestBlockInfo[];
}

interface PubOption {
  id: string;
  params?: CellParams | null; // matrix
  text?: string | null; // text
}

interface PubItem {
  id: string;
  kind: 'matrix' | 'text';
  body: Record<string, unknown>;
  options: PubOption[];
}

interface PubCurrentBlock {
  index: number;
  total: number;
  key: string;
  title: string;
  time_left_sec: number;
}

interface CurrentResp {
  status: 'in_progress' | 'awaiting_next_block' | 'completed' | 'not_started';
  index: number;
  total: number;
  time_left_sec?: number | null; // single
  block?: PubCurrentBlock | null;
  item?: PubItem | null;
  next_block_title?: string | null;
}

interface AnswerResp {
  ok: boolean;
  status: 'in_progress' | 'awaiting_next_block' | 'completed';
}

interface BlockNextResp {
  status: 'in_progress' | 'completed';
  block?: PubCurrentBlock | null;
}

// ---------------------------------------------------------------------------
// Ошибки axios
// ---------------------------------------------------------------------------
function errStatus(e: unknown): number | undefined {
  return (e as { response?: { status?: number } })?.response?.status;
}
function errCode(e: unknown): string | undefined {
  return (e as { response?: { data?: { error?: { code?: string } } } })?.response?.data?.error?.code;
}
function hasResponse(e: unknown): boolean {
  return !!(e as { response?: unknown })?.response;
}

// ---------------------------------------------------------------------------
// Хелперы
// ---------------------------------------------------------------------------
function fmtTime(sec: number): string {
  const s = Math.max(0, sec);
  const m = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${m}:${ss}`;
}

const LETTERS = ['а', 'б', 'в', 'г', 'д', 'е', 'ж', 'з'];

// Статичные ОБУЧАЮЩИЕ примеры заставки блока — иллюстрации, НЕ из банка (не утечка).
const BLOCK_EXAMPLES: Record<string, { q: ReactNode; a: ReactNode }> = {
  exclusion: {
    q: 'стол · стул · шкаф · дождь · диван',
    a: (
      <>
        Лишнее — <b>дождь</b>: остальные слова обозначают мебель.
      </>
    ),
  },
  analogy: {
    q: 'птица : гнездо = пчела : ?',
    a: (
      <>
        Верный ответ — <b>улей</b>. Связь «обитатель → жилище», а не «насекомое → мёд».
      </>
    ),
  },
  series: {
    q: '2, 4, 8, 16, …',
    a: (
      <>
        Дальше <b>32</b>: каждое следующее число вдвое больше предыдущего.
      </>
    ),
  },
  generalization: {
    q: 'яблоко · груша',
    a: (
      <>
        Общее понятие — <b>фрукты</b>.
      </>
    ),
  },
};

// ---------------------------------------------------------------------------
// Компонент
// ---------------------------------------------------------------------------
type Phase =
  | 'loading'
  | 'start'
  | 'question'
  | 'blockIntro'
  | 'timeUp'
  | 'finished'
  | 'expired'
  | 'notfound'
  | 'done' // уже пройден
  | 'loadError';

export default function TestPage() {
  const { token } = useParams<{ token: string }>();

  const [phase, setPhase] = useState<Phase>('loading');
  const [info, setInfo] = useState<TestInfo | null>(null);
  const [current, setCurrent] = useState<CurrentResp | null>(null);

  const [agreed, setAgreed] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [timeLeft, setTimeLeft] = useState<number | null>(null);

  // Ветка «blocked»: обзор ранее пройденных заданий (allow_back).
  const [frontierIndex, setFrontierIndex] = useState(0);
  const [viewIndex, setViewIndex] = useState(0);
  const [allowBack, setAllowBack] = useState(false);

  const [nextBlockTitle, setNextBlockTitle] = useState<string | null>(null);
  const [timeUpMode, setTimeUpMode] = useState<'finish' | 'block'>('finish');
  const [disconnected, setDisconnected] = useState(false);

  // ── Серверный таймер: deadline из time_left_sec, полученного с сервера ──────
  // Источник истины — серверный time_left_sec. deadlineRef ВСЕГДА выставляется из
  // последнего серверного значения; локальный интервал лишь интерполирует между
  // синхронизациями и НИКОГДА сам не завершает тест — он лишь дёргает /current на нуле.
  const deadlineRef = useRef<number>(0);
  const timerFiredRef = useRef<boolean>(false);
  const itemShownAtRef = useRef<number>(Date.now());
  const timerZeroRef = useRef<() => void>(() => {});

  /** Синхронизировать локальный таймер с серверным остатком (секунды). */
  const syncTimer = useCallback((sec: number) => {
    deadlineRef.current = Date.now() + sec * 1000;
    timerFiredRef.current = false;
    setTimeLeft(sec);
  }, []);

  // ── Загрузка текущего задания (frontier или обзорный reviewIndex) ───────────
  const fetchCurrent = useCallback(
    async (reviewIndex?: number) => {
      if (!token) return;
      const url =
        reviewIndex == null
          ? `/public/test/${token}/current`
          : `/public/test/${token}/current?index=${reviewIndex}`;
      const res = await publicClient.get<CurrentResp>(url);
      const d = res.data;
      setDisconnected(false);

      if (d.status === 'in_progress' && d.item) {
        const secs = d.block ? d.block.time_left_sec : d.time_left_sec ?? 0;
        syncTimer(secs);
        setCurrent(d);
        setSelectedOptionId(null);
        itemShownAtRef.current = Date.now();
        if (reviewIndex == null) {
          setFrontierIndex(d.index);
          setViewIndex(d.index);
        } else if (d.index === reviewIndex) {
          setViewIndex(reviewIndex);
        } else {
          // Сервер проигнорировал ?index → allow_back у теста НЕТ. Снимаем обзор.
          setViewIndex(d.index);
          setFrontierIndex(d.index);
          setAllowBack(false);
        }
        setPhase('question');
      } else if (d.status === 'awaiting_next_block') {
        setNextBlockTitle(d.next_block_title ?? null);
        setPhase('blockIntro');
      } else if (d.status === 'completed') {
        setPhase('done');
      } else {
        setPhase('start');
      }
    },
    [token, syncTimer],
  );

  /** Обёртка сетевой устойчивости: HTTP-ошибки прокидывает, обрыв связи → «переподключение». */
  const withNet = useCallback(async (fn: () => Promise<void>) => {
    try {
      await fn();
    } catch (e: unknown) {
      if (errStatus(e) === 410) {
        setPhase('expired');
        return;
      }
      if (!hasResponse(e)) {
        setDisconnected(true);
        return;
      }
      throw e;
    }
  }, []);

  // ── Первичная загрузка /info ────────────────────────────────────────────────
  useEffect(() => {
    if (!token) {
      setPhase('notfound');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await publicClient.get<TestInfo>(`/public/test/${token}/info`);
        if (cancelled) return;
        const data = res.data;
        setInfo(data);
        setAllowBack(data.kind === 'blocked');

        if (data.status === 'completed') {
          setPhase('done');
        } else if (data.status === 'expired') {
          setPhase('expired');
        } else if (data.status === 'started') {
          // Возобновление начатой попытки — подтягиваем текущее состояние с сервера.
          await withNet(() => fetchCurrent());
        } else {
          setPhase('start');
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const st = errStatus(e);
        if (st === 404) setPhase('notfound');
        else if (st === 410) setPhase('expired');
        else setPhase('loadError');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, fetchCurrent, withNet]);

  // ── Таймер: локальный интервал только рисует; на нуле спрашивает сервер ──────
  timerZeroRef.current = () => {
    void withNet(async () => {
      if (!token) return;
      const res = await publicClient.get<CurrentResp>(`/public/test/${token}/current`);
      const d = res.data;
      if (d.status === 'in_progress' && d.item) {
        const secs = d.block ? d.block.time_left_sec : d.time_left_sec ?? 0;
        if (secs > 0) {
          // Сервер говорит: время ещё есть (наш локальный отсчёт спешил) → ре-синк.
          syncTimer(secs);
          if (d.item.id !== current?.item?.id) {
            setCurrent(d);
            setSelectedOptionId(null);
            itemShownAtRef.current = Date.now();
          }
          return;
        }
      }
      if (d.status === 'awaiting_next_block') {
        setNextBlockTitle(d.next_block_title ?? null);
        setTimeUpMode('block');
        setPhase('timeUp');
      } else if (d.status === 'completed') {
        setTimeUpMode('finish');
        setPhase('timeUp');
      } else if (d.status === 'in_progress') {
        // secs<=0 но статус ещё in_progress — подтвердим завершение повторным запросом позже.
        syncTimer(0);
      }
    });
  };

  useEffect(() => {
    if (phase !== 'question') return;
    const id = setInterval(() => {
      const remain = Math.max(0, Math.ceil((deadlineRef.current - Date.now()) / 1000));
      setTimeLeft(remain);
      if (remain <= 0 && !timerFiredRef.current) {
        timerFiredRef.current = true;
        timerZeroRef.current();
      }
    }, 250);
    return () => clearInterval(id);
  }, [phase]);

  // ── Автопереподключение при обрыве связи (таймер продолжает идти) ────────────
  useEffect(() => {
    if (!disconnected) return;
    if (phase !== 'question' && phase !== 'blockIntro') return;
    const id = setInterval(() => {
      void withNet(() => fetchCurrent());
    }, 4000);
    return () => clearInterval(id);
  }, [disconnected, phase, fetchCurrent, withNet]);

  // ── Старт (согласие → POST /start) ──────────────────────────────────────────
  const handleStart = async () => {
    if (!agreed || !token || starting) return;
    setStarting(true);
    setStartError(null);
    try {
      await publicClient.post(`/public/test/${token}/start`, { consent: true });
      await withNet(() => fetchCurrent());
    } catch (e: unknown) {
      const st = errStatus(e);
      if (st === 409) setPhase('done');
      else if (st === 410) setPhase('expired');
      else if (st === 403) setStartError('Для прохождения теста требуется согласие на обработку данных.');
      else if (!hasResponse(e)) setStartError('Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.');
      else setStartError('Не удалось начать тест. Попробуйте ещё раз.');
    } finally {
      setStarting(false);
    }
  };

  // ── Отправка ответа на текущее задание (frontier) ───────────────────────────
  const submitFrontier = async () => {
    if (!token || !current?.item || !selectedOptionId || submitting) return;
    setSubmitting(true);
    try {
      const res = await publicClient.post<AnswerResp>(`/public/test/${token}/answer`, {
        item_id: current.item.id,
        chosen_option_id: selectedOptionId,
        time_ms: Math.max(0, Date.now() - itemShownAtRef.current),
      });
      const s = res.data.status;
      if (s === 'completed') {
        setPhase('finished');
      } else {
        // in_progress | awaiting_next_block → сервер сам скажет через /current.
        await withNet(() => fetchCurrent());
      }
    } catch (e: unknown) {
      const st = errStatus(e);
      const code = errCode(e);
      if (st === 410 && code === 'TIME_EXPIRED') {
        setTimeUpMode('finish');
        setPhase('timeUp');
      } else if (st === 410 && code === 'BLOCK_TIME_EXPIRED') {
        setTimeUpMode('block');
        setPhase('timeUp');
      } else if (st === 410) {
        setPhase('expired');
      } else if (st === 409) {
        // ALREADY_ANSWERED / NOT_CURRENT_ITEM — рассинхрон, перечитываем состояние.
        await withNet(() => fetchCurrent());
      } else if (!hasResponse(e)) {
        setDisconnected(true);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ── Обзорная навигация внутри блока (allow_back) ─────────────────────────────
  const isReviewing = viewIndex < frontierIndex;

  const goBack = async () => {
    if (submitting || viewIndex <= 0) return;
    setSubmitting(true);
    try {
      await withNet(() => fetchCurrent(viewIndex - 1));
    } finally {
      setSubmitting(false);
    }
  };

  const goForwardReview = async () => {
    // Только на обзорном задании: перейти вперёд БЕЗ сохранения выбора.
    if (submitting || !isReviewing) return;
    setSubmitting(true);
    try {
      const next = viewIndex + 1;
      if (next >= frontierIndex) await withNet(() => fetchCurrent());
      else await withNet(() => fetchCurrent(next));
    } finally {
      setSubmitting(false);
    }
  };

  const submitReviewChange = async () => {
    // На обзорном задании «Далее»: если выбран вариант — перезаписать ответ, затем вперёд.
    if (!token || !current?.item || submitting) return;
    if (!selectedOptionId) {
      await goForwardReview();
      return;
    }
    setSubmitting(true);
    try {
      await publicClient.post<AnswerResp>(`/public/test/${token}/answer`, {
        item_id: current.item.id,
        chosen_option_id: selectedOptionId,
        time_ms: Math.max(0, Date.now() - itemShownAtRef.current),
      });
      const next = viewIndex + 1;
      if (next >= frontierIndex) await withNet(() => fetchCurrent());
      else await withNet(() => fetchCurrent(next));
    } catch (e: unknown) {
      const st = errStatus(e);
      if (st === 410 && errCode(e) === 'BLOCK_TIME_EXPIRED') {
        setTimeUpMode('block');
        setPhase('timeUp');
      } else if (st === 410) {
        setPhase('expired');
      } else if (st === 409) {
        await withNet(() => fetchCurrent());
      } else if (!hasResponse(e)) {
        setDisconnected(true);
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ── Заставка блока → /block/next ────────────────────────────────────────────
  const startNextBlock = async () => {
    if (!token || submitting) return;
    setSubmitting(true);
    try {
      const res = await publicClient.post<BlockNextResp>(`/public/test/${token}/block/next`);
      if (res.data.status === 'completed') {
        setPhase('finished');
      } else {
        await withNet(() => fetchCurrent());
      }
    } catch (e: unknown) {
      const st = errStatus(e);
      if (st === 410) setPhase('expired');
      else if (st === 409) await withNet(() => fetchCurrent());
      else if (!hasResponse(e)) setDisconnected(true);
    } finally {
      setSubmitting(false);
    }
  };

  // ── «Продолжить» из модалки «время истекло» ─────────────────────────────────
  const continueFromTimeUp = async () => {
    if (timeUpMode === 'finish') {
      setPhase('finished');
    } else {
      await withNet(() => fetchCurrent());
    }
  };

  // ---------------------------------------------------------------------------
  // Рендер
  // ---------------------------------------------------------------------------
  const co = info?.company_name ? `· для кандидатов «${info.company_name}»` : '';

  const Brand = ({ suffix }: { suffix?: string }) => (
    <div className="brand">
      <span className="mark">👩🏻</span> Глафира <span className="co">{suffix ?? co}</span>
    </div>
  );

  const Foot = () => <div className="foot">Работает на «Глафире» 💃</div>;

  // ── loading ────────────────────────────────────────────────────────────────
  if (phase === 'loading') {
    return (
      <div className="test-page">
        <div className="load-center">
          <span className="spinner" /> Загрузка теста…
        </div>
      </div>
    );
  }

  // ── notfound / expired / done / loadError (служебные) ───────────────────────
  if (phase === 'notfound' || phase === 'expired' || phase === 'done' || phase === 'loadError') {
    return (
      <div className="test-page grad">
        <div className="pg">
          <Brand />
          {phase === 'expired' && (
            <div className="card state-card">
              <div className="ico dead">⏳</div>
              <h2>Срок ссылки истёк</h2>
              <p>
                Ссылка больше недействительна. Если вы всё ещё участвуете в отборе, напишите рекрутёру —
                он вышлет новую.
              </p>
              {info?.test_name && <div className="fine">Тест «{info.test_name}»</div>}
            </div>
          )}
          {phase === 'notfound' && (
            <div className="card state-card">
              <div className="ico dead">⏳</div>
              <h2>Ссылка не найдена</h2>
              <p>
                Проверьте, что вы открыли ссылку из письма или сообщения целиком. Если не получается —
                напишите рекрутёру.
              </p>
            </div>
          )}
          {phase === 'done' && (
            <div className="card state-card">
              <div className="ico done">✓</div>
              <h2>Этот тест уже пройден</h2>
              <p>
                Вы уже проходили этот тест. Результат передан рекрутёру — повторное прохождение не
                требуется и не повлияет на оценку.
              </p>
              <div className="fine">Если это были не вы — сообщите рекрутёру</div>
            </div>
          )}
          {phase === 'loadError' && (
            <div className="card state-card">
              <div className="ico net">⚡︎</div>
              <h2>Не удалось загрузить</h2>
              <p>Проверьте интернет-соединение и обновите страницу.</p>
              <div className="net-strip">
                <span className="spinner" /> Проблема со связью
              </div>
            </div>
          )}
        </div>
        <Foot />
      </div>
    );
  }

  // ── finished ────────────────────────────────────────────────────────────────
  if (phase === 'finished') {
    return (
      <div className="test-page grad">
        <div className="pg">
          <Brand />
          <div className="card state-card">
            <div className="ico ok">✓</div>
            <h2>Тест завершён</h2>
            <p>
              Спасибо! Ваши ответы сохранены и переданы рекрутёру. Он свяжется с вами и расскажет о
              следующем шаге.
            </p>
          </div>
        </div>
        <Foot />
      </div>
    );
  }

  // ── start (экран 1) ──────────────────────────────────────────────────────────
  if (phase === 'start' && info) {
    const single = info.kind === 'single';
    return (
      <div className="test-page grad">
        <div className="pg">
          <Brand />
          <div className="card">
            <h1>{info.test_name}</h1>
            <p className="sub">{info.instruction}</p>

            <div className="facts">
              <div className="fact">
                ◻︎ <b>{info.item_count}</b> заданий
              </div>
              {single && info.duration_min != null && (
                <div className="fact">
                  ⏱ <b>{info.duration_min}</b> минут
                </div>
              )}
              {!single && (
                <div className="fact">
                  ▤ <b>{info.blocks.length}</b> блоков
                </div>
              )}
              {single ? (
                <div className="fact warn">Таймер идёт непрерывно и на паузу не ставится</div>
              ) : (
                <div className="fact warn">На каждый блок отведено своё время</div>
              )}
            </div>

            <div className="block-h">Как проходить</div>
            <ul className="rules">
              {single ? (
                <>
                  <li>
                    <span className="n">1</span>
                    <span>Одно задание за раз. Выберите вариант — и переходите к следующему.</span>
                  </li>
                  <li>
                    <span className="n">2</span>
                    <span>Вернуться к предыдущему заданию нельзя, поэтому отвечайте вдумчиво.</span>
                  </li>
                  <li>
                    <span className="n">3</span>
                    <span>
                      Отвечайте как можно точнее. Если сомневаетесь — выберите наиболее подходящий
                      вариант.
                    </span>
                  </li>
                  <li>
                    <span className="n">4</span>
                    <span>Когда время выйдет, тест завершится сам. Всё, что вы успели, сохранится.</span>
                  </li>
                </>
              ) : (
                <>
                  <li>
                    <span className="n">1</span>
                    <span>Тест состоит из нескольких блоков, у каждого — своё время.</span>
                  </li>
                  <li>
                    <span className="n">2</span>
                    <span>Внутри блока можно вернуться к предыдущему заданию и изменить ответ.</span>
                  </li>
                  <li>
                    <span className="n">3</span>
                    <span>
                      Между блоками только вперёд — к завершённому блоку вернуться нельзя. Пауза между
                      блоками не ограничена.
                    </span>
                  </li>
                  <li>
                    <span className="n">4</span>
                    <span>Когда время блока выйдет, он завершится сам. Ответы сохранятся.</span>
                  </li>
                </>
              )}
            </ul>

            {single && (
              <>
                <div className="block-h">Пример задания</div>
                <div className="example">
                  <div className="mini">
                    {MINI_EXAMPLE.map((cell, i) => (
                      <div key={i} className={`c${i === 8 ? ' ans' : ''}`}>
                        <MatrixCell params={cell} />
                      </div>
                    ))}
                  </div>
                  <div className="ex-txt">
                    В строках меняется фигура, в столбцах — заливка: пусто → штриховка → сплошная. В пустой
                    клетке должен быть <b>сплошной треугольник</b> — он подставлен, клетка обведена зелёным.
                    <br />
                    <br />
                    Этот пример обучающий и в зачёт не идёт.
                  </div>
                </div>
              </>
            )}

            <label className="consent">
              <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
              <span>
                Я даю согласие на обработку моих персональных данных и результатов тестирования
                {info.company_name ? ` компанией «${info.company_name}»` : ''} в целях подбора персонала
                (152-ФЗ).
              </span>
            </label>
            <button className="cta" disabled={!agreed || starting} onClick={handleStart}>
              {starting ? 'Запускаем…' : 'Начать тест'}
            </button>
            {startError && <p className="cta-note" style={{ color: 'var(--status-error)' }}>{startError}</p>}
            <p className="cta-note">
              {single
                ? `После нажатия таймер запустится${
                    info.duration_min != null ? ` — убедитесь, что вас ${info.duration_min} минут никто не отвлечёт` : ''
                  }.`
                : 'После нажатия начнётся первый блок и пойдёт его таймер.'}
            </p>
          </div>
          <Foot />
        </div>
      </div>
    );
  }

  // ── blockIntro (экран 4) ──────────────────────────────────────────────────────
  if (phase === 'blockIntro' && info) {
    const blk = info.blocks.find((b) => b.title === nextBlockTitle) ?? null;
    const idx = blk ? blk.index : 0;
    const example = blk ? BLOCK_EXAMPLES[blk.key] : undefined;
    return (
      <div className="test-page grad">
        <div className="pg">
          <Brand suffix={`· ${info.test_name}`} />
          <div className="card">
            <span className="blk-num">
              Блок {idx + 1} из {info.blocks.length}
            </span>
            <h1>{nextBlockTitle ?? 'Следующий блок'}</h1>
            <p className="sub">
              Отвечайте по одному заданию. Внутри блока можно вернуться к предыдущему заданию и изменить
              ответ. Время блока пойдёт после нажатия кнопки.
            </p>
            {example && (
              <div className="ex-solved">
                <div className="t">Разобранный пример</div>
                <div className="q">{example.q}</div>
                <div className="a">{example.a}</div>
              </div>
            )}
            {blk && (
              <div className="facts">
                <div className="fact">
                  ◻︎ <b>{blk.item_count}</b> заданий
                </div>
                <div className="fact">
                  ⏱ <b>{blk.duration_min}</b> минут на блок
                </div>
              </div>
            )}
            <p className="cta-note" style={{ textAlign: 'left', margin: '14px 0 16px' }}>
              Таймер блока начнётся после нажатия. Между блоками можно отдохнуть сколько нужно — пауза не
              ограничена.
            </p>
            <button className="cta" disabled={submitting} onClick={startNextBlock}>
              {submitting ? 'Загружаем…' : 'Начать блок'}
            </button>
            {disconnected && (
              <div className="net-strip">
                <span className="spinner" /> Переподключение…
              </div>
            )}
          </div>
          <Foot />
        </div>
      </div>
    );
  }

  // ── question (экраны 2/3) + timeUp (экран 5 как оверлей) ─────────────────────
  if ((phase === 'question' || phase === 'timeUp') && info && current?.item) {
    const item = current.item;
    const isMatrix = item.kind === 'matrix';
    const secs = timeLeft ?? 0;
    const timerCls = secs <= 60 ? 'timer crit' : secs <= 180 ? 'timer warn' : 'timer';
    const total = current.total || 1;
    const displayNum = current.index + 1;
    const progressPct = Math.min(100, Math.round((displayNum / total) * 100));
    const dimmed = phase === 'timeUp';

    return (
      <div className="test-page">
        <div className="tbar">
          <div className="tname">
            <span className="mk">👩🏻</span>
            <span>{info.test_name}</span>
          </div>
          <div className="tprog">
            <div className="lbl">
              {current.block && (
                <span className="blk">
                  Блок {current.block.index + 1} из {current.block.total} · {current.block.title}
                </span>
              )}
              <span>
                Задание <b>{displayNum}</b> из {total}
              </span>
            </div>
            <div className="bar">
              <i style={{ width: `${progressPct}%` }} />
            </div>
          </div>
          <div className={timerCls}>
            <span className="dot" />
            <span className="v">{fmtTime(secs)}</span>
          </div>
        </div>

        <div className="task" style={dimmed ? { filter: 'blur(2px)', opacity: 0.5 } : undefined}>
          {isMatrix ? (
            <MatrixQuestion item={item} selectedOptionId={selectedOptionId} onSelect={setSelectedOptionId} />
          ) : (
            <TextQuestion
              item={item}
              blockTitle={current.block?.title}
              selectedOptionId={selectedOptionId}
              onSelect={setSelectedOptionId}
            />
          )}
        </div>

        {phase === 'question' && (
          <div className="tfoot">
            {allowBack ? (
              <>
                <button className="btn" disabled={viewIndex <= 0 || submitting} onClick={goBack}>
                  Назад
                </button>
                <button
                  className="btn ghost"
                  disabled={!isReviewing || submitting}
                  onClick={goForwardReview}
                  title={isReviewing ? undefined : 'Чтобы двигаться дальше, ответьте на текущее задание'}
                >
                  Пропустить
                </button>
                <span className="sp" />
                {disconnected && <span className="hint">Переподключение…</span>}
                {isReviewing ? (
                  <button className="btn pri" disabled={submitting} onClick={submitReviewChange}>
                    Далее
                  </button>
                ) : (
                  <button className="btn pri" disabled={!selectedOptionId || submitting} onClick={submitFrontier}>
                    Далее
                  </button>
                )}
              </>
            ) : (
              <>
                <span className="hint">Вернуться назад нельзя</span>
                <span className="sp" />
                {disconnected && <span className="hint">Переподключение…</span>}
                <button className="btn pri" disabled={!selectedOptionId || submitting} onClick={submitFrontier}>
                  Далее
                </button>
              </>
            )}
          </div>
        )}

        {phase === 'timeUp' && (
          <div className="ovl">
            <div className="modal">
              <div className="ico">⏱</div>
              <h2>{timeUpMode === 'block' ? 'Время блока вышло' : 'Время вышло'}</h2>
              <p>
                {timeUpMode === 'block'
                  ? 'Это нормально — блоки рассчитаны так, что решить все задания успевают немногие. Ответы сохранены, впереди ещё есть блоки.'
                  : 'Тест завершён по времени. Всё, что вы успели ответить, сохранено и передано рекрутёру.'}
              </p>
              <button className="cta" onClick={continueFromTimeUp}>
                Продолжить
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ── fallback (не должно достигаться) ─────────────────────────────────────────
  return (
    <div className="test-page">
      <div className="load-center">
        <span className="spinner" /> Загрузка…
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Матрица-вопрос + 8 вариантов
// ---------------------------------------------------------------------------
function MatrixQuestion({
  item,
  selectedOptionId,
  onSelect,
}: {
  item: PubItem;
  selectedOptionId: string | null;
  onSelect: (id: string) => void;
}) {
  const cells = (item.body.cells as (CellParams | null)[][] | undefined) ?? [];
  return (
    <>
      <div className="matrix">
        {cells.flatMap((row, r) =>
          row.map((cell, c) =>
            cell == null ? (
              <div key={`${r}-${c}`} className="c q">
                ?
              </div>
            ) : (
              <div key={`${r}-${c}`} className="c">
                <MatrixCell params={cell} />
              </div>
            ),
          ),
        )}
      </div>
      <div className="ask">Какая фигура должна стоять на месте знака вопроса?</div>
      <div className="opts">
        {item.options.map((o, i) => (
          <button
            key={o.id}
            className={`opt${selectedOptionId === o.id ? ' sel' : ''}`}
            onClick={() => onSelect(o.id)}
          >
            <span className="no">{i + 1}</span>
            {o.params && <MatrixCell params={o.params} />}
          </button>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Текст-вопрос (аналогия / числовой ряд / исключение / обобщение)
// ---------------------------------------------------------------------------
function TextQuestion({
  item,
  blockTitle,
  selectedOptionId,
  onSelect,
}: {
  item: PubItem;
  blockTitle?: string;
  selectedOptionId: string | null;
  onSelect: (id: string) => void;
}) {
  const body = item.body as {
    kind?: string;
    prompt?: string;
    terms?: unknown;
  };
  const kind = body.kind ?? '';

  let visual: ReactNode = null;
  let instr = typeof body.prompt === 'string' ? body.prompt : '';

  if (kind === 'analogy' && body.terms && typeof body.terms === 'object' && !Array.isArray(body.terms)) {
    const t = body.terms as { a?: string; b?: string; c?: string };
    visual = (
      <div className="analogy">
        {t.a} <span className="op">:</span> {t.b} <span className="op">=</span> {t.c} <span className="op">:</span>{' '}
        <span className="qm">?</span>
      </div>
    );
    instr = 'Во второй паре подберите недостающее слово так, чтобы связь была такой же, как в первой.';
  } else if (kind === 'series' && Array.isArray(body.terms)) {
    const seq = (body.terms as (number | string)[]).map(String);
    visual = <div className="series">{seq.join('   ')}   …   ?</div>;
  } else if (kind === 'generalization' && Array.isArray(body.terms)) {
    const words = (body.terms as string[]).map(String);
    visual = (
      <div className="analogy">
        {words.join(' ')}
        <span className="op"> · </span>
        <span className="qm">?</span>
      </div>
    );
  } else if (kind === 'exclusion') {
    // Слова-варианты и есть задание — крупного «вопроса» нет, только инструкция + карточки.
    visual = null;
  }

  return (
    <>
      <div className="qcard">
        {blockTitle && <div className="qkind">{blockTitle}</div>}
        {visual}
        {instr && <p className="qinstr">{instr}</p>}
      </div>
      <div className="choices">
        {item.options.map((o, i) => (
          <button
            key={o.id}
            className={`choice${selectedOptionId === o.id ? ' sel' : ''}`}
            onClick={() => onSelect(o.id)}
          >
            <span className="ltr">{LETTERS[i] ?? i + 1}</span>
            {o.text}
          </button>
        ))}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// Статичный обучающий мини-пример на стартовом экране (фигура×заливка).
// Последняя ячейка (индекс 8) — «подставленный» ответ, обведена зелёным.
// ---------------------------------------------------------------------------
const MINI_EXAMPLE: CellParams[] = [
  { shape: 'circle', fill: 'empty' },
  { shape: 'circle', fill: 'hatch-h' },
  { shape: 'circle', fill: 'solid' },
  { shape: 'square', fill: 'empty' },
  { shape: 'square', fill: 'hatch-h' },
  { shape: 'square', fill: 'solid' },
  { shape: 'triangle', fill: 'empty' },
  { shape: 'triangle', fill: 'hatch-h' },
  { shape: 'triangle', fill: 'solid' },
];
