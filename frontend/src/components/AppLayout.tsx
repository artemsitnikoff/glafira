import { Outlet, Navigate, useLocation } from 'react-router-dom';
import { Suspense } from 'react';
import { Sidebar } from './Sidebar';
import { ChatPopup } from './chat/ChatPopup';
import { useAuthStore } from '@/store/authStore';

export default function AppLayout() {
  const role = useAuthStore((s) => s.user?.role);
  const location = useLocation();

  // Нанимающий менеджер (hiring_manager) видит ТОЛЬКО «Мои заявки». Бэкенд отбивает
  // все прочие data-роуты 403 — фронт не рендерит их страницы, а уводит на /requests.
  if (role === 'hiring_manager' && !location.pathname.startsWith('/requests')) {
    return <Navigate to="/requests" replace />;
  }

  // Попап «Чаты» монтируется один раз рядом с Layout. Только для персонала
  // (admin/recruiter) — у manager/hiring_manager нет кнопки и попап не нужен
  // (закрытый попап не поллит: useDialogs enabled=open).
  const showChat = role === 'admin' || role === 'recruiter';

  return (
    <div className="app-layout">
      {showChat && <ChatPopup />}
      <Sidebar />
      <div className="main">
        <main className="content">
          <Suspense fallback={
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              minHeight: '200px',
              color: 'var(--fg-2)'
            }}>
              Загрузка...
            </div>
          }>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}