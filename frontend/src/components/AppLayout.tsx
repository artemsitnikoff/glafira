import { Outlet } from 'react-router-dom';

export default function AppLayout() {
  return (
    <div className="app-layout">
      <aside className="app-sidebar">
        {/* TODO(TZ-3 §7): Sidebar — следующий шаг */}
        Sidebar placeholder
      </aside>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}