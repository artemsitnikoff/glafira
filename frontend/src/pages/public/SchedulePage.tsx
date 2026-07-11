import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { publicClient } from '@/api/publicClient';
import './SchedulePage.css';

// ---------------------------------------------------------------------------
// Типы
// ---------------------------------------------------------------------------
interface Participant {
  name: string;
  role?: string | null;
}

interface ScheduleInfo {
  status: 'active' | 'booked' | 'expired';
  vacancy_name?: string | null;
  recruiter_name?: string | null;
  recruiter_role?: string | null;
  participants?: Participant[];
  slot_from?: string | null; // ISO UTC (только когда status='booked')
  video_link?: string | null;
}

interface Slot {
  from_utc: string; // ISO UTC
  to_utc: string;   // ISO UTC
}

// ---------------------------------------------------------------------------
// Константы
// ---------------------------------------------------------------------------
const TZ_OPTIONS = [
  { value: 'Europe/Moscow',        label: 'Москва (UTC+3)' },
  { value: 'Europe/Kaliningrad',   label: 'Калининград (UTC+2)' },
  { value: 'Europe/Samara',        label: 'Самара (UTC+4)' },
  { value: 'Asia/Yekaterinburg',   label: 'Екатеринбург (UTC+5)' },
  { value: 'Asia/Omsk',            label: 'Омск (UTC+6)' },
  { value: 'Asia/Novosibirsk',     label: 'Новосибирск (UTC+7)' },
  { value: 'Asia/Krasnoyarsk',     label: 'Красноярск (UTC+7)' },
  { value: 'Asia/Irkutsk',         label: 'Иркутск (UTC+8)' },
  { value: 'Asia/Yakutsk',         label: 'Якутск (UTC+9)' },
  { value: 'Asia/Vladivostok',     label: 'Владивосток (UTC+10)' },
  { value: 'Asia/Kamchatka',       label: 'Камчатка (UTC+12)' },
  { value: 'Asia/Almaty',          label: 'Алматы (UTC+6)' },
  { value: 'Asia/Tashkent',        label: 'Ташкент (UTC+5)' },
  { value: 'Europe/Minsk',         label: 'Минск (UTC+3)' },
  { value: 'Europe/London',        label: 'Лондон' },
  { value: 'Europe/Berlin',        label: 'Берлин/Варшава' },
  { value: 'America/New_York',     label: 'Нью-Йорк' },
  { value: 'America/Chicago',      label: 'Чикаго' },
  { value: 'America/Denver',       label: 'Денвер' },
  { value: 'America/Los_Angeles',  label: 'Лос-Анджелес' },
  { value: 'UTC',                  label: 'UTC' },
];

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

// ---------------------------------------------------------------------------
// Хелперы
// ---------------------------------------------------------------------------

/** Определить TZ пользователя автоматически, с фолбэком на Moscow */
function detectTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow';
  } catch {
    return 'Europe/Moscow';
  }
}

/** Конвертировать ISO UTC строку в объект Date (JS UTC) */
function parseUtc(iso: string): Date {
  return new Date(iso);
}

/**
 * Форматировать UTC Date → время в нужном TZ.
 * НЕ дважды конвертировать: берём UTC Date, форматируем через Intl сразу в target TZ.
 */
function formatTime(utcDate: Date, tz: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: tz,
    }).format(utcDate);
  } catch {
    return new Intl.DateTimeFormat('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'UTC',
    }).format(utcDate);
  }
}

/** Форматировать UTC Date → дату+время в нужном TZ */
function formatDateTime(utcDate: Date, tz: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: tz,
    }).format(utcDate);
  } catch {
    return utcDate.toISOString();
  }
}

/**
 * Получить «ключ дня» UTC Date в нужном TZ в формате YYYY-MM-DD.
 * Используем Intl для получения Y/M/D в TZ — без сдвигов.
 */
function getDayKey(utcDate: Date, tz: string): string {
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: tz,
    }).formatToParts(utcDate);
    const p: Record<string, string> = {};
    parts.forEach((part) => { p[part.type] = part.value; });
    return `${p.year}-${p.month}-${p.day}`;
  } catch {
    return utcDate.toISOString().slice(0, 10);
  }
}

/** Получить Y/M/D чисел из UTC Date в нужном TZ */
function getLocalYMD(utcDate: Date, tz: string): { y: number; m: number; d: number } {
  try {
    const parts = new Intl.DateTimeFormat('en-CA', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: tz,
    }).formatToParts(utcDate);
    const p: Record<string, string> = {};
    parts.forEach((part) => { p[part.type] = part.value; });
    return { y: parseInt(p.year), m: parseInt(p.month) - 1, d: parseInt(p.day) };
  } catch {
    return { y: utcDate.getUTCFullYear(), m: utcDate.getUTCMonth(), d: utcDate.getUTCDate() };
  }
}

