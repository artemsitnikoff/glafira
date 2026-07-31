import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
// Разводящая переиспользует анатомию Архива (archive-head/filter-bar/archive-grid/
// arch-card/result-badge/stats-row/empty-pane скоуплены под .content-inner).
// Страницы lazy → без явного импорта CSS-чанк архива не подтянется.
import './archive/Archive.css';
import './AllVacanciesPage.css';
import { Icon } from '@/components/ui/Icon';
import { Skeleton } from '@/components/ui/Skeleton';
import { useVacancies } from '@/api/hooks/useVacancies';
import { useAuthStore } from '@/store/authStore';
import type { Vacancy } from '@/api/aliases';

// Кап списка: сервер отдаёт максимум 100 за страницу. Фильтрация/группировка —
// клиентские (как в эталоне). При >100 активных показываем первые 100.
const PAGE_SIZE = 100;

// openapi не регенерён — бек добавил к VacancyDetail агрегаты для разводящей
// «Все вакансии»: candidates_count / new_count / hired / request_num. Расширяем
// тип локально + as-cast (конвенция §3: локальный тип + пометка).
type AllVacancy = Vacancy & {
  candidates_count?: number;
  new_count?: number;
  hired?: number;
  request_num?: number | null;
};

function daysWord(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'день';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return 'дня';
  return 'дней';
}

function daysOpen(createdAt: string): number {
  const t = new Date(createdAt).getTime();
  if (Number.isNaN(t)) return 0;
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}

// scope: 'mine' | 'all' | <responsible_user_id>
type Scope = string;

