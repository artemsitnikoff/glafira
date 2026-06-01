import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';

interface RoleGuardProps {
  children: ReactNode;
  roles: Array<'admin' | 'recruiter' | 'manager'>;
  fallbackPath?: string;
}

/**
 * Защита роутов по ролям. Если у пользователя нет нужной роли — редирект на fallbackPath.
 * Используется для блокировки доступа менеджера к /candidates, /analytics, /settings.
 */
export function RoleGuard({ children, roles, fallbackPath = '/home' }: RoleGuardProps) {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  // Если роль пользователя не в списке разрешённых — редирект
  if (!user?.role || !roles.includes(user.role as 'admin' | 'recruiter' | 'manager')) {
    return <Navigate to={fallbackPath} state={{ from: location }} replace />;
  }

  return <>{children}</>;
}