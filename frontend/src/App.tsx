import { useEffect, useState } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuthStore, selectIsAuthenticated } from '@/store/authStore';
import { api } from '@/api/client';
import type { UserMe } from '@/api/aliases';
import AppLayout from '@/components/AppLayout';
import LoginPage from '@/pages/LoginPage';
import HomePage from '@/pages/HomePage';
import VacanciesPage from '@/pages/VacanciesPage';
import VacanciesArchivePage from '@/pages/VacanciesArchivePage';
import VacancyFormPage from '@/pages/VacancyFormPage';
import VacancyDetailPage from '@/pages/VacancyDetailPage';
import { CandidatesPoolPage } from '@/pages/candidates/CandidatesPoolPage';
import { CandidatePoolDetailPage } from '@/pages/candidates/CandidatePoolDetailPage';
import { PulsePage } from '@/pages/pulse/PulsePage';
import { PulseEmployeePage } from '@/pages/pulse/PulseEmployeePage';
import AnalyticsPage from '@/pages/AnalyticsPage';
import SettingsPage from '@/pages/SettingsPage';
import NotFoundPage from '@/pages/NotFoundPage';

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
        <Route path="pulse" element={<PulsePage />} />
        <Route path="pulse/:employeeId" element={<PulseEmployeePage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}