export default function AllVacanciesPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const { data, isLoading, isError } = useVacancies({ status: 'active', page: 1, page_size: PAGE_SIZE });
  const items = useMemo(() => (data?.items ?? []) as AllVacancy[], [data]);
  const total = data?.total ?? 0;

  const [scope, setScope] = useState<Scope>('mine');
  const [dept, setDept] = useState<string>('all');
  const [query, setQuery] = useState('');

  const isMine = (v: AllVacancy) => !!v.responsible_user_id && v.responsible_user_id === user?.id;

  // Список ответственных для сегмента — из реальных данных (без демо-состава).
  const owners = useMemo(
    () =>
      Array.from(
        new Map(
          items
            .filter((v) => v.responsible_user)
            .map((v) => [v.responsible_user!.id, v.responsible_user!])
        ).values()
      ),
    [items]
  );

  // Отделы для дропдауна — реальные значения.
  const departments = useMemo(
    () => Array.from(new Set(items.map((v) => v.department).filter(Boolean) as string[])).sort(),
    [items]
  );

  const list = useMemo(
    () =>
      items.filter((v) => {
        if (scope === 'mine' && !isMine(v)) return false;
        if (scope !== 'mine' && scope !== 'all' && v.responsible_user_id !== scope) return false;
        if (dept !== 'all' && v.department !== dept) return false;
        if (query && !v.name.toLowerCase().includes(query.toLowerCase())) return false;
        return true;
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, scope, dept, query, user?.id]
  );

  const mine = useMemo(() => items.filter(isMine), [items, user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Группы строим из ОТФИЛЬТРОВАННОГО list — бейдж «Мои · N» должен совпадать с числом
  // карточек под ним (при активном фильтре отдел/поиск мои сокращаются вместе с карточками).
  const filteredMine = list.filter(isMine);
  const filteredOthers = list.filter((v) => !isMine(v));
  const groups =
    scope === 'all'
      ? [
          { title: `Мои · ${filteredMine.length}`, items: filteredMine },
          { title: 'Другие рекрутеры', items: filteredOthers },
        ]
      : [{ title: null as string | null, items: list }];

  const hasFilters = scope !== 'mine' || dept !== 'all' || query !== '';
  const reset = () => {
    setScope('mine');
    setDept('all');
    setQuery('');
  };
  const resetAll = () => {
    setScope('all');
    setDept('all');
    setQuery('');
  };

  const ownerLabel = (v: AllVacancy) =>
    isMine(v) ? 'Я' : v.responsible_user?.full_name ?? '—';

  // Создавать вакансию может не-менеджер (роут /vacancies/new под RoleGuard admin/recruiter,
  // сайдбар прячет «Новую» для manager). Иначе кнопка молча выкинула бы менеджера на /home (§0).
  const canCreate = user?.role !== 'manager';

  if (isLoading) {
    return (
      <div className="content-inner av-page">
        <div className="archive-head">
          <h1>Все вакансии</h1>
          <Skeleton width={180} height={14} />
        </div>
        <div className="filter-bar">
          <Skeleton width={260} height={28} />
          <Skeleton width={180} height={28} />
          <div className="filter-spacer" />
          <Skeleton width={240} height={28} />
        </div>
        <div className="archive-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} height={170} />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="content-inner av-page">
        <div className="archive-head">
          <h1>Все вакансии</h1>
        </div>
        <div className="empty-pane" style={{ minHeight: 280 }}>
          <div className="empty-illust">
            <Icon name="alert-triangle" size={36} />
          </div>
          <h3>Не удалось загрузить вакансии</h3>
          <p>Обновите страницу — если ошибка повторится, попробуйте позже.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="content-inner av-page">
      <div className="archive-head">
        <h1>Все вакансии</h1>
        <div className="sub">
          {scope === 'mine' ? (
            <>
              <span className="t-mono">{mine.length}</span> моих из{' '}
              <span className="t-mono">{total}</span> активных
            </>
          ) : (
            <>
              Показано <span className="t-mono">{list.length}</span> из{' '}
              <span className="t-mono">{total}</span>
            </>
          )}
        </div>
      </div>

      <div className="filter-bar">
        <div className="filter-group">
          <span className="filter-label">Ответственный</span>
          <div className="seg-sm">
            <button className={scope === 'mine' ? 'active' : ''} onClick={() => setScope('mine')}>
              Мои
            </button>
            <button className={scope === 'all' ? 'active' : ''} onClick={() => setScope('all')}>
              Все
            </button>
            {owners
              .filter((o) => o.id !== user?.id)
              .map((o) => (
                <button
                  key={o.id}
                  className={scope === o.id ? 'active' : ''}
                  onClick={() => setScope(o.id)}
                >
                  {o.full_name}
                </button>
              ))}
          </div>
        </div>

        {departments.length > 0 && (
          <div className="filter-group">
            <span className="filter-label">Отдел</span>
            <FilterDropdown value={dept} options={departments} onChange={setDept} />
          </div>
        )}

        <div className="filter-spacer" />

        <div className="submenu-search" style={{ width: 240, height: 28 }}>
          <Icon name="search" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
          <input
            placeholder="Поиск по вакансиям…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>

        {hasFilters && (
          <button className="btn btn-ghost btn-sm" onClick={reset}>
            <Icon name="x" size={14} /> Сбросить
          </button>
        )}
        {canCreate && (
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/vacancies/new')}>
            <Icon name="plus" size={14} /> Новая
          </button>
        )}
      </div>

      {list.length === 0 ? (
        <div className="empty-pane" style={{ minHeight: 280 }}>
          <div className="empty-illust">
            <Icon name={items.length === 0 ? 'briefcase' : 'filter'} size={36} />
          </div>
          <h3>{items.length === 0 ? 'Активных вакансий нет' : 'Ничего не найдено'}</h3>
          <p>
            {items.length === 0
              ? 'Создайте вакансию — она появится здесь и в подсписке слева.'
              : 'По заданным фильтрам вакансий нет. Попробуйте сбросить часть условий.'}
          </p>
          {items.length === 0 ? (
            canCreate ? (
              <button className="btn btn-secondary btn-sm" onClick={() => navigate('/vacancies/new')}>
                Новая вакансия
              </button>
            ) : null
          ) : (
            <button className="btn btn-secondary btn-sm" onClick={resetAll}>
              Сбросить фильтры
            </button>
          )}
        </div>
      ) : (
        groups.map((g, gi) =>
          g.items.length === 0 ? null : (
            <div key={gi} style={{ marginBottom: 18 }}>
              {g.title && <div className="av-group-title">{g.title}</div>}
              <div className="archive-grid">
                {g.items.map((v) => {
                  const days = daysOpen(v.created_at);
                  const newCount = v.new_count ?? 0;
                  const hired = v.hired ?? 0;
                  const candidates = v.candidates_count ?? 0;
                  return (
                    <div key={v.id} className="arch-card" onClick={() => navigate(`/vacancies/${v.id}`)}>
                      <div className="top-row">
                        <span className="result-badge open">
                          <Icon name="briefcase" size={11} /> В работе
                        </span>
                        {newCount > 0 && <span className="av-new">+{newCount} новых</span>}
                      </div>
                      <div className="title">{v.name}</div>
                      <div className="meta">
                        {v.department || '—'}
                        <span className="sep">·</span>
                        {ownerLabel(v)}
                      </div>
                      <div className="meta" style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                        <Icon name="clock" size={13} style={{ color: 'var(--fg-3)' }} />
                        В работе {days} {daysWord(days)}
                        <span className="sep">·</span>
                        {v.city || '—'}
                        {v.request_num != null && (
                          <>
                            <span className="sep">·</span>
                            <span className="av-req">заявка №{v.request_num}</span>
                          </>
                        )}
                      </div>
                      <div className="stats-row">
                        <div className="stat-cell">
                          <span className="stat-val">{candidates}</span>
                          <span className="stat-lbl">кандидатов</span>
                        </div>
                        <div className="stat-cell">
                          <span
                            className="stat-val"
                            style={{ color: hired > 0 ? 'var(--ark-green-600)' : 'var(--fg-3)' }}
                          >
                            {hired} из {v.positions_count}
                          </span>
                          <span className="stat-lbl">нанято</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )
        )
      )}
    </div>
  );
}

function FilterDropdown({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const select = (v: string) => {
    onChange(v);
    setOpen(false);
  };
  return (
    <div className="dropdown-wrap">
      <button className={`dropdown${value !== 'all' ? ' active' : ''}`} onClick={() => setOpen((o) => !o)}>
        {value === 'all' ? 'Все' : value}
        <Icon name="chevD" size={12} />
      </button>
      {open && (
        <>
          <div className="dropdown-overlay" onClick={() => setOpen(false)} />
          <div className="dropdown-menu">
            <button className={value === 'all' ? 'active' : ''} onClick={() => select('all')}>
              Все
            </button>
            {options.map((opt) => (
              <button key={opt} className={value === opt ? 'active' : ''} onClick={() => select(opt)}>
                {opt}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
