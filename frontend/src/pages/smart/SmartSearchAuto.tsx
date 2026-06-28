// Ветка В умного подбора — «Автоподбор» (сохранённые автопоиски hh.ru).
// ЧАНК A: шапка ветки + список автопоисков из реального бека (/smart/auto/*).
// Кандидаты выбранного автопоиска, нижняя карточка, оценка и «забор контакта» —
// СЛЕДУЮЩИЕ чанки (здесь только плейсхолдер при выборе автопоиска, без фейк-строк).
import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import {
  useAutoAccess,
  useAutoSearches,
  useSyncAutoSearches,
  type AutoSearch,
} from '@/api/hooks/useSmartSearch';
import './SmartSearchAuto.css';

// Форматирование чисел с разделителями (зеркало ssFmt из SmartSearchPage)
function ssaFmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return n.toLocaleString('ru-RU');
}

// Имя автопоиска приходит от hh иногда В КАВЫЧКАХ (`"Business upgrade"`) —
// срезаем ведущие/замыкающие кавычки перед обёрткой в «…».
function stripQuotes(name: string): string {
  return name.replace(/^["«»\s]+|["«»\s]+$/g, '');
}

// Короткая сводка основы оценки (вакансия/промт)
function basisLabel(b: AutoSearch['basis']): string | null {
  if (!b) return null;
  if (b.kind === 'vacancy') return 'против вакансии';
  const t = (b.prompt || '').trim();
  if (!t) return 'по промту';
  return t.length > 40 ? t.slice(0, 40) + '…' : t;
}

export function SmartSearchAuto({ onBack }: { onBack: () => void }) {
  const { data: access } = useAutoAccess();
  const { data: searches = [], isLoading, isError, error } = useAutoSearches();
  const syncMutation = useSyncAutoSearches();

  // searchId/view заведены для следующего чанка (список кандидатов) —
  // в этом чанке выбор автопоиска показывает только плейсхолдер.
  const [searchId, setSearchId] = useState<string | null>(null);

  // Нет доступа к автопоискам hh (нет привязки / 402 / 403)
  const noAccess = access && access.has_access === false;

  return (
    <div className="ss-page ssa-page">
      <SSAutoHeader onBack={onBack} poolLeft={access?.pool_left ?? null} />

      {noAccess ? (
        <SSAutoNoAccess reason={access?.reason ?? null} />
      ) : isLoading ? (
        <div className="ssa-state ssa-state-loading">
          <span className="ssa-spin" /> Загрузка автопоисков…
        </div>
      ) : isError ? (
        <div className="ssa-state ssa-state-error">
          <Icon name="alert-circle" size={16} />
          Не удалось загрузить автопоиски{error?.message ? `: ${error.message}` : '.'}
        </div>
      ) : searches.length === 0 ? (
        <div className="ssa-state ssa-state-empty">
          <Icon name="radio" size={26} className="ssa-state-ic" />
          <div className="ssa-state-title">Автопоиски не найдены</div>
          <div className="ssa-state-sub">
            Настройте сохранённый поиск на hh.ru и подпишитесь на новые резюме — он появится здесь.
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
          >
            {syncMutation.isPending
              ? <><span className="ssa-spin dark" /> Синхронизация…</>
              : <><Icon name="refresh-cw" size={14} /> Синхронизировать</>}
          </button>
        </div>
      ) : searchId ? (
        // Список кандидатов выбранного автопоиска — следующий чанк (B)
        <div className="ssa-cands-soon">
          <button className="ssa-crumb" onClick={() => setSearchId(null)}>
            <Icon name="chevron-left" size={13} /> Автопоиски
          </button>
          <div className="ssa-cands-soon-body">
            <Icon name="users" size={26} className="ssa-cands-soon-ic" />
            <div className="ssa-cands-soon-title">Список кандидатов — подключаем</div>
            <div className="ssa-cands-soon-sub">Скоро здесь появятся соискатели выбранного автопоиска.</div>
          </div>
        </div>
      ) : (
        <SSAutoSearchesView
          searches={searches}
          onOpen={(id) => setSearchId(id)}
        />
      )}
    </div>
  );
}

// ====== Шапка ветки ======
function SSAutoHeader({ onBack, poolLeft }: { onBack: () => void; poolLeft: number | null }) {
  return (
    <div>
      <button className="ss-back" onClick={onBack}>
        <Icon name="chevron-left" size={14} /> Выбор источника
      </button>
      <div className="ss-head">
        <div className="ss-head-mark ssa-mark">💃</div>
        <div className="ss-head-text">
          <h1>
            Автоподбор <span className="ss-beta">beta</span>
            <span className="ssa-hh-pill"><Icon name="radio" size={12} /> пока через hh</span>
          </h1>
          <div className="ss-sub">
            Ваши <b>автопоиски на hh.ru</b>: фильтры настроены и подписаны — новые подходящие резюме
            приходят в поток. Глафира забирает их, оценивает AI-матчингом и даёт открыть контакт.
          </div>
        </div>
        <div className="ssa-pool" title="Остаток контактов в пуле hh">
          <div className="ssa-pool-num t-mono">{poolLeft ?? '—'}</div>
          <div className="ssa-pool-cap">контактов<br />в пуле</div>
        </div>
      </div>
    </div>
  );
}

