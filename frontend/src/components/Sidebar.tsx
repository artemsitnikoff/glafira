import { NavLink, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useUiStore } from '@/store/uiStore';
import { useMe } from '@/api/hooks/useMe';
import { useSidebar } from '@/api/hooks/useSidebar';
import { usePulseAlertsCount } from '@/api/hooks/usePulseAlerts';
import { useCandidates } from '@/api/hooks/useCandidates';
import { Avatar } from './ui/Avatar';
import { Icon } from './ui/Icon';
import { APP_VERSION } from '@/lib/version';
import './Sidebar.css';

const ANALYTICS_REPORTS = [
  { id: 'overview', label: 'Обзор', emoji: '📋' },
  { id: 'speed', label: 'Скорость', emoji: '⏱' },
  { id: 'funnel', label: 'Воронка', emoji: '🔻' },
  { id: 'sources', label: 'Источники', emoji: '🌐' },
  { id: 'rejections', label: 'Отказы', emoji: '❌' },
  { id: 'turnover', label: 'Текучка', emoji: '📉' },
  { id: 'recruiters', label: 'Рекрутёры', emoji: '👤' },
];

export function Sidebar() {
  const location = useLocation();
  const { id: activeVacancyId } = useParams();
  const navigate = useNavigate();

  const { data: me } = useMe();
  const { data: sidebar } = useSidebar();
  const { count: alertsCount } = usePulseAlertsCount();
  const { data: candidatesData } = useCandidates({});
  const ui = useUiStore();

  // Фильтруем вакансии по поисковому запросу
  const items = (sidebar?.items ?? []).filter((v: any) =>
    !ui.vacancySearch || v.name.toLowerCase().includes(ui.vacancySearch.toLowerCase())
  );

  const handleBrandClick = () => {
    navigate('/home');
  };

  const handleNewVacancy = () => {
    navigate('/vacancies/new');
  };

  const handleAnalyticsReport = (reportId: string) => {
    ui.setAnalyticsReportId(reportId);
    navigate(`/analytics?report=${reportId}`);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar__brand" onClick={handleBrandClick}>
        <span>👩🏻</span>
        <span className="sidebar__brand-name">
          Глафира
          <span className="sidebar__brand-version">v{APP_VERSION}</span>
        </span>
        <span>💃</span>
      </div>

      <nav className="sidebar__nav">
        <NavLink
          to="/home"
          className={({ isActive }) => `sidebar__item ${isActive ? 'is-active' : ''}`}
        >
          <Icon name="home" size={18} />
          <span>Главная</span>
        </NavLink>

        <button
          className={`sidebar__item ${location.pathname.startsWith('/vacancies') ? 'is-active' : ''}`}
          onClick={ui.toggleVacancies}
        >
          <Icon name="briefcase" size={18} />
          <span>Вакансии</span>
          <Icon
            name={ui.vacanciesOpen ? 'chevron-down' : 'chevron-right'}
            size={16}
            className={`sidebar__chevron ${ui.vacanciesOpen ? 'open' : ''}`}
          />
        </button>

        {ui.vacanciesOpen && (
          <div className="sidebar__sub">
            <button className="sidebar__new" onClick={handleNewVacancy}>
              <Icon name="plus" size={14} />
              Новая вакансия
            </button>

            <div className="sidebar__search">
              <Icon name="search" size={14} style={{ color: 'var(--fg-3)', flex: 'none' }} />
              <input
                type="text"
                placeholder="Поиск…"
                value={ui.vacancySearch}
                onChange={(e) => ui.setVacancySearch(e.target.value)}
              />
            </div>

            <div className="sidebar__list">
              {items.length === 0 ? (
                <div className="sidebar__empty">
                  {ui.vacancySearch ? 'Ничего не найдено' : 'Нет вакансий'}
                </div>
              ) : (
                items.map((v: any) => (
                  <NavLink
                    key={v.id}
                    to={`/vacancies/${v.id}`}
                    className={({ isActive }) =>
                      `sidebar__vac ${isActive || activeVacancyId === String(v.id) ? 'is-active' : ''}`
                    }
                  >
                    <span className="sidebar__vac-name">{v.name}</span>
                    <span className="mono">{v.count}</span>
                    {v.new_count > 0 && (
                      <span className="sidebar__new-badge">+{v.new_count}</span>
                    )}
                  </NavLink>
                ))
              )}

              <NavLink
                to="/vacancies/archive"
                className={({ isActive }) => `sidebar__archive ${isActive ? 'is-active' : ''}`}
              >
                <Icon name="archive" size={14} />
                <span>Архив</span>
                <span className="mono">—</span>
              </NavLink>
            </div>
          </div>
        )}

        <NavLink
          to="/candidates"
          className={({ isActive }) => `sidebar__item ${isActive ? 'is-active' : ''}`}
        >
          <Icon name="users" size={18} />
          <span>Кандидаты</span>
          {candidatesData?.pages?.[0]?.total && (
            <span className="mono">{candidatesData.pages[0].total}</span>
          )}
        </NavLink>

        <NavLink
          to="/pulse"
          className={({ isActive }) => `sidebar__item ${isActive ? 'is-active' : ''}`}
        >
          <Icon name="activity" size={18} />
          <span>Пульс</span>
          {alertsCount > 0 && <span className="sidebar__badge">{alertsCount}</span>}
        </NavLink>

        <button
          className={`sidebar__item ${location.pathname.startsWith('/analytics') ? 'is-active' : ''}`}
          onClick={ui.toggleAnalytics}
        >
          <Icon name="bar-chart" size={18} />
          <span>Аналитика</span>
          <Icon
            name={ui.analyticsOpen ? 'chevron-down' : 'chevron-right'}
            size={16}
            className={`sidebar__chevron ${ui.analyticsOpen ? 'open' : ''}`}
          />
        </button>

        {ui.analyticsOpen && (
          <div className="sidebar__sub">
            <div className="sidebar__list">
              {ANALYTICS_REPORTS.map((r) => (
                <button
                  key={r.id}
                  className={`sidebar__report ${ui.analyticsReportId === r.id ? 'is-active' : ''}`}
                  onClick={() => handleAnalyticsReport(r.id)}
                >
                  <span>{r.emoji}</span>
                  <span>{r.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <NavLink
          to="/settings"
          className={({ isActive }) => `sidebar__item ${isActive ? 'is-active' : ''}`}
        >
          <Icon name="settings" size={18} />
          <span>Настройки</span>
        </NavLink>
      </nav>

      <div className="sidebar__user">
        {me && (
          <>
            <Avatar name={me.full_name} size="md" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="sidebar__user-name">{me.full_name}</div>
              <div className="sidebar__user-role">{me.role}</div>
            </div>
            <button className="sidebar__bell" aria-label="Уведомления">
              <Icon name="bell" size={16} />
              {alertsCount > 0 && <span className="sidebar__pip" />}
            </button>
          </>
        )}
      </div>
    </aside>
  );
}