import { useEffect, useState, lazy } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuthStore, selectIsAuthenticated } from '@/store/authStore';
import { api } from '@/api/client';
import type { UserMe } from '@/api/aliases';
import AppLayout from '@/components/AppLayout';
import LoginPage from '@/pages/LoginPage';
import NotFoundPage from '@/pages/NotFoundPage';

// Lazy-загружаемые страницы
const HomePage = lazy(() => import('@/pages/HomePage'));
const VacanciesPage = lazy(() => import('@/pages/VacanciesPage'));
const VacanciesArchivePage = lazy(() => import('@/pages/VacanciesArchivePage'));
const VacancyFormPage = lazy(() => import('@/pages/VacancyFormPage'));
const VacancyDetailPage = lazy(() => import('@/pages/VacancyDetailPage'));
const CandidatesPoolPage = lazy(() => import('@/pages/candidates/CandidatesPoolPage').then(m => ({ default: m.CandidatesPoolPage })));
const CandidatePoolDetailPage = lazy(() => import('@/pages/candidates/CandidatePoolDetailPage').then(m => ({ default: m.CandidatePoolDetailPage })));
const PulseComingSoon = lazy(() => import('@/pages/pulse/PulseComingSoon').then(m => ({ default: m.PulseComingSoon })));
const AnalyticsPage = lazy(() => import('@/pages/AnalyticsPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));

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
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
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
        <Route path="vacancies/new" element={<VacancyFormPage />} />
        <Route path="vacancies/:id/edit" element={<VacancyFormPage />} />
        <Route path="vacancies/:id" element={<VacancyDetailPage />} />
        <Route path="vacancies/:id/candidates/:cid" element={<VacancyDetailPage />} />
        <Route path="candidates" element={<CandidatesPoolPage />} />
        <Route path="candidates/:id" element={<CandidatePoolDetailPage />} />
        <Route path="pulse" element={<PulseComingSoon />} />
        <Route path="pulse/:employeeId" element={<PulseComingSoon />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}