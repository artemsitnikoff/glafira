import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { PageHead, Card, FormRow, TextInput, Select, Switch } from '../components/FormComponents';

interface SettingsProfileProps {
  readOnly?: boolean;
}

export function SettingsProfile({ readOnly: _ = false }: SettingsProfileProps) {
  // All controls are disabled for "скоро" (не зависит от readOnly - всё заблокировано в любом случае)
  const form = {
    fio: 'Анна Седова',
    role: 'Старший рекрутер',
    email: 'anna.sedova@company.ru',
    phone: '+7 (916) 482-30-15',
    city: 'Москва (UTC+3)',
    lang: 'ru',
  };

  return (
    <div className="set-content-inner">
      <PageHead title="Мой профиль"
        subtitle="Личные данные, безопасность и уведомления" />

      <div className="info-banner">
        <Icon name="bell" size={16} />
        <div>
          <b>Скоро.</b> Функциональность находится в разработке.
        </div>
      </div>

      <Card title="Аватар и основные данные">
        <div className="profile-avatar-row">
          <div className="big-avatar">
            <Avatar name={form.fio} size="lg"/>
          </div>
          <div className="avatar-actions">
            <button className="btn btn-secondary btn-sm" disabled>Загрузить фото</button>
            <button className="btn btn-ghost btn-sm" disabled>Удалить</button>
            <div className="t-caption" style={{marginTop: 6}}>JPG / PNG, до 4МБ. Квадратное, мин. 200×200.</div>
          </div>
        </div>
        <div className="form-grid form-grid-2">
          <FormRow label="ФИО" required>
            <TextInput value={form.fio} locked />
          </FormRow>
          <FormRow label="Должность">
            <TextInput value={form.role} locked />
          </FormRow>
          <FormRow label="Email" required hint="На этот адрес приходят уведомления и приглашения">
            <TextInput value={form.email} locked />
          </FormRow>
          <FormRow label="Телефон">
            <TextInput value={form.phone} locked />
          </FormRow>
          <FormRow label="Город / часовой пояс">
            <Select value={form.city}
              options={['Москва (UTC+3)','Санкт-Петербург (UTC+3)','Екатеринбург (UTC+5)','Новосибирск (UTC+7)','Владивосток (UTC+10)']}
              disabled />
          </FormRow>
          <FormRow label="Язык интерфейса">
            <Select value={form.lang}
              options={[{value:'ru', label:'Русский'},{value:'en', label:'English'}]}
              disabled />
          </FormRow>
        </div>
      </Card>

      <Card title="Безопасность">
        <div className="action-row">
          <div>
            <div className="ar-title">Пароль</div>
            <div className="ar-desc">Последняя смена: 14 февраля 2026 г.</div>
          </div>
          <button className="btn btn-secondary" disabled>Сменить пароль</button>
        </div>
      </Card>

      <Card title="Уведомления" desc="Каналы доставки и события, по которым вам приходят оповещения">
        <div className="notif-table">
          <div className="notif-thead">
            <div>Событие</div>
            <div>Email</div>
            <div>Telegram</div>
            <div>Push</div>
          </div>
          {[
            ['Новый отклик на мою вакансию', true, true, false],
            ['Глафира квалифицировала кандидата', true, true, true],
            ['Кандидат перешёл на этап «Оффер»', true, false, true],
            ['Заказчик оставил оценку', true, true, false],
            ['Ежедневный дайджест по почте', true, false, false],
            ['Еженедельный отчёт', true, false, false],
          ].map((r, i) => (
            <div key={i} className="notif-row">
              <div className="notif-evt">{r[0]}</div>
              <div><Switch value={r[1] as boolean} disabled /></div>
              <div><Switch value={r[2] as boolean} disabled /></div>
              <div><Switch value={r[3] as boolean} disabled /></div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}