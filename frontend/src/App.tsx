import { useEffect, useState, lazy, Suspense } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuthStore, selectIsAuthenticated } from '@/store/authStore';
import { api } from '@/api/client';
import type { UserMe } from '@/api/aliases';
import AppLayout from '@/components/AppLayout';
import LoginPage from '@/pages/LoginPage';
import NotFoundPage from '@/pages/NotFoundPage';
import { RoleGuard } from '@/components/RoleGuard';
import SubscriptionExpiredScreen from '@/components/SubscriptionExpiredScreen';

// Lazy-загружаемые страницы
const HomePage = lazy(() => import('@/pages/HomePage'));
const VacanciesPage = lazy(() => import('@/pages/VacanciesPage'));
const VacanciesArchivePage = lazy(() => import('@/pages/VacanciesArchivePage'));
const VacancyFormPage = lazy(() => import('@/pages/VacancyFormPage'));
const VacancyDetailPage = lazy(() => import('@/pages/VacancyDetailPage'));
const CandidatesPoolPage = lazy(() => import('@/pages/candidates/CandidatesPoolPage').then(m => ({ default: m.CandidatesPoolPage })));
const CandidatePoolDetailPage = lazy(() => import('@/pages/candidates/CandidatePoolDetailPage').then(m => ({ default: m.CandidatePoolDetailPage })));
const SmartSearchPage = lazy(() => import('@/pages/smart/SmartSearchPage'));
const PulsePage = lazy(() => import('@/pages/pulse/PulsePage').then(m => ({ default: m.PulsePage })));
const PulseEmployeePage = lazy(() => import('@/pages/pulse/PulseEmployeePage').then(m => ({ default: m.PulseEmployeePage })));
const AnalyticsPage = lazy(() => import('@/pages/analytics/AnalyticsPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));
// Публичная страница опроса — БЕЗ авторизации, вне AppLayout. /pulse/survey/#<token>
const SurveyPublicPage = lazy(() => import('@/pages/public/SurveyPublicPage'));

function RequireAuth({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const setAuth = useAuthStore((s) => s.setAuth);
  const location = useLocation();
  // bootstrap: при первом маунте после reload — token/user в памяти потеряны,
  // но refresh-cookie HttpOnly жива. Пробуем восстановить сессию через refresh.
  const [bootstrapping, setBootstrapping] = useState(!isAuthenticated);

  useEffect(() => {
    if (isAuthenticated) {
      setBootstrapping(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const refresh = await api.post<{ access_token: string }>('/auth/refresh');
        const token = refresh.data.access_token;
        const me = await api.get<UserMe>('/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!cancelled) setAuth(token, me.data);
      } catch {
        // refresh не сработал — пользователь не авторизован, редирект на /login
      } finally {
        if (!cancelled) setBootstrapping(false);
      }
    })();
    return () => { cancelled = true; };
  }, [isAuthenticated, setAuth]);

  if (bootstrapping) return null;
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  const subscriptionExpired = useAuthStore((s) => s.subscriptionExpired);

  if (subscriptionExpired) {
    return <SubscriptionExpiredScreen />;
  }

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {/* Публичный опрос — статический путь, выигрывает у защищённого /pulse/:employeeId */}
      <Route
        path="/pulse/survey"
        element={
          <Suspense fallback={null}>
            <SurveyPublicPage />
          </Suspense>
        }
      />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/home" replace />} />
        <Route path="home" element={<HomePage />} />
        <Route path="vacancies" element={<VacanciesPage />} />
        <Route path="vacancies/archive" element={<VacanciesArchivePage />} />
        <Route
          path="vacancies/new"
          element={
            <RoleGuard roles={['admin', 'recruiter']}>
              <VacancyFormPage />
            </RoleGuard>
          }
        />
        <Route path="vacancies/:id/edit" element={<VacancyFormPage />} />
        <Route path="vacancies/:id" element={<VacancyDetailPage />} />
        <Route path="vacancies/:id/candidates/:cid" element={<VacancyDetailPage />} />
        <Route
          path="candidates"
          element={
            <RoleGuard roles={['admin', 'recruiter']}>
              <CandidatesPoolPage />
            </RoleGuard>
          }
        />
        <Route
          path="candidates/:id"
          element={
            <RoleGuard roles={['admin', 'recruiter']}>
              <CandidatePoolDetailPage />
            </RoleGuard>
          }
        />
        <Route
          path="smart"
          element={
            <RoleGuard roles={['admin', 'recruiter']}>
              <SmartSearchPage />
            </RoleGuard>
          }
        />
        <Route path="pulse" element={<PulsePage />} />
        <Route path="pulse/:employeeId" element={<PulseEmployeePage />} />
        <Route
          path="analytics"
          element={
            <RoleGuard roles={['admin', 'recruiter']}>
              <AnalyticsPage />
            </RoleGuard>
          }
        />
        <Route
          path="settings"
          element={
            <RoleGuard
              roles={['admin', 'recruiter']}
              fallbackPath="/home"
            >
              <SettingsPage />
            </RoleGuard>
          }
        />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}