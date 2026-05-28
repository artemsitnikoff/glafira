import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useAuthStore, selectIsAuthenticated } from '@/store/authStore';
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
  const location = useLocation();
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