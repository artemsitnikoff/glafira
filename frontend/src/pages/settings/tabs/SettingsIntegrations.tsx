import { Icon } from '@/components/ui/Icon';
import { PageHead, FormRow, TextInput, Textarea, Select, Switch } from '../components/FormComponents';

function IntegrationCard({
  ico,
  iconBg,
  name,
  desc,
  status,
  children
}: {
  ico: React.ReactNode;
  iconBg: string;
  name: string;
  desc: string;
  status: 'ok' | 'bad' | 'err';
  children: React.ReactNode;
}) {
  const statusInfo = {
    ok: { label: 'Подключено', cls: 'ok' },
    bad: { label: 'Не настроено', cls: 'bad' },
    err: { label: 'Ошибка авторизации', cls: 'err' },
  }[status];

  return (
    <section className="integ-card">
      <div className="integ-head">
        <div className="integ-ico" style={{ background: iconBg }}>{ico}</div>
        <div className="integ-body">
          <div className="integ-name">{name}</div>
          <div className="integ-desc">{desc}</div>
        </div>
        <div className={`conn-pill ${statusInfo.cls}`}>
          {status === 'ok' && <Icon name="check" size={12}/>}
          {status === 'err' && <Icon name="x" size={12}/>}
          {statusInfo.label}
        </div>
        <span className="integ-chev"><Icon name="chevD" size={16}/></span>
      </div>
      <div className="integ-content">{children}</div>
    </section>
  );
}

export function SettingsIntegrations() {
  return (
    <div className="set-content-inner">
      <PageHead title="Интеграции"
        subtitle="Внешние сервисы, с которыми работает Глафира"/>

      <div className="info-banner">
        <Icon name="bell" size={16} />
        <div>
          <b>Скоро.</b> Функциональность находится в разработке.
        </div>
      </div>

      <div className="integ-list">
        {/* TELEGRAM */}
        <IntegrationCard
          ico={<span className="integ-emoji">🤖</span>}
          iconBg="#EAF3FE"
          name="Telegram"
          desc="Бот «Глафира» для общения с кандидатами и уведомления пользователей"
          status="ok">
          <div className="integ-section">
            <div className="integ-section-title">Бот «Глафира» — общение с кандидатами</div>
            <div className="form-grid form-grid-2">
              <FormRow label="Bot Token" required>
                <TextInput value="••••••••••••5817:AAFq-pK9b3xN-vN" mono locked />
              </FormRow>
              <FormRow label="Bot Username" hint="Определяется автоматически после ввода токена">
                <TextInput value="@glafira_recruit_bot" mono locked />
              </FormRow>
              <FormRow label="Webhook URL" span={2} hint="Скопируйте URL в настройки бота, если он не привязался автоматически">
                <div className="row-with-action">
                  <TextInput value="https://api.glafira.app/webhook/tg/8f3d2e91-…" mono locked />
                  <button className="btn btn-secondary btn-sm" disabled>
                    <Icon name="link" size={13}/>Копировать
                  </button>
                </div>
              </FormRow>
              <FormRow label="Приветственное сообщение" span={2}
                hint="Что Глафира пишет кандидату при первом контакте. Поддерживает {{vacancy}} и {{company}}">
                <Textarea rows={3}
                  value="Здравствуйте! Я Глафира — помогаю с подбором в {{company}}. Я задам пару коротких вопросов по вакансии «{{vacancy}}», чтобы понять, насколько она вам подходит. Это займёт 3–5 минут 🙂" />
              </FormRow>
            </div>
            <div className="integ-actions">
              <Switch value={true} disabled
                label="Включить бота" desc="Если выключено — кандидаты получают сообщение «Бот временно недоступен»"/>
              <button className="btn btn-secondary btn-sm" disabled>Проверить подключение</button>
            </div>
          </div>
        </IntegrationCard>

        {/* SMTP */}
        <IntegrationCard
          ico={<Icon name="mail" size={18}/>}
          iconBg="#FFF1C8"
          name="Почтовый сервер (SMTP)"
          desc="Отправка писем кандидатам и системных уведомлений"
          status="bad">
          <div className="integ-section">
            <div className="form-grid form-grid-2">
              <FormRow label="SMTP-сервер" required>
                <TextInput value="smtp.yandex.ru" mono locked />
              </FormRow>
              <FormRow label="Порт">
                <TextInput value="587" mono locked />
              </FormRow>
              <FormRow label="Шифрование">
                <Select value="tls"
                  options={[{value:'tls',label:'TLS (рекомендуется)'},{value:'ssl',label:'SSL'},{value:'none',label:'Без шифрования'}]}
                  disabled />
              </FormRow>
              <FormRow label="Reply-to">
                <TextInput placeholder="hr@company.ru" locked />
              </FormRow>
              <FormRow label="Email отправителя" required>
                <TextInput value="hr@company.ru" mono locked />
              </FormRow>
              <FormRow label="Имя отправителя">
                <TextInput value="HR · ООО Логос" locked />
              </FormRow>
              <FormRow label="Логин SMTP">
                <TextInput value="hr@company.ru" mono locked />
              </FormRow>
              <FormRow label="Пароль">
                <TextInput value="••••••••••••" type="password" mono locked />
              </FormRow>
            </div>
            <div className="integ-actions">
              <button className="btn btn-secondary btn-sm" disabled>Отправить тестовое письмо</button>
              <button className="btn btn-primary btn-sm" disabled>Сохранить и подключить</button>
            </div>
          </div>
        </IntegrationCard>

        {/* B24 */}
        <IntegrationCard
          ico={<span className="integ-emoji">🔵</span>}
          iconBg="#EAF3FE"
          name="Битрикс·24"
          desc="Импорт пользователей и данные о текучке"
          status="ok">
          <div className="integ-section">
            <div className="form-grid form-grid-2">
              <FormRow label="URL портала Битрикс·24" required span={2}>
                <TextInput value="https://logos.bitrix24.ru" mono locked />
              </FormRow>
            </div>

            <div className="integ-section-title" style={{marginTop:8}}>Авторизация · OAuth-приложение</div>
            <div className="form-grid form-grid-2" style={{marginTop:8}}>
              <FormRow label="Client ID">
                <TextInput placeholder="local.61f8…" mono locked />
              </FormRow>
              <FormRow label="Client Secret">
                <TextInput type="password" placeholder="••••••••••" mono locked />
              </FormRow>
              <FormRow span={2}>
                <button className="btn btn-secondary btn-sm" disabled>Авторизоваться в Битрикс·24</button>
              </FormRow>
            </div>
          </div>

          <div className="integ-divider"/>

          <div className="integ-section">
            <div className="integ-section-title">Что синхронизируется</div>
            <div className="sync-list">
              <Switch value={true} disabled label="Импортировать пользователей" desc="Настройки в разделе «Общие → Импорт пользователей»"/>
              <Switch value={true} disabled label="Получать данные о текучке" desc="Статусы сотрудников и даты увольнения для отчёта «Текучка»"/>
              <Switch value={false} disabled label="Создавать дело в Б24 при найме кандидата"/>
            </div>
          </div>
        </IntegrationCard>
      </div>

      <div className="info-banner muted">
        <Icon name="sparkle" size={14}/>
        <div>В будущих релизах сюда добавятся карточки <b>hh.ru</b>, <b>Авито Работа</b> и публикация в <b>Telegram-каналы</b>.</div>
      </div>
    </div>
  );
}