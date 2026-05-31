import { Outlet } from 'react-router-dom';
import { Suspense } from 'react';
import { Sidebar } from './Sidebar';

export default function AppLayout() {
  return (
    <div className="app-layout">
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