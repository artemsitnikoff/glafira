import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { IntegrationCard } from './SettingsIntegrations';
import { useMyHhStatus } from '@/api/hooks/useHhIntegration';
import { useMyHhAuthorize, useDisconnectMyHh } from '@/api/mutations/hhIntegration';
import { useAuthStore } from '@/store/authStore';
import type { ApiError } from '@/api/aliases';

/**
 * «Мой hh» — ПЕРСОНАЛЬНОЕ подключение рекрутёром своего аккаунта hh.ru.
 * Рендерится СЕКЦИЕЙ внутри вкладки «Профиль» (SettingsProfile), сразу после
 * блока смены пароля. Профиль (adminOnly:false) виден admin+recruiter —
 * достижимость сохранена, а личное подключение логично рядом с паролем.
 *
 * Компонент — встраиваемый: без собственного `set-content-inner`/PageHead, чтобы
 * лечь секцией в окружение Профиля. Роль-гейт (admin/recruiter) внутри дублирует
 * бек (require_recruiter_or_admin); manager/hiring_manager в Настройки не
 * попадают (ранний возврат + RoleGuard в SettingsPage). Контент НЕ гейтится
 * readOnly: рекрутёр — read-only для настроек компании, но своим личным hh
 * управлять вправе (это его аккаунт, не компанийная настройка).
 */
export function SettingsMyHh() {
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const currentUserRole = useAuthStore((s) => s.user?.role);
  const isMyHhAllowed = currentUserRole === 'admin' || currentUserRole === 'recruiter';
  const { data: myHhStatus, isLoading: myHhStatusLoading } = useMyHhStatus(isMyHhAllowed);
  const myHhAuthorizeMutation = useMyHhAuthorize();
  const myHhDisconnectMutation = useDisconnectMyHh();

  const handleMyHhConnect = async () => {
    try {
      const response = await myHhAuthorizeMutation.mutateAsync();
      window.location.href = response.authorize_url;
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при подключении вашего hh-аккаунта',
      });
    }
  };

  const handleMyHhDisconnect = async () => {
    try {
      await myHhDisconnectMutation.mutateAsync();
      setNotification({
        type: 'success',
        message: 'Ваш личный hh-аккаунт отключён — интерактивные операции пойдут через общий аккаунт компании.',
      });
    } catch (error) {
      const e = error as unknown as ApiError;
      setNotification({
        type: 'error',
        message: e.error?.message || 'Ошибка при отключении вашего hh-аккаунта',
      });
    }
  };

  // manager/hiring_manager до Профиля не доходят, но на всякий случай — ничего.
  if (!isMyHhAllowed) return null;

  return (
    <>
      {notification && (
        <div className={notification.type === 'success' ? 'info-banner' : 'error-banner'}
             style={{
               marginBottom: 16,
               background: notification.type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
               borderColor: notification.type === 'success' ? 'var(--success-border)' : 'var(--error-border)',
               color: notification.type === 'success' ? 'var(--success-fg)' : 'var(--error-fg)'
             }}>
          <Icon name={notification.type === 'success' ? 'check' : 'x'} size={16} />
          <div>{notification.message}</div>
        </div>
      )}

      <div className="integ-list">
        <IntegrationCard
          ico={<Icon name="user" size={18}/>}
          iconBg="var(--ark-yellow-100)"
          name="Мой hh"
          desc="Персональное подключение вашего аккаунта hh.ru"
          status={myHhStatusLoading ? 'bad' : (myHhStatus?.connected ? 'ok' : 'bad')}
          statusLabel={myHhStatus?.connected ? undefined : 'Не подключено'}>
          <div className="integ-section">
            <div className="integ-section-title">Личное подключение</div>

            {myHhStatusLoading ? (
              <div style={{ padding: '16px 0', color: 'var(--fg-3)' }}>Загрузка статуса...</div>
            ) : myHhStatus?.connected ? (
              // Подключён личный hh-аккаунт
              <div>
                <div style={{ marginBottom: '12px' }}>
                  <div style={{ fontSize: '13px', color: 'var(--fg-2)' }}>
                    <strong>Подключён</strong> ваш личный hh-аккаунт
                    {myHhStatus.hh_employer_id ? ` · работодатель ID: ${myHhStatus.hh_employer_id}` : ''}
                    {myHhStatus.hh_manager_id ? ` · менеджер ID: ${myHhStatus.hh_manager_id}` : ''}
                  </div>
                  {myHhStatus.connected_at && (
                    <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '4px' }}>
                      Подключён: {new Date(myHhStatus.connected_at).toLocaleString('ru')}
                    </div>
                  )}
                  {myHhStatus.expires_at && (
                    <div style={{ fontSize: '12px', color: 'var(--fg-3)', marginTop: '2px' }}>
                      Токен действует до: {new Date(myHhStatus.expires_at).toLocaleString('ru')}
                    </div>
                  )}
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleMyHhDisconnect}
                    disabled={myHhDisconnectMutation.isPending}
                  >
                    {myHhDisconnectMutation.isPending ? 'Отключение...' : 'Отключить'}
                  </button>
                </div>
                <div className="info-banner small" style={{ marginTop: 10 }}>
                  <Icon name="alert-triangle" size={14} />
                  <div>
                    Чат, поиск и просмотры резюме идут под вашим hh-аккаунтом (ваш лимит 500 просмотров/сутки,
                    ваши действия — на вас). Отключите — интерактивные операции вернутся на общий аккаунт компании.
                  </div>
                </div>
              </div>
            ) : (
              // Не подключён — предложение подключить свой hh
              <div>
                <div style={{ marginBottom: '12px', fontSize: '13px', color: 'var(--fg-2)' }}>
                  Чат, поиск и просмотры резюме будут идти под вашим hh-аккаунтом (ваш лимит 500 просмотров/сутки,
                  ваши действия — на вас). Без него используется общий аккаунт компании.
                </div>
                <div className="integ-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleMyHhConnect}
                    disabled={myHhAuthorizeMutation.isPending}
                  >
                    {myHhAuthorizeMutation.isPending ? 'Подключение...' : 'Подключить мой hh'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </IntegrationCard>
      </div>
    </>
  );
}
