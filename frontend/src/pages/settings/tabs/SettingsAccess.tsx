import { Icon } from '@/components/ui/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { PageHead, Card, Select } from '../components/FormComponents';

const ROLE_INFO = [
  {
    id: 'admin', label: 'Администратор', tone: 'admin',
    sum: 'Настраивает систему',
    can: 'Всё: интеграции, пользователи, воронка, теги. Полный доступ ко всем вакансиям и аналитике.',
    sees: 'Все разделы и все данные.',
  },
  {
    id: 'recruiter', label: 'Рекрутер', tone: 'recruiter',
    sum: 'Основной пользователь',
    can: 'Создаёт и ведёт вакансии, работает с кандидатами, передаёт по воронке, общается через Глафиру.',
    sees: 'Свои вакансии, общую базу кандидатов, Аналитику (без отчёта «Рекрутеры»). Не видит Общие настройки, Воронку, Права, Интеграции.',
  },
  {
    id: 'manager', label: 'Нанимающий менеджер', tone: 'manager',
    sum: 'Лёгкий пользователь · заказчик',
    can: 'Согласует требования, оценивает кандидатов, проводит интервью на своей стороне. Не двигает кандидатов между этапами (кроме своей зоны).',
    sees: 'Только вакансии, где он указан заказчиком. Не видит Аналитику и Настройки (кроме Профиля). Не видит общую базу.',
  },
];

const users = [
  { fio: 'Анна Седова', email: 'anna.sedova@company.ru', role: 'admin', src: 'manual', last: '2 ч назад', status: 'active' },
  { fio: 'Иван Петров', email: 'ivan.petrov@company.ru', role: 'recruiter', src: 'manual', last: 'вчера', status: 'active' },
  { fio: 'Мария Кузнецова', email: 'maria.k@company.ru', role: 'recruiter', src: 'manual', last: 'месяц назад', status: 'blocked' },
  { fio: 'Сергей Волков', email: 'sergey.volkov@company.ru', role: 'manager', src: 'b24', last: '5 мин назад', status: 'active' },
];

const roleLabel = { admin: 'Администратор', recruiter: 'Рекрутер', manager: 'Нанимающий менеджер' };
const roleClass = { admin: 'admin', recruiter: 'recruiter', manager: 'manager' };
const statusLabel = { active: 'Активен', blocked: 'Заблокирован', invited: 'Приглашён' };

export function SettingsAccess() {
  return (
    <div className="set-content-inner">
      <PageHead title="Права доступа"
        subtitle="Пользователи системы и их роли"/>

      <div className="info-banner">
        <Icon name="bell" size={16} />
        <div>
          <b>Скоро.</b> Функциональность находится в разработке.
        </div>
      </div>

      <Card title="Роли в системе">
        <div className="roles-grid">
          {ROLE_INFO.map(r => (
            <div key={r.id} className={`role-card role-${r.tone}`}>
              <div className="role-card-head">
                <div className={`role-pill role-${r.tone}`}>{r.label}</div>
                <div className="role-sum">{r.sum}</div>
              </div>
              <div className="role-block">
                <div className="role-cap">Что может</div>
                <div className="role-text">{r.can}</div>
              </div>
              <div className="role-block">
                <div className="role-cap">Что видит</div>
                <div className="role-text">{r.sees}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Пользователи" desc={`Всего ${users.length}: ${users.filter(u => u.status === 'active').length} активных`}>
        <div className="users-toolbar">
          <div className="users-search">
            <Icon name="search" size={14}/>
            <input placeholder="Поиск по ФИО или email…" disabled />
          </div>
          <Select
            options={[
              { value: 'all', label: 'Все роли' },
              { value: 'admin', label: 'Администраторы' },
              { value: 'recruiter', label: 'Рекрутеры' },
              { value: 'manager', label: 'Нанимающие менеджеры' }
            ]}
            disabled
          />
          <Select
            options={[
              { value: 'all', label: 'Все статусы' },
              { value: 'active', label: 'Активные' },
              { value: 'blocked', label: 'Заблокированные' },
              { value: 'invited', label: 'Приглашённые' }
            ]}
            disabled
          />
          <div style={{ flex: 1 }} />
          <button className="btn btn-secondary btn-sm" disabled>
            <Icon name="download" size={14} />Импорт из Б24
          </button>
          <button className="btn btn-primary btn-sm" disabled>
            <Icon name="plus" size={14} />Пригласить
          </button>
        </div>

        <div className="users-table">
          <div className="ut-thead">
            <div>Пользователь</div>
            <div>Роль</div>
            <div>Источник</div>
            <div>Последний вход</div>
            <div>Статус</div>
            <div></div>
          </div>
          {users.map((u, i) => (
            <div key={i} className="ut-row">
              <div className="ut-user">
                <Avatar name={u.fio} size="sm"/>
                <div>
                  <div className="ut-fio">{u.fio}</div>
                  <div className="ut-email">{u.email}</div>
                </div>
              </div>
              <div><span className={`role-pill role-${roleClass[u.role as keyof typeof roleClass]}`}>{roleLabel[u.role as keyof typeof roleLabel]}</span></div>
              <div className="ut-cell">
                {u.src === 'b24'
                  ? <span className="src-pill src-b24"><span className="b24-dot"/>Импорт из Б24</span>
                  : <span className="t-secondary">Создан вручную</span>}
              </div>
              <div className="ut-cell t-mono" style={{ fontSize: 12 }}>{u.last}</div>
              <div>
                <span className={`status-pill status-${u.status}`}>
                  <span className="st-dot"/>{statusLabel[u.status as keyof typeof statusLabel]}
                </span>
              </div>
              <div style={{ textAlign: 'right' }}>
                <button className="row-icon-btn" disabled><Icon name="more" size={16}/></button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}