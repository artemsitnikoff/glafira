// AnalyticsReports — отчёты 4-7 (Источники, Отказы, Текучка, Рекрутеры)

/* ============================================================
   ОТЧЁТ 4. ИСТОЧНИКИ
   ============================================================ */
function AnSources({ period }) {
  const sources = [
    { src: 'hh.ru',                kandidatov: 487, conv: 4.2, days: 24, churn: 14, color: '#DC4646' },
    { src: 'Авито Работа',         kandidatov: 312, conv: 6.8, days: 18, churn: 18, color: '#E08A3C' },
    { src: 'Анатолий (Telegram)',  kandidatov: 156, conv: 12.1, days: 11, churn: 8,  color: '#2A8AF0' },
    { src: 'Импорт / парсинг',     kandidatov: 89,  conv: 9.0, days: 16, churn: 11, color: '#3FA3B3' },
    { src: 'Ручной ввод',          kandidatov: 23,  conv: 21.7, days: 9, churn: 5,  color: '#7E5CF0' },
  ];

  const stackedData = sources.map(s => ({ label: s.src, value: s.kandidatov, color: s.color }));

  // dynamics — фейк по неделям/месяцам
  const dynamicsData = [
    { x: 'Нед.1', hh: 110, avito: 72, tg: 31, import: 18, manual: 4 },
    { x: 'Нед.2', hh: 124, avito: 68, tg: 38, import: 22, manual: 6 },
    { x: 'Нед.3', hh: 132, avito: 84, tg: 42, import: 24, manual: 7 },
    { x: 'Нед.4', hh: 121, avito: 88, tg: 45, import: 25, manual: 6 },
  ];
  const series = [
    { key: 'hh',     label: 'hh.ru',          color: '#DC4646' },
    { key: 'avito',  label: 'Авито',          color: '#E08A3C' },
    { key: 'tg',     label: 'Анатолий (TG)',  color: '#2A8AF0' },
    { key: 'import', label: 'Импорт',         color: '#3FA3B3' },
    { key: 'manual', label: 'Ручной ввод',    color: '#7E5CF0' },
  ];

  return (
    <>
      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Распределение по источникам</div>
            <div className="sub">Сколько кандидатов пришло из каждого канала за период.</div>
          </div>
        </div>
        <StackedBar data={stackedData}/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Эффективность источников</div>
            <div className="sub">Объективное сравнение каналов не по объёму, а по качеству.</div>
          </div>
        </div>
        <div className="an-table">
          <div className="an-thead">
            <div style={{ flex: 2 }}>Источник</div>
            <div style={{ width: 110, textAlign: 'right' }}>Кандидатов</div>
            <div style={{ width: 130, textAlign: 'right' }}>Конверсия в найм</div>
            <div style={{ width: 130, textAlign: 'right' }}>Срок до найма</div>
            <div style={{ width: 130, textAlign: 'right' }}>Текучка 90д</div>
          </div>
          {sources.map((s, i) => (
            <div key={i} className="an-trow">
              <div style={{ flex: 2 }} className="an-cell-link">
                <span className="src-dot" style={{ background: s.color }}/>
                {s.src}
              </div>
              <div style={{ width: 110, textAlign: 'right' }} className="t-num">{s.kandidatov}</div>
              <div style={{ width: 130, textAlign: 'right' }}>
                <span className={`an-pill ${s.conv > 10 ? 'an-pill-green' : s.conv < 5 ? 'an-pill-red' : 'an-pill-gray'}`}>
                  {s.conv}%
                </span>
              </div>
              <div style={{ width: 130, textAlign: 'right' }} className="t-num">{s.days} дней</div>
              <div style={{ width: 130, textAlign: 'right' }}>
                <span className={`an-pill ${s.churn < 10 ? 'an-pill-green' : s.churn > 15 ? 'an-pill-red' : 'an-pill-gray'}`}>
                  {s.churn}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Динамика источников</div>
            <div className="sub">Какие каналы растут, какие сдыхают.</div>
          </div>
        </div>
        <MultiLineChart data={dynamicsData} series={series} height={240}/>
      </div>
    </>
  );
}

/* ============================================================
   ОТЧЁТ 5. ПРИЧИНЫ ОТКАЗОВ
   ============================================================ */
function AnRejections({ period }) {
  const sides = [
    { label: 'Кандидат отказал', value: 162, color: '#E08A3C' },
    { label: 'Мы отказали',      value: 384, color: '#5B6573' },
  ];

  const byCandidate = [
    { label: 'Не вышел на связь',     value: 64 },
    { label: 'Не устроила ЗП',         value: 38 },
    { label: 'Принял другой оффер',    value: 28, highlight: true },
    { label: 'Слишком далеко от дома', value: 19 },
    { label: 'Не устроил график',      value: 13 },
  ];
  const byCompany = [
    { label: 'Несоответствие опыта',           value: 142, highlight: true },
    { label: 'Несоответствие навыков',          value: 96 },
    { label: 'Не прошёл интервью',              value: 78 },
    { label: 'Завышенные ожидания по ЗП',       value: 44 },
    { label: 'Не прошёл СБ',                    value: 24 },
  ];

  const stages = [
    { stage: 'Отклик',                bumped: 488, top: 'Несоответствие опыта' },
    { stage: 'Отобран',               bumped: 156, top: 'Не вышел на связь' },
    { stage: 'Контакт с рекрутером',  bumped: 88,  top: 'Не вышел на связь' },
    { stage: 'Интервью',              bumped: 64,  top: 'Не прошёл интервью' },
    { stage: 'Контакт с менеджером',  bumped: 42,  top: 'Несоответствие навыков' },
    { stage: 'Оффер',                 bumped: 16,  top: 'Принял другой оффер' },
  ];

  return (
    <>
      <div className="an-row-2">
        <div className="an-card">
          <div className="an-card-head">
            <div>
              <div className="title">Кто отказал</div>
              <div className="sub">Распределение отказов за период.</div>
            </div>
          </div>
          <DonutChart data={sides} centerValue={(sides[0].value + sides[1].value).toLocaleString('ru-RU')}
            centerLabel="отказов всего"/>
        </div>
        <div className="an-card">
          <div className="an-card-head">
            <div className="title">Топ-причин: со стороны кандидата</div>
          </div>
          <HBarChart data={byCandidate} maxLabel={220}/>
        </div>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div className="title">Топ-причин: со стороны компании</div>
        </div>
        <HBarChart data={byCompany} maxLabel={240}/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div className="title">Этапы, где чаще всего отказывают</div>
        </div>
        <div className="an-table">
          <div className="an-thead">
            <div style={{ flex: 1 }}>Этап</div>
            <div style={{ width: 130, textAlign: 'right' }}>Отвалилось</div>
            <div style={{ flex: 2 }}>Самая частая причина</div>
          </div>
          {stages.map((s, i) => (
            <div key={i} className="an-trow">
              <div style={{ flex: 1 }}>{s.stage}</div>
              <div style={{ width: 130, textAlign: 'right' }} className="t-num">{s.bumped}</div>
              <div style={{ flex: 2 }}>{s.top}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

/* ============================================================
   ОТЧЁТ 6. ТЕКУЧКА ПОСЛЕ НАЙМА
   ============================================================ */
function AnTurnover({ period, hasBitrix }) {
  if (!hasBitrix) {
    return (
      <div className="an-empty-big">
        <div className="ill"><Icon name="chart" size={48}/></div>
        <h2>Подключите Битрикс·24, чтобы видеть данные о текучке</h2>
        <p>Текучка считается на основе данных о статусе сотрудников из вашей CRM. Без интеграции этот раздел недоступен.</p>
        <button className="an-btn-primary">Перейти к настройкам интеграции</button>
      </div>
    );
  }

  const periods = [
    { label: '0–30 дн.',   value: 12, sub: 'испытательный', color: '#DC4646' },
    { label: '31–60 дн.',  value: 8,  color: '#E0A21A' },
    { label: '61–90 дн.',  value: 6,  color: '#E0A21A' },
    { label: '91–180 дн.', value: 4,  color: '#59A861' },
    { label: '180–365 дн.', value: 3, color: '#16A34A' },
    { label: '365+ дн.',    value: 2, color: '#16A34A' },
  ];

  const cohort = [
    { month: 'Янв 2025', hired: 14, retention: { d30: 92, d90: 78, d180: 64 } },
    { month: 'Фев 2025', hired: 18, retention: { d30: 88, d90: 82, d180: 71 } },
    { month: 'Мар 2025', hired: 16, retention: { d30: 94, d90: 81, d180: 75 } },
    { month: 'Апр 2025', hired: 22, retention: { d30: 95, d90: 86, d180: 78 } },
    { month: 'Май 2025', hired: 19, retention: { d30: 89, d90: 84, d180: null } },
    { month: 'Июн 2025', hired: 24, retention: { d30: 96, d90: 87, d180: null } },
    { month: 'Июл 2025', hired: 21, retention: { d30: 95, d90: null, d180: null } },
  ];

  const worstVacancies = [
    { v: 'Кладовщик',                hired: 12, left: 7, churn: 58, reason: 'Не устроила ЗП' },
    { v: 'Менеджер по продажам',     hired: 8,  left: 3, churn: 38, reason: 'Не справился с планом' },
    { v: 'Оператор склада',          hired: 9,  left: 3, churn: 33, reason: 'Не устроил график' },
    { v: 'Кассир',                   hired: 14, left: 4, churn: 29, reason: 'Не устроила ЗП' },
    { v: 'Frontend (Senior)',        hired: 5,  left: 0, churn: 0,  reason: '—' },
  ];

  const sourceTurnover = [
    { src: 'hh.ru',               hired: 48, churn: 14, color: '#DC4646' },
    { src: 'Авито Работа',        hired: 32, churn: 18, color: '#E08A3C' },
    { src: 'Анатолий (Telegram)', hired: 24, churn: 8,  color: '#2A8AF0' },
    { src: 'Импорт / парсинг',    hired: 14, churn: 11, color: '#3FA3B3' },
    { src: 'Ручной ввод',         hired: 6,  churn: 5,  color: '#7E5CF0' },
  ];

  return (
    <>
      <div className="an-kpi-band band-3">
        <AnKpi label="Текучка 30 дней" value="6.4" unit="%"
          delta={{ kind: 'down-good', text: '▼ 1.2 п.п.' }} deltaSub="к прошлому периоду"
          accent="#DC4646"/>
        <AnKpi label="Текучка 90 дней" value="14.2" unit="%"
          delta={{ kind: 'down-good', text: '▼ 0.8 п.п.' }} deltaSub="к прошлому периоду"/>
        <AnKpi label="Удержание 1 год" value="68" unit="%"
          delta={{ kind: 'up', text: '▲ 4 п.п.' }} deltaSub="к прошлому году"
          accent="#16A34A"/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Когда уходят</div>
            <div className="sub">Пик в первый месяц = плохо подбираем. Пик через год = проблема в условиях работы.</div>
          </div>
        </div>
        <VBarChart data={periods} unit=" чел." height={220}/>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Когортный анализ — текучка по месяцам найма</div>
            <div className="sub">% выживших сотрудников через 30 / 90 / 180 дней. Зелёное = хорошо.</div>
          </div>
        </div>
        <CohortMatrix rows={cohort}
          cols={[
            { key: 'd30',  label: '30 дней' },
            { key: 'd90',  label: '90 дней' },
            { key: 'd180', label: '180 дней' },
          ]}/>
      </div>

      <div className="an-row-2">
        <div className="an-card">
          <div className="an-card-head">
            <div>
              <div className="title">Вакансии с самой высокой текучкой</div>
              <div className="sub">«Дырявое ведро» — разговор с заказчиком, а не с рекрутером.</div>
            </div>
          </div>
          <div className="an-table">
            <div className="an-thead">
              <div style={{ flex: 2 }}>Вакансия</div>
              <div style={{ width: 70, textAlign: 'right' }}>Нанято</div>
              <div style={{ width: 90, textAlign: 'right' }}>Уволилось</div>
              <div style={{ width: 90, textAlign: 'right' }}>% 90д</div>
            </div>
            {worstVacancies.map((r, i) => (
              <div key={i} className="an-trow">
                <div style={{ flex: 2 }} className="an-cell-link">{r.v}</div>
                <div style={{ width: 70, textAlign: 'right' }} className="t-num">{r.hired}</div>
                <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.left}</div>
                <div style={{ width: 90, textAlign: 'right' }}>
                  <span className={`an-pill ${r.churn > 40 ? 'an-pill-red' : r.churn > 20 ? 'an-pill-yellow' : 'an-pill-green'}`}>
                    {r.churn}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="an-card">
          <div className="an-card-head">
            <div>
              <div className="title">Текучка по источникам</div>
              <div className="sub">Откуда приходят кандидаты, которые остаются.</div>
            </div>
          </div>
          <div className="an-table">
            <div className="an-thead">
              <div style={{ flex: 2 }}>Источник</div>
              <div style={{ width: 80, textAlign: 'right' }}>Нанято</div>
              <div style={{ width: 100, textAlign: 'right' }}>% 90д</div>
            </div>
            {sourceTurnover.map((r, i) => (
              <div key={i} className="an-trow">
                <div style={{ flex: 2 }} className="an-cell-link">
                  <span className="src-dot" style={{ background: r.color }}/>
                  {r.src}
                </div>
                <div style={{ width: 80, textAlign: 'right' }} className="t-num">{r.hired}</div>
                <div style={{ width: 100, textAlign: 'right' }}>
                  <span className={`an-pill ${r.churn < 10 ? 'an-pill-green' : r.churn > 15 ? 'an-pill-red' : 'an-pill-yellow'}`}>
                    {r.churn}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

/* ============================================================
   ОТЧЁТ 7. РЕКРУТЕРЫ (только для админов)
   ============================================================ */
function AnRecruiters({ period }) {
  const recruiters = [
    { name: 'Анна Седова',   active: 5, closed: 8, days: 19, conv: 7.2, churn: 8 },
    { name: 'Иван Петров',   active: 7, closed: 6, days: 28, conv: 4.1, churn: 18 },
    { name: 'Мария Орлова',  active: 4, closed: 5, days: 22, conv: 5.8, churn: 12 },
    { name: 'Денис Ковалёв', active: 6, closed: 4, days: 31, conv: 3.6, churn: 22 },
    { name: 'Юлия Белая',    active: 3, closed: 7, days: 17, conv: 8.9, churn: 6 },
  ];

  const dyn = [
    { x: 'Нед.1', anna: 2, ivan: 1, maria: 1, denis: 0, julia: 2 },
    { x: 'Нед.2', anna: 2, ivan: 2, maria: 1, denis: 1, julia: 2 },
    { x: 'Нед.3', anna: 2, ivan: 1, maria: 2, denis: 1, julia: 1 },
    { x: 'Нед.4', anna: 2, ivan: 2, maria: 1, denis: 2, julia: 2 },
  ];
  const series = [
    { key: 'anna',  label: 'Анна С.',   color: '#2A8AF0' },
    { key: 'ivan',  label: 'Иван П.',   color: '#DC4646' },
    { key: 'maria', label: 'Мария О.',  color: '#7E5CF0' },
    { key: 'denis', label: 'Денис К.',  color: '#E08A3C' },
    { key: 'julia', label: 'Юлия Б.',   color: '#16A34A' },
  ];

  return (
    <>
      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Производительность рекрутеров</div>
            <div className="sub">Кликните по строке, чтобы открыть отчёт по рекрутеру.</div>
          </div>
        </div>
        <div className="an-table">
          <div className="an-thead">
            <div style={{ flex: 2 }}>Рекрутер</div>
            <div style={{ width: 90, textAlign: 'right' }}>Активных</div>
            <div style={{ width: 90, textAlign: 'right' }}>Закрыто</div>
            <div style={{ width: 110, textAlign: 'right' }}>Время найма</div>
            <div style={{ width: 110, textAlign: 'right' }}>Конверсия</div>
            <div style={{ width: 110, textAlign: 'right' }}>Текучка 90д</div>
          </div>
          {recruiters.map((r, i) => (
            <div key={i} className="an-trow">
              <div style={{ flex: 2 }} className="an-cell-link">
                <Avatar name={r.name} size="sm"/>
                <span style={{ marginLeft: 10 }}>{r.name}</span>
              </div>
              <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.active}</div>
              <div style={{ width: 90, textAlign: 'right' }} className="t-num">{r.closed}</div>
              <div style={{ width: 110, textAlign: 'right' }} className="t-num">{r.days} дней</div>
              <div style={{ width: 110, textAlign: 'right' }}>
                <span className={`an-pill ${r.conv > 6 ? 'an-pill-green' : r.conv < 4 ? 'an-pill-red' : 'an-pill-gray'}`}>
                  {r.conv}%
                </span>
              </div>
              <div style={{ width: 110, textAlign: 'right' }}>
                <span className={`an-pill ${r.churn < 10 ? 'an-pill-green' : r.churn > 15 ? 'an-pill-red' : 'an-pill-yellow'}`}>
                  {r.churn}%
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="an-card">
        <div className="an-card-head">
          <div>
            <div className="title">Динамика производительности команды</div>
            <div className="sub">Число закрытых вакансий по неделям.</div>
          </div>
        </div>
        <MultiLineChart data={dyn} series={series} height={240}/>
      </div>
    </>
  );
}

window.AnSources = AnSources;
window.AnRejections = AnRejections;
window.AnTurnover = AnTurnover;
window.AnRecruiters = AnRecruiters;

// Also export inner overview/speed/funnel which Analytics.jsx defines
// (they're already in scope via Babel global, but explicit window assignment
// from Analytics.jsx would be cleaner — we keep the Analytics shell as the entry point).
