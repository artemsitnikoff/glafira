// Тесты — экраны внутри Глафиры (каталог, настройка, назначение, результат)
const { useState: useStateT } = React;
const { PageHead: TPageHead, Card: TCard, FormRow: TFormRow, TextInput: TTextInput,
        Select: TSelect, Switch: TSwitch, Textarea: TTextarea } = window;

/* ============================================================
   Данные
   ============================================================ */
const TESTS_LIB = [
  { id:'logic', name:'Тест на логику', kind:'Логика', qs:20, mins:20, state:'on', assigned:148,
    about:'Прогрессивные матрицы 3×3. Один блок, задания идут по возрастанию сложности.', blocks:null },
  { id:'si', name:'Структура интеллекта', kind:'Структура интеллекта', qs:57, mins:24, state:'on', assigned:63,
    about:'Четыре блока по вербальному и числовому мышлению — даёт профиль сильных сторон.',
    blocks:[
      { name:'Исключение слова', qs:15, mins:6 },
      { name:'Аналогии',         qs:15, mins:6 },
      { name:'Числовые ряды',    qs:15, mins:7 },
      { name:'Обобщение',        qs:12, mins:5 },
    ] },
  { id:'attn', name:'Внимательность (корректурная проба)', kind:'Логика', qs:40, mins:8, state:'draft', assigned:0,
    about:'Черновик. Скорость и устойчивость внимания — для линейного персонала.', blocks:null },
];

const TEST_KITS = [
  { id:'hrm', name:'HR-менеджер', items:['Тест на логику','Структура интеллекта'], mins:44, assigned:21 },
  { id:'dev', name:'Разработчик', items:['Тест на логику'], mins:20, assigned:57 },
];

const TEST_CATS = [
  { id:5, label:'Высокий',       lamp:'#16A34A', from:17, to:20 },
  { id:4, label:'Выше среднего', lamp:'#7CC08C', from:14, to:16 },
  { id:3, label:'Средний',       lamp:'#E0A21A', from:10, to:13 },
  { id:2, label:'Ниже среднего', lamp:'#E08A3C', from:7,  to:9  },
  { id:1, label:'Низкий',        lamp:'#DC4646', from:0,  to:6  },
];
const catOf = (score, max = 20) => {
  const s = Math.round(score / max * 20);
  return TEST_CATS.find(c => s >= c.from) || TEST_CATS[4];
};

// результаты тестов по кандидатам (id из CANDIDATES)
const TEST_RESULTS = {
  1: { status:'done', test:'Структура интеллекта', date:'8 апреля 2026, 14:26', score:41, max:57, spent:'21 мин из 24',
       pct:78, blocks:[{n:'Исключение слова',v:12,m:15},{n:'Аналогии',v:11,m:15},{n:'Числовые ряды',v:9,m:15},{n:'Обобщение',v:9,m:12}] },
  2: { status:'done', test:'Тест на логику', date:'9 апреля 2026, 11:03', score:17, max:20, spent:'14 мин из 20', pct:91 },
  3: { status:'sent', test:'Тест на логику', sentAt:'вчера, 17:40', expires:'через 4 дня', channel:'Telegram' },
  4: { status:'done', test:'Тест на логику', date:'7 апреля 2026, 09:12', score:8, max:20, spent:'6 мин из 20', pct:24,
       flag:'Пройден за 6 минут из 20 — втрое быстрее среднего. Доля верных ответов в конце выше, чем в начале.' },
  6: { status:'sent', test:'HR-менеджер (набор)', sentAt:'сегодня, 10:15', expires:'через 7 дней', channel:'WhatsApp' },
  7: { status:'done', test:'Тест на логику', date:'5 апреля 2026, 16:48', score:13, max:20, spent:'19 мин из 20', pct:52 },
};

/* ============================================================
   8. Каталог тестов (Настройки → Тесты)
   ============================================================ */