/** Инициалы из имени */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((s) => s[0].toUpperCase())
    .join('');
}

/** Локализованное название месяца/года */
function monthYearLabel(year: number, month: number, tz: string): string {
  try {
    const d = new Date(Date.UTC(year, month, 1, 12, 0, 0));
    return new Intl.DateTimeFormat('ru-RU', {
      year: 'numeric',
      month: 'long',
      timeZone: tz,
    }).format(d);
  } catch {
    return `${year}-${month + 1}`;
  }
}

// ---------------------------------------------------------------------------
// Компонент
// ---------------------------------------------------------------------------

export default function SchedulePage() {
  const { token } = useParams<{ token: string }>();

  const [info, setInfo] = useState<ScheduleInfo | null>(null);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loadingInfo, setLoadingInfo] = useState(true);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [infoError, setInfoError] = useState<'expired' | 'unknown' | null>(null);
  const [slotsError, setSlotsError] = useState(false);

  const [tz, setTz] = useState<string>(detectTz);
  // Отображаемый месяц/год
  const [calYear, setCalYear] = useState<number>(new Date().getFullYear());
  const [calMonth, setCalMonth] = useState<number>(new Date().getMonth());
  const [selectedDayKey, setSelectedDayKey] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null); // ISO UTC

  const [booking, setBooking] = useState(false);
  const [booked, setBooked] = useState(false);
  const [bookedAt, setBookedAt] = useState<string | null>(null);
  const [videoLink, setVideoLink] = useState<string | null>(null);

  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Показ тоста с авто-скрытием через 2500мс
  const showToast = (msg: string) => {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2500);
  };

  // Загрузить информацию о встрече
  useEffect(() => {
    if (!token) {
      setInfoError('unknown');
      setLoadingInfo(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await publicClient.get<ScheduleInfo>(`/schedule/${token}`);
        if (cancelled) return;
        setInfo(res.data);
        if (res.data.status === 'booked' && res.data.slot_from) {
          setBooked(true);
          setBookedAt(res.data.slot_from);
          setVideoLink(res.data.video_link ?? null);
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const status = (e as { response?: { status?: number } })?.response?.status;
        setInfoError(status === 410 ? 'expired' : 'unknown');
      } finally {
        if (!cancelled) setLoadingInfo(false);
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  // Загрузить слоты
  const fetchSlots = () => {
    if (!token) return;
    setSlotsError(false);
    setLoadingSlots(true);
    publicClient
      .get<{ slots: Slot[]; tz: string }>(`/schedule/${token}/slots`)
      .then((res) => {
        const slotsArr = res.data?.slots ?? [];
        setSlots(slotsArr);
        // Определить первый месяц со слотами
        if (slotsArr.length > 0) {
          const first = parseUtc(slotsArr[0].from_utc);
          const { y, m } = getLocalYMD(first, tz);
          setCalYear(y);
          setCalMonth(m);
        }
      })
      .catch(() => setSlotsError(true))
      .finally(() => setLoadingSlots(false));
  };

  useEffect(() => {
    if (info && info.status !== 'booked' && info.status !== 'expired') {
      fetchSlots();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info]);

  // Перегруппировать слоты по дням при смене TZ
  const slotsByDay: Record<string, Slot[]> = {};
  slots.forEach((slot) => {
    const key = getDayKey(parseUtc(slot.from_utc), tz);
    if (!slotsByDay[key]) slotsByDay[key] = [];
    slotsByDay[key].push(slot);
  });

  // Сбрасывать выбор при смене TZ
  const handleTzChange = (newTz: string) => {
    setTz(newTz);
    setSelectedDayKey(null);
    setSelectedSlot(null);
  };

  // Забронировать
  const handleBook = async () => {
    if (!selectedSlot || !token) return;
    setBooking(true);
    try {
      const res = await publicClient.post<{ video_link?: string | null }>(`/schedule/${token}/book`, {
        slot_from: selectedSlot.from_utc,
        slot_to: selectedSlot.to_utc,
      });
      setBooked(true);
      setBookedAt(selectedSlot.from_utc);
      setVideoLink(res.data?.video_link ?? null);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        showToast('Этот слот уже занят — выберите другое время');
        setSelectedSlot(null);
        setSelectedDayKey(null);
        fetchSlots();
      } else {
        showToast('Не удалось забронировать. Попробуйте ещё раз.');
      }
    } finally {
      setBooking(false);
    }
  };

  // Построить сетку календаря для текущего месяца
  const buildCalDays = () => {
    // Первый день месяца
    const firstDay = new Date(Date.UTC(calYear, calMonth, 1, 12, 0, 0));
    // День недели первого числа (0=вс, → приводим к Пн=0)
    const rawWd = firstDay.getUTCDay(); // 0=вс
    const startWd = rawWd === 0 ? 6 : rawWd - 1; // Пн=0
    // Количество дней в месяце
    const daysInMonth = new Date(Date.UTC(calYear, calMonth + 1, 0)).getUTCDate();
    // Всего ячеек (кратно 7)
    const totalCells = Math.ceil((startWd + daysInMonth) / 7) * 7;

    const today = new Date();
    const todayKey = getDayKey(today, tz);

    const cells = [];
    for (let i = 0; i < totalCells; i++) {
      const dayOffset = i - startWd;
      const date = new Date(Date.UTC(calYear, calMonth, 1 + dayOffset, 12, 0, 0));
      const { y, m, d } = getLocalYMD(date, tz);
      const key = `${y}-${String(m + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const isCurrentMonth = m === calMonth && y === calYear;
      const hasSlots = !!slotsByDay[key];
      cells.push({
        key,
        d,
        isCurrentMonth,
        hasSlots,
        isToday: key === todayKey,
        isSelected: key === selectedDayKey,
      });
    }
    return cells;
  };

  const calDays = buildCalDays();

  // Слоты для выбранного дня
  const daySlots = selectedDayKey ? (slotsByDay[selectedDayKey] ?? []) : [];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loadingInfo) {
    return (
      <div className="sched-bg">
        <div className="sched-brand">Глафира</div>
        <div className="sched-state">
          <div className="sched-spinner" />
          <div className="sched-state-msg">Загрузка…</div>
        </div>
      </div>
    );
  }

  if (infoError) {
    return (
      <div className="sched-bg">
        <div className="sched-brand">Глафира</div>
        <div className="sched-state">
          <div className="sched-err">
            {infoError === 'expired'
              ? 'Ссылка недействительна или истекла. Обратитесь к рекрутёру.'
              : 'Не удалось загрузить страницу. Попробуйте позже.'}
          </div>
        </div>
      </div>
    );
  }

  // Встреча уже назначена
  if (booked && bookedAt) {
    return (
      <div className="sched-bg">
        <div className="sched-brand">Глафира</div>
        <div className="sched-state">
          <div className="sched-booked-card">
            <div className="sched-booked-icon">✅</div>
            <div className="sched-booked-title">Встреча назначена</div>
            <div className="sched-booked-time">
              {formatDateTime(parseUtc(bookedAt), tz)}
            </div>
            {videoLink && (
              <div className="sched-booked-link">
                <a href={videoLink} target="_blank" rel="noopener noreferrer">
                  Ссылка на видеовстречу →
                </a>
              </div>
            )}
            {info?.participants && info.participants.length > 0 && (
              <div className="sched-booked-participants">
                На встрече:{' '}
                {info.participants.map((p) => p.name).join(', ')}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="sched-bg">
      <div className="sched-brand">
        <span>Глафира</span>
        {info?.vacancy_name && (
          <span style={{ color: 'var(--fg-3)', fontWeight: 400, fontSize: 'var(--fs-14)', marginLeft: 12 }}>
            · {info.vacancy_name}
          </span>
        )}
      </div>

      <div className="sched-layout">
        {/* Левая колонка */}
        <div className="sched-sidebar">
          {info?.recruiter_name && (
            <div className="sched-recruiter">
              <div className="sched-avatar">
                {initials(info.recruiter_name)}
              </div>
              <div className="sched-recruiter-info">
                <div className="sched-recruiter-name">{info.recruiter_name}</div>
                {info.recruiter_role && (
                  <div className="sched-recruiter-role">{info.recruiter_role}</div>
                )}
              </div>
            </div>
          )}

          <div className="sched-tagline">
            Выберите удобное время для интервью
          </div>

          {info?.vacancy_name && (
            <div className="sched-vacancy">
              <div className="sched-vacancy-label">Вакансия</div>
              {info.vacancy_name}
            </div>
          )}

          {info?.participants && info.participants.length > 0 && (
            <div>
              <div className="sched-participants-label">На встрече будут:</div>
              <div className="sched-participants">
                {info.participants.map((p, i) => (
                  <div key={i} className="sched-participant">
                    <div className="sched-avatar-sm">
                      {initials(p.name)}
                    </div>
                    <span>{p.name}{p.role ? ` · ${p.role}` : ''}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Центр — календарь */}
        <div className="sched-calendar-col">
          <div className="sched-cal-header">
            <div className="sched-cal-title">
              {monthYearLabel(calYear, calMonth, tz)}
            </div>
            <div className="sched-cal-nav">
              <button
                className="sched-cal-btn"
                onClick={() => {
                  if (calMonth === 0) { setCalYear(y => y - 1); setCalMonth(11); }
                  else setCalMonth(m => m - 1);
                }}
                aria-label="Предыдущий месяц"
              >
                ‹
              </button>
              <button
                className="sched-cal-btn"
                onClick={() => {
                  if (calMonth === 11) { setCalYear(y => y + 1); setCalMonth(0); }
                  else setCalMonth(m => m + 1);
                }}
                aria-label="Следующий месяц"
              >
                ›
              </button>
            </div>
          </div>

          <div className="sched-cal-weekdays">
            {WEEKDAYS.map((d) => (
              <div key={d} className="sched-cal-wd">{d}</div>
            ))}
          </div>

          {loadingSlots ? (
            <div className="sched-slots-empty">
              <div className="sched-spinner" style={{ margin: '0 auto' }} />
            </div>
          ) : slotsError ? (
            <div className="sched-slots-empty">
              Не удалось получить расписание
              <br />
              <button className="sched-btn-retry" onClick={fetchSlots}>Повторить</button>
            </div>
          ) : (
            <div className="sched-cal-grid">
              {calDays.map((cell, idx) => {
                const cls = [
                  'sched-cal-day',
                  !cell.isCurrentMonth ? 'other-month' : '',
                  cell.hasSlots && cell.isCurrentMonth ? 'has-slots' : '',
                  cell.isSelected ? 'selected' : '',
                  cell.isToday && !cell.isSelected ? 'today' : '',
                ].filter(Boolean).join(' ');
                return (
                  <button
                    key={idx}
                    className={cls}
                    disabled={!cell.hasSlots || !cell.isCurrentMonth}
                    onClick={() => {
                      if (cell.hasSlots && cell.isCurrentMonth) {
                        setSelectedDayKey(cell.key);
                        setSelectedSlot(null);
                      }
                    }}
                    aria-label={`${cell.d} ${cell.hasSlots ? '— есть слоты' : ''}`}
                  >
                    {cell.d}
                  </button>
                );
              })}
            </div>
          )}

          {!loadingSlots && !slotsError && slots.length === 0 && (
            <div className="sched-slots-empty">Нет доступных слотов</div>
          )}
        </div>

        {/* Правая колонка — слоты */}
        <div className="sched-slots-col">
          <div className="sched-slots-title">
            {selectedDayKey
              ? (() => {
                  const [y, m, d] = selectedDayKey.split('-').map(Number);
                  const date = new Date(Date.UTC(y, m - 1, d, 12));
                  return new Intl.DateTimeFormat('ru-RU', {
                    day: 'numeric',
                    month: 'long',
                    timeZone: tz,
                  }).format(date);
                })()
              : 'Выберите день'}
          </div>
          {daySlots.length > 0 ? (
            <div className="sched-slots-list">
              {daySlots.map((slot) => (
                <button
                  key={slot.from_utc}
                  className={`sched-slot-btn ${selectedSlot?.from_utc === slot.from_utc ? 'selected' : ''}`}
                  onClick={() => setSelectedSlot(slot)}
                >
                  {formatTime(parseUtc(slot.from_utc), tz)}
                </button>
              ))}
            </div>
          ) : selectedDayKey ? (
            <div style={{ fontSize: 'var(--fs-12)', color: 'var(--fg-3)' }}>
              Нет слотов в этот день
            </div>
          ) : (
            <div style={{ fontSize: 'var(--fs-12)', color: 'var(--fg-3)' }}>
              Нажмите на выделенный день в календаре
            </div>
          )}
        </div>
      </div>

      {/* TZ selector */}
      <div className="sched-tz-row">
        <span>Ваш часовой пояс:</span>
        <select
          className="sched-tz-select"
          value={tz}
          onChange={(e) => handleTzChange(e.target.value)}
        >
          {TZ_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
          {/* Если текущий TZ не в списке — добавить */}
          {!TZ_OPTIONS.some((o) => o.value === tz) && (
            <option value={tz}>{tz}</option>
          )}
        </select>
      </div>

      {/* Панель подтверждения */}
      {selectedSlot && (
        <div className="sched-confirm-bar">
          <div className="sched-confirm-info">
            <div className="sched-confirm-label">Выбранное время:</div>
            <div className="sched-confirm-val">
              {formatDateTime(parseUtc(selectedSlot.from_utc), tz)}
            </div>
          </div>
          <button
            className="sched-btn-book"
            disabled={booking}
            onClick={handleBook}
          >
            {booking ? 'Бронирую…' : 'Подтвердить встречу'}
          </button>
        </div>
      )}

      {/* Тост */}
      {toast && (
        <div className="sched-toast">{toast}</div>
      )}
    </div>
  );
}
