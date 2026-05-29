import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export default function AppLayout() {
  return (
    <div className="app-layout">
      <Sidebar />
      <div className="main">
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}