function SettingsTests() {
  const [cfgId, setCfg] = useStateT(null);
  const [copied, setCopied] = useStateT(null);
  if (cfgId) return <TestConfig test={TESTS_LIB.find(t => t.id === cfgId)} onBack={() => setCfg(null)}/>;
  return (
    <div className="set-content-inner">
      <TPageHead title="Тесты"
        subtitle="Тесты способностей, которые кандидат проходит по ссылке. Результат приходит в карточку кандидата."/>
      <TCard title="Отдельные тесты" desc="Кандидат открывает тест по ссылке без авторизации — таймер запускается по нажатию «Начать»."
        foot={<button className="btn btn-secondary btn-sm"><Icon name="plus" size={14}/> Добавить тест</button>}>
        <div className="ts-grid">
          {TESTS_LIB.map(t => (
            <div key={t.id} className="ts-card">
              <div className="ts-card-top">
                <span className="ts-ico"><Icon name="grid" size={18}/></span>
                <div className="ts-card-ttl">
                  <h3>{t.name}</h3>
                  <div className="kind">{t.kind}</div>
                </div>
                <span className={`ts-state ${t.state}`}>{t.state === 'on' ? 'активен' : 'черновик'}</span>
              </div>
              <div className="ts-meta">
                <span><b>{t.qs}</b> заданий</span>
                <span><b>{t.mins}</b> мин</span>
                {t.blocks && <span><b>{t.blocks.length}</b> блока</span>}
              </div>
              <div className="ts-blocks">{t.blocks ? t.blocks.map(b => b.name).join(' · ') : t.about}</div>
              <div className="ts-card-foot">
                <a className="btn btn-secondary btn-sm" href="Тесты - кандидат.html" target="_blank" rel="noreferrer">
                  <Icon name="open" size={13}/> Предпросмотр
                </a>
                <button className="btn btn-secondary btn-sm" onClick={() => setCfg(t.id)}>Настроить</button>
                <button className="btn btn-ghost btn-sm" title="Скопировать ссылку-приглашение"
                        onClick={() => { setCopied(t.id); setTimeout(() => setCopied(null), 1800); }}>
                  <Icon name={copied === t.id ? 'check' : 'link'} size={13}/>
                </button>
                <span className="assigned">назначен {t.assigned}×</span>
              </div>
            </div>
          ))}
        </div>
      </TCard>

      <TCard title="Наборы" desc="Несколько тестов одной ссылкой — кандидат проходит их подряд, с паузой между."
        foot={<button className="btn btn-secondary btn-sm"><Icon name="plus" size={14}/> Создать набор</button>}>
        <div className="ts-grid">
          {TEST_KITS.map(k => (
            <div key={k.id} className="ts-card">
              <div className="ts-card-top">
                <span className="ts-ico kit"><Icon name="copy" size={18}/></span>
                <div className="ts-card-ttl">
                  <h3>{k.name}</h3>
                  <div className="kind">{k.items.length} теста в наборе</div>
                </div>
              </div>
              <div className="ts-blocks">{k.items.join(' + ')}</div>
              <div className="ts-meta"><span><b>{k.mins}</b> мин суммарно</span></div>
              <div className="ts-card-foot">
                <button className="btn btn-secondary btn-sm">Настроить</button>
                <span className="assigned">назначен {k.assigned}×</span>
              </div>
            </div>
          ))}
        </div>
      </TCard>
    </div>
  );
}

/* ============================================================
   9. Настройка теста
   ============================================================ */