// ====== Вид: список автопоисков ======
function SSAutoSearchesView({ searches, onOpen }: {
  searches: AutoSearch[];
  onOpen: (id: string) => void;
}) {
  const totalNew = searches.reduce((s, x) => s + (x.new_count ?? 0), 0);
  return (
    <div className="ssa-searches">
      <div className="ssa-searches-bar">
        <div className="ssa-sb-left">
          <span className="ssa-sb-title">Автопоиски</span>
          <span className="ssa-sb-count t-mono">{searches.length}</span>
          {totalNew > 0 && <span className="ssa-sb-new">+{totalNew} новых</span>}
        </div>
        <div className="ssa-sb-sync">
          <span className="ssa-sync-dot" /> синхронизировано с hh
        </div>
      </div>

      <div className="ssa-search-list">
        {searches.map((s) => {
          const name = stripQuotes(s.name);
          const bl = basisLabel(s.basis);
          const newCount = s.new_count ?? 0;
          return (
            <div key={s.id} className="ssa-search-card">
              <div className="ssa-sc-main">
                <div className="ssa-sc-head">
                  <span className="ssa-sc-name">«{name}»</span>
                  <button className="ssa-sc-edit" title="Изменить автопоиск на hh">
                    <Icon name="external-link" size={13} />
                  </button>
                  {s.region && (
                    <span className="ssa-sc-region"><Icon name="pin" size={12} /> {s.region}</span>
                  )}
                  <div style={{ flex: 1 }} />
                  {s.updated_at && <span className="ssa-sc-date t-mono">{s.updated_at}</span>}
                </div>

                <div className="ssa-sc-filters">
                  {/* Тумблер подписки — ОТОБРАЖЕНИЕ состояния (запись — в следующем чанке) */}
                  <span
                    className={`ssa-sub ${s.subscribed ? 'on' : 'off'}`}
                    title="Подписка на новые резюме"
                  >
                    <span className="ssa-sub-dot" />
                    {s.subscribed ? 'подписка активна' : 'подписка выключена'}
                  </span>
                </div>

                <div className="ssa-sc-foot">
                  <button className="ssa-sc-link all" onClick={() => onOpen(s.id)}>
                    Показать соискателей <span className="t-mono">{ssaFmt(s.total)}</span>
                  </button>
                  {newCount > 0 ? (
                    <button className="ssa-sc-link new" onClick={() => onOpen(s.id)}>
                      <span className="ssa-new-dot" /> Новые <span className="t-mono">+{newCount}</span>
                    </button>
                  ) : (
                    <span className="ssa-sc-nonew">новых нет</span>
                  )}
                </div>
              </div>

              <div className="ssa-sc-aside">
                <div className="ssa-autoeval">
                  <div className="ssa-ae-text">
                    <div className="ssa-ae-title">Авто-оценка новых</div>
                    <div className="ssa-ae-sub">
                      {s.auto_eval ? 'новые приходят с AI-баллом' : 'оценивать вручную'}
                    </div>
                  </div>
                  {/* Тумблер авто-оценки — ОТОБРАЖЕНИЕ состояния (запись — в следующем чанке) */}
                  <span className={`ss-switch ${s.auto_eval ? 'on' : ''}`} aria-label="Авто-оценка" />
                </div>
                {s.basis && bl && (
                  <div className="ssa-basis" title="Основа оценки">
                    <Icon name={s.basis.kind === 'vacancy' ? 'briefcase' : 'message-circle'} size={12} />
                    <span className="ssa-basis-text">
                      <span className="ssa-basis-k">{s.basis.kind === 'vacancy' ? 'против вакансии' : 'по промту'}</span>
                      <span className="ssa-basis-v">{bl}</span>
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ====== Нет доступа к автопоискам hh ======
function SSAutoNoAccess({ reason }: { reason: string | null }) {
  return (
    <div className="ssa-state ssa-state-noaccess">
      <Icon name="lock" size={26} className="ssa-state-ic" />
      <div className="ssa-state-title">Нет доступа к автопоискам hh</div>
      <div className="ssa-state-sub">
        {reason || 'Подключите hh.ru с платным доступом к базе резюме — тогда автопоиски станут доступны.'}
      </div>
    </div>
  );
}
