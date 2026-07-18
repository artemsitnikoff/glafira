import { useLocation, useNavigate } from 'react-router-dom';
import { useUiStore } from '@/store/uiStore';
import { useAuthStore } from '@/store/authStore';
import { api } from '@/api/client';
import { useMe } from '@/api/hooks/useMe';
import { useSidebar } from '@/api/hooks/useSidebar';
import { usePulseAlertsCount } from '@/api/hooks/usePulseAlerts';
import { useRequestsSidebar } from '@/api/hooks/useRequests';
import { Avatar } from './ui/Avatar';
import { Icon, type IconName } from './ui/Icon';
import { APP_VERSION } from '@/lib/version';
import './Sidebar.css';

const ANALYTICS_REPORTS: Array<{ id: string; label: string; icon: IconName }> = [
  { id: 'overview', label: 'Обзор', icon: 'bar-chart' },
  { id: 'speed', label: 'Скорость', icon: 'clock' },
  { id: 'funnel', label: 'Воронка', icon: 'funnel' },
  { id: 'sources', label: 'Источники', icon: 'link' },
  { id: 'rejections', label: 'Отказы', icon: 'x' },
  { id: 'turnover', label: 'Текучка', icon: 'activity' },
  { id: 'recruiters', label: 'Рекрутёры', icon: 'user' },
];