function TestConfig({ test, onBack }) {
  const [dirty, setDirty] = useStateT(false);
  const d = () => setDirty(true);
  const [shuffle, setShuffle] = useStateT(true);
  const [allowBack, setAllowBack] = useStateT(false);
  const [autoReject, setAutoReject] = useStateT(false);
  const [autoSend, setAutoSend] = useStateT(true);
  const [blocks, setBlocks] = useStateT(test.blocks || []);
  const totalQ = blocks.length ? blocks.reduce((a,b) => a + b.qs, 0) : test.qs;
  const totalM = blocks.length ? blocks.reduce((a,b) => a + b.mins, 0) : test.mins;
  return (
    <div className="set-content-inner">
      <div className="pulse-back" onClick={onBack}><Icon name="chevL" size={13}/> Все тесты</div>
      <TPageHead title={test.name} subtitle={`${test.kind} · настройка теста`} dirty={dirty} onSave={() => setDirty(false)}/>

      <TCard title="Общее">
        <div className="form-grid form-grid-2">
          <TFormRow label="Название"><TTextInput value={test.name} onChange={d}/></TFormRow>
          <TFormRow label="Тип"><TSelect value={test.kind} options={['Логика','Структура интеллекта']} onChange={d}/></TFormRow>
          <TFormRow label="Заданий" hint="Сколько заданий увидит кандидат"><TTextInput value={String(totalQ)} mono onChange={d}/></TFormRow>
          <TFormRow label="Длительность" hint="Общий лимит времени"><TTextInput value={String(totalM)} mono suffix="мин" onChange={d}/></TFormRow>
        </div>
        <div style={{marginTop:12, display:'flex', flexDirection:'column', gap:10}}>
          <TSwitch value={shuffle} onChange={v => { setShuffle(v); d(); }}
            label="Перемешивать варианты ответов"
            desc="Порядок вариантов у каждого кандидата свой — сложнее передать ответы."/>
          <TSwitch value={allowBack} onChange={v => { setAllowBack(v); d(); }}
            label="Разрешить возврат к заданиям"
            desc="Кандидат сможет вернуться к предыдущему заданию внутри блока."/>
        </div>
      </TCard>

      {blocks.length > 0 && (
        <TCard title="Блоки" desc="Порядок можно менять перетаскиванием. Время считается по каждому блоку отдельно.">
          {blocks.map((b, i) => (
            <div key={i} className="ts-blk">
              <span className="drag"><Icon name="sort" size={15}/></span>
              <span className="n">{i+1}</span>
              <span className="nm">{b.name}</span>
              <span className="qn">{b.qs} заданий</span>
              <span className="mins">
                <input value={b.mins} onChange={e => {
                  const n = blocks.slice(); n[i] = {...b, mins: +e.target.value || 0}; setBlocks(n); d();
                }}/> мин
              </span>
              <button className="row-icon-btn" onClick={() => { setBlocks(blocks.filter((_,x) => x !== i)); d(); }}>
                <Icon name="x" size={14}/>
              </button>
            </div>
          ))}
          <button className="fn-add" onClick={() => { setBlocks([...blocks, { name:'Новый блок', qs:10, mins:5 }]); d(); }}>
            <Icon name="plus" size={14}/> Добавить блок
          </button>
          <div className="ts-total">Всего: <b>{totalQ}</b> заданий · <b>{totalM}</b> мин</div>
        </TCard>
      )}

      <TCard title="Пороги" desc="Границы категорий по баллу. Категория показывается рекрутёру в карточке кандидата — кандидат её не видит.">
        <div className="ts-thresholds">
          {TEST_CATS.map(c => (
            <div key={c.id} className="ts-thr">
              <span className="lamp" style={{background:c.lamp}}/>
              <span className="nm">{c.label}</span>
              <input defaultValue={c.from} onChange={d}/>
              <input defaultValue={c.to} onChange={d}/>
            </div>
          ))}
        </div>
      </TCard>

      <TCard title="Автоматика" desc="Глафира может отправлять тест и отсеивать по результату без участия рекрутёра.">
        <div style={{display:'flex', flexDirection:'column', gap:12}}>
          <TSwitch value={autoSend} onChange={v => { setAutoSend(v); d(); }}
            label="Отправлять тест автоматически на этапе"
            desc="Как только кандидат попадает на выбранный этап, Глафира отправляет ссылку в предпочтительный канал."/>
          {autoSend && (
            <div style={{paddingLeft:46, maxWidth:320}}>
              <TSelect value="Скрининг" options={['Отклик','Скрининг','Интервью','Оффер']} onChange={d}/>
            </div>
          )}
          <TSwitch value={autoReject} onChange={v => { setAutoReject(v); d(); }}
            label="Автоматически отклонять при результате ниже порога"
            desc="Отказ уходит с причиной «Не прошёл тест». Рекрутёр видит это в ленте действий."/>
          {autoReject && (
            <div style={{paddingLeft:46, display:'flex', alignItems:'center', gap:9}}>
              <span style={{fontSize:12.5, color:'var(--fg-2)'}}>Порог, баллов:</span>
              <div style={{width:90}}><TTextInput value="8" mono onChange={d}/></div>
              <span className="ts-cat c2">ниже среднего</span>
            </div>
          )}
        </div>
      </TCard>
    </div>
  );
}

/* ============================================================
   10. Назначение теста кандидату (модалка)
   ============================================================ */
function AssignTestModal({ candidate, onClose }) {
  const [pick, setPick] = useStateT('logic');
  const [days, setDays] = useStateT(7);
  const [chan, setChan] = useStateT('tg');
  const [sent, setSent] = useStateT(false);
  const pickName = (TESTS_LIB.find(t => t.id === pick) || TEST_KITS.find(k => k.id === pick) || {}).name;
  const name = (candidate?.name || 'Кандидат').split(' ')[1] || candidate?.name;
  const tpl = `${name}, здравствуйте! Это Анна из «Логоса». Следующий шаг по вакансии — короткий тест «${pickName}». Он занимает около 20 минут, проходить лучше в спокойной обстановке: таймер идёт непрерывно.\n\nСсылка действует ${days} дней: glafira.hr/t/8kq2vd`;
  return (
    <div className="ts-ovl" onClick={onClose}>
      <div className="ts-modal" onClick={e => e.stopPropagation()}>
        <div className="ts-modal-head">
          <div>
            <h3>Назначить тест</h3>
            <div className="sub">{candidate?.name} · Frontend-разработчик (Senior)</div>
          </div>
          <button className="x" onClick={onClose}><Icon name="x" size={16}/></button>
        </div>

        {sent ? (
          <div className="ts-modal-body">
            <div className="ts-sent"><Icon name="check" size={16}/> Ссылка отправлена, ожидаем прохождения</div>
            <div style={{fontSize:13, color:'var(--fg-2)', lineHeight:1.6}}>
              «{pickName}» ушёл {chan === 'tg' ? 'в Telegram' : chan === 'mail' ? 'на e-mail' : 'в WhatsApp'} и действует {days} дней.
              Результат появится во вкладке «Тесты» сразу после прохождения — Глафира пришлёт уведомление.
            </div>
          </div>
        ) : (
          <div className="ts-modal-body">
            <div>
              <span className="ts-lbl">Что назначаем</span>
              <div className="ts-pick">
                {TESTS_LIB.filter(t => t.state === 'on').map(t => (
                  <button key={t.id} className={`ts-pick-opt ${pick === t.id ? 'on' : ''}`} onClick={() => setPick(t.id)}>
                    <span className="ts-ico" style={{width:30, height:30, borderRadius:8}}><Icon name="grid" size={15}/></span>
                    <span className="nm">{t.name}</span>
                    <span className="mt">{t.qs} заданий · {t.mins} мин</span>
                  </button>
                ))}
                {TEST_KITS.map(k => (
                  <button key={k.id} className={`ts-pick-opt ${pick === k.id ? 'on' : ''}`} onClick={() => setPick(k.id)}>
                    <span className="ts-ico kit" style={{width:30, height:30, borderRadius:8}}><Icon name="copy" size={15}/></span>
                    <span className="nm">Набор «{k.name}»</span>
                    <span className="mt">{k.items.length} теста · {k.mins} мин</span>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <span className="ts-lbl">Срок действия ссылки</span>
              <div className="ts-days">
                <input value={days} onChange={e => setDays(+e.target.value || 0)}/>
                <span>дней — после этого ссылка перестанет открываться</span>
              </div>
            </div>

            <div>
              <span className="ts-lbl">Канал отправки</span>
              <div className="ts-chan">
                <button className={chan === 'tg' ? 'on' : ''} onClick={() => setChan('tg')}>
                  <span className="pref">предпочитает</span>Telegram
                </button>
                <button className={chan === 'mail' ? 'on' : ''} onClick={() => setChan('mail')}>E-mail</button>
                <button className={chan === 'wa' ? 'on' : ''} onClick={() => setChan('wa')}>WhatsApp</button>
              </div>
            </div>

            <div>
              <span className="ts-lbl">Текст сообщения</span>
              <textarea className="ts-tpl" defaultValue={tpl} key={pick + days}/>
            </div>
          </div>
        )}

        <div className="ts-modal-foot">
          <span className="sp"/>
          {sent
            ? <button className="btn btn-primary btn-sm" onClick={onClose}>Готово</button>
            : <>
                <button className="btn btn-secondary btn-sm" onClick={onClose}>Отмена</button>
                <button className="btn btn-primary btn-sm" onClick={() => setSent(true)}>Отправить</button>
              </>}
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   11. Вкладка «Тесты» в карточке кандидата
   ============================================================ */
const ANSWER_ROWS = [
  { n:1, a:'в', ok:true,  t:'0:22' }, { n:2, a:'а', ok:true,  t:'0:31' },
  { n:3, a:'д', ok:false, t:'1:04' }, { n:4, a:'б', ok:true,  t:'0:44' },
  { n:5, a:'г', ok:true,  t:'0:38' }, { n:6, a:'а', ok:false, t:'1:22' },
  { n:7, a:'в', ok:true,  t:'0:51' }, { n:8, a:'—', ok:false, t:'—'    },
];

function TestsTab({ c }) {
  const [assign, setAssign] = useStateT(false);
  const [open, setOpen] = useStateT(false);
  const r = TEST_RESULTS[c.id];

  if (!r) return (
    <>
      <div className="ts-empty">
        <div className="empty-illust" style={{margin:'0 auto'}}><Icon name="grid" size={34}/></div>
        <h3>Тест не назначен</h3>
        <p>Отправьте кандидату тест способностей — ссылка уйдёт в предпочтительный канал, результат придёт сюда.</p>
        <button className="btn btn-primary btn-sm" onClick={() => setAssign(true)}>Назначить тест</button>
      </div>
      {assign && <AssignTestModal candidate={c} onClose={() => setAssign(false)}/>}
    </>
  );

  if (r.status === 'sent') return (
    <>
      <div className="ts-res">
        <div className="ts-pending">
          <span className="ico"><Icon name="clock" size={17}/></span>
          <div className="tx">
            <b>«{r.test}» — ожидаем прохождения</b>
            <span>Ссылка отправлена {r.sentAt} в {r.channel} · действует ещё {r.expires.replace('через ','')}</span>
          </div>
          <button className="btn btn-secondary btn-sm">Напомнить</button>
          <button className="btn btn-ghost btn-sm">Отменить</button>
        </div>
      </div>
      {assign && <AssignTestModal candidate={c} onClose={() => setAssign(false)}/>}
    </>
  );

  const cat = catOf(r.score, r.max);
  return (
    <>
      <div className="ts-res">
        <div className="ts-res-card">
          <div className="ts-res-head">
            <div className="ttl">
              <h4>{r.test}</h4>
              <div className="when">{r.date} · {r.spent}</div>
            </div>
            <div className="ts-score">{r.score}<span className="of">&thinsp;/&thinsp;{r.max}</span></div>
            <span className={`ts-cat c${cat.id}`}>{cat.label}</span>
          </div>
          <div className="ts-res-body">
            {r.flag && (
              <div className="ts-flag">
                <Icon name="alert" size={16} style={{flex:'none', marginTop:1}}/>
                <div><b>Результат может быть недостоверен</b>{r.flag}</div>
              </div>
            )}
            {r.blocks && (
              <div>
                <div className="ts-subhead" style={{marginBottom:10}}>Профиль по блокам</div>
                <div className="ts-bars">
                  {r.blocks.map(b => {
                    const p = b.v / b.m;
                    return (
                      <div key={b.n} className="ts-bar">
                        <span className="nm">{b.n}</span>
                        <span className="track"><i className={p >= .75 ? 'strong' : p < .65 ? 'weak' : ''} style={{width:`${p*100}%`}}/></span>
                        <span className="val">{b.v}/{b.m}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
            <div className="ts-pct">
              <Icon name="chart" size={15}/> Результат выше, чем у <b>&nbsp;{r.pct}%&nbsp;</b> кандидатов на схожие позиции
              <span style={{marginLeft:'auto', fontSize:11.5, color:'var(--fg-3)'}}>база: 211 прохождений</span>
            </div>

            <div className="ts-exp">
              <button className="ts-exp-btn" onClick={() => setOpen(o => !o)}>
                <Icon name={open ? 'chevD' : 'chevR'} size={14}/> Ответы по заданиям
              </button>
              {open && (
                <table className="ts-ans">
                  <thead><tr><th style={{width:70}}>Задание</th><th style={{width:90}}>Ответ</th><th style={{width:110}}>Результат</th><th>Время</th></tr></thead>
                  <tbody>
                    {ANSWER_ROWS.map(a => (
                      <tr key={a.n}>
                        <td className="mono">{a.n}</td>
                        <td className="mono">{a.a}</td>
                        <td className={a.ok ? 'ok' : 'no'}>{a.ok ? 'верно' : a.a === '—' ? 'нет ответа' : 'неверно'}</td>
                        <td className="mono">{a.t}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
        <div style={{display:'flex', gap:8}}>
          <button className="btn btn-secondary btn-sm" onClick={() => setAssign(true)}>Назначить ещё тест</button>
          <a className="btn btn-ghost btn-sm" href="Тесты - кандидат.html" target="_blank" rel="noreferrer">
            <Icon name="open" size={13}/> Как это видел кандидат
          </a>
        </div>
      </div>
      {assign && <AssignTestModal candidate={c} onClose={() => setAssign(false)}/>}
    </>
  );
}

/* ============================================================
   12. Плашка теста в таблице воронки
   ============================================================ */
function TestPill({ candidateId }) {
  const r = TEST_RESULTS[candidateId];
  if (!r) return <span className="ts-dash">—</span>;
  if (r.status === 'sent') return <span className="ts-pill wait" title={`Отправлен ${r.sentAt}`}>⏳ ожидаем</span>;
  const cat = catOf(r.score, r.max);
  return <span className={`ts-pill c${cat.id}`} title={`${r.test} · ${cat.label}`}>{r.score}/{r.max}</span>;
}

Object.assign(window, { SettingsTests, TestConfig, AssignTestModal, TestsTab, TestPill,
                        TESTS_LIB, TEST_KITS, TEST_RESULTS, TEST_CATS });