export function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  const { data: me } = useMe();
  const { data: reqCounts } = useRequestsSidebar();
  const reqActive = reqCounts?.active ?? 0;
  const reqNew = reqCounts?.new ?? 0;
  const ui = useUiStore();
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.logout);
  // hiring_manager видит только «Мои заявки» — не дёргаем чужие счётчики (иначе 403 каждые 30с).
  const isHiringManager = user?.role === 'hiring_manager';
  const { data: sidebar } = useSidebar(!isHiringManager);
  const { count: alertsCount } = usePulseAlertsCount(!isHiringManager);

  const handleLogout = async () => {
    // Гасим refresh-cookie на сервере; даже если запрос упал — разлогиниваем локально.
    try {
      await api.post('/auth/logout');
    } catch {
      // игнорируем — локальный logout всё равно выполняем
    }
    clearAuth();
    navigate('/login');
  };

  // Определяем активный раздел по location.pathname
  const getActiveSection = () => {
    const path = location.pathname;
    if (path.startsWith('/home') || path === '/') return 'home';
    if (path.startsWith('/vacancies')) return 'vacancies';
    if (path.startsWith('/candidates')) return 'candidates';
    if (path.startsWith('/smart')) return 'smart';
    if (path.startsWith('/analytics')) return 'analytics';
    if (path.startsWith('/pulse')) return 'pulse';
    if (path.startsWith('/settings')) return 'settings';
    return '';
  };

  const activeSection = getActiveSection();
  const activeReportId = ui.analyticsReportId;

  // Фильтруем вакансии по поисковому запросу
  const filteredVacancies = (sidebar?.items ?? []).filter((v: any) =>
    !ui.vacancySearch || v.name.toLowerCase().includes(ui.vacancySearch.toLowerCase())
  );

  const handleBrandClick = () => {
    navigate('/home');
  };

  const handleNewVacancy = () => {
    navigate('/vacancies/new');
  };

  // Фильтруем навигацию по ролям
  const getVisibleNavItems = () => {
    const baseNav = [
      { id: 'home', label: 'Главная', icon: 'home' as IconName },
      { id: 'vacancies', label: 'Вакансии', icon: 'briefcase' as IconName, expandable: 'vacancies', pip: reqNew },
      { id: 'candidates', label: 'Кандидаты', icon: 'users' as IconName },
      { id: 'smart', label: 'Умный подбор', icon: 'sparkles' as IconName, beta: true },
      { id: 'analytics', label: 'Аналитика', icon: 'chart' as IconName, expandable: 'analytics' },
      { id: 'pulse', label: 'Пульс-Онбординг', icon: 'heart' as IconName, beta: true, pip: alertsCount },
      { id: 'settings', label: 'Настройки', icon: 'settings' as IconName },
    ];

    // Нанимающий менеджер видит ТОЛЬКО «Мои заявки».
    if (user?.role === 'hiring_manager') {
      return [{ id: 'requests', label: 'Мои заявки', icon: 'inbox' as IconName }];
    }

    // manager (ассистент) видит только Главная, Вакансии, Пульс
    if (user?.role === 'manager') {
      return baseNav.filter((item) => ['home', 'vacancies', 'pulse'].includes(item.id));
    }

    // admin и recruiter видят всё
    return baseNav;
  };

  const handleVacancySelect = (vacancyId: number) => {
    navigate(`/vacancies/${vacancyId}`);
  };

  const handleArchiveClick = () => {
    navigate('/vacancies/archive');
  };

  const handleAnalyticsReport = (reportId: string) => {
    ui.setAnalyticsReportId(reportId);
    navigate(`/analytics?report=${reportId}`);
  };

  const nav = getVisibleNavItems();

  const renderVacanciesSub = () => (
    <div className="sub-block">
      {/* «Заявки» — закреплённая строка СВЕРХУ подсписка (эталон: первый элемент sub-block). */}
      <div
        className={`sub-archive sub-requests ${location.pathname.startsWith('/requests') ? 'selected' : ''}`}
        onClick={() => navigate('/requests')}
      >
        <Icon name="inbox" size={15} />
        <span>Заявки</span>
        {reqNew > 0 && <span className="sub-new">+{reqNew}</span>}
        <span className="sub-count">{reqActive}</span>
      </div>
      {/* Кнопку создания вакансии видят только admin и recruiter */}
      {user?.role !== 'manager' && (
        <button className="sub-add" onClick={handleNewVacancy}>
          <Icon name="plus" size={14} /> Новая вакансия
        </button>
      )}
      <div className="sub-search">
        <Icon name="search" size={13} style={{ color: 'var(--fg-3)', flex: 'none' }} />
        <input
          placeholder="Поиск…"
          value={ui.vacancySearch}
          onChange={(e) => ui.setVacancySearch(e.target.value)}
        />
      </div>
      <div className="sub-list">
        {filteredVacancies.length === 0 ? (
          <div className="sub-empty">Ничего не найдено</div>
        ) : (
          filteredVacancies.map((v: any) => (
            <div
              key={v.id}
              className={`sub-row ${
                location.pathname === `/vacancies/${v.id}` && !location.pathname.includes('/archive')
                  ? 'selected'
                  : ''
              }`}
              onClick={() => handleVacancySelect(v.id)}
            >
              <span className="sub-name">{v.name}</span>
              <span className="sub-count">{v.count}</span>
              {v.new_count > 0 && <span className="sub-new">+{v.new_count}</span>}
            </div>
          ))
        )}
        <div className="sub-divider" />
        <div
          className={`sub-archive ${location.pathname === '/vacancies/all' ? 'selected' : ''}`}
          onClick={() => navigate('/vacancies/all')}
        >
          <Icon name="layout-grid" size={15} />
          <span>Все вакансии</span>
          <span className="sub-count">{sidebar?.items?.length ?? 0}</span>
        </div>
        <div
          className={`sub-archive ${location.pathname.includes('/archive') ? 'selected' : ''}`}
          onClick={handleArchiveClick}
        >
          <Icon name="archive" size={15} />
          <span>Архив</span>
          <span className="sub-count">{sidebar?.archived_count ?? 0}</span>
        </div>
      </div>
    </div>
  );

  const renderAnalyticsSub = () => (
    <div className="sub-block">
      <div className="sub-list">
        {ANALYTICS_REPORTS.map((r) => (
          <div
            key={r.id}
            className={`sub-row sub-row-an ${activeReportId === r.id ? 'selected' : ''}`}
            onClick={() => handleAnalyticsReport(r.id)}
          >
            <Icon name={r.icon} size={14} style={{ flex: 'none', color: 'var(--fg-2)' }} />
            <span className="sub-name">{r.label}</span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <aside className="sidebar-wide">
      <div className="brand-wide" onClick={handleBrandClick}>
        <div className="brand-mark">
          <span className="brand-emoji">👩🏻</span>
        </div>
        <span className="brand-name">
          Глафира
          <span className="brand-version">v{APP_VERSION}</span>
        </span>
        <span className="brand-dancer">💃</span>
      </div>
      <div className="nav-wide">
        {nav.map((n) => {
          const isActive = activeSection === n.id;
          const isExpanded =
            (n.expandable === 'vacancies' && ui.vacanciesOpen) ||
            (n.expandable === 'analytics' && ui.analyticsOpen);
          return (
            <div key={n.id}>
              <button
                className={`nav-row ${isActive ? 'active' : ''}`}
                onClick={() => {
                  if (n.expandable === 'vacancies') ui.toggleVacancies();
                  else if (n.expandable === 'analytics') ui.toggleAnalytics();
                  else navigate(`/${n.id === 'home' ? '' : n.id}`);
                }}
              >
                <Icon name={n.icon} size={18} className="nav-row-icon" />
                <span className="nav-row-label">
                  {n.label}
                  {(n as any).beta && <span className="nav-beta">beta</span>}
                </span>
                {n.pip && n.pip > 0 ? <span className="nav-row-pip">{n.pip}</span> : null}
                {n.expandable && (
                  <span className={`nav-chev ${isExpanded ? 'open' : ''}`}>
                    <Icon name="chevD" size={14} />
                  </span>
                )}
              </button>
              {n.expandable === 'vacancies' && isExpanded && renderVacanciesSub()}
              {n.expandable === 'analytics' && isExpanded && renderAnalyticsSub()}
            </div>
          );
        })}
      </div>

      <div className="user-card-wide">
        {me && (
          <>
            <Avatar name={me.full_name} size="sm" />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="uc-name">{me.full_name}</div>
              <div className="uc-role">{me.role}</div>
            </div>
            <button className="icon-btn" aria-label="Уведомления">
              <Icon name="bell" size={16} />
              {alertsCount > 0 && <span className="pip" />}
            </button>
            <button className="icon-btn" aria-label="Выйти" title="Выйти" onClick={handleLogout}>
              <Icon name="log-out" size={16} />
            </button>
          </>
        )}
      </div>
    </aside>
  );
}