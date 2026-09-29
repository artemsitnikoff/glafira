// Chat — попап чатов с кандидатами (аналог чата hh.ru)
window.CHATS_DATA = [
  { id:'c1', candidateId:1, name:'Артём Чуликов', vacancy:'Frontend-разработчик (Senior)', online:true, unread:2, messages:[
    { from:'me', day:'Вчера', time:'15:02', read:true, text:'Артём, добрый день! Это Анна из «Глафиры» 👩🏻 Посмотрела ваше резюме — опыт с React очень подходящий. Хотим позвать вас на интервью 🙂' },
    { from:'them', day:'Вчера', time:'15:40', text:'Добрый день, Анна! Спасибо, очень приятно 🙂 Да, мне интересно!' },
    { from:'me', day:'Вчера', time:'15:42', read:true, text:'Отлично! ✨ Есть слоты завтра в 12:00 или 14:00 — что удобнее?' },
    { from:'them', day:'Сегодня', time:'10:46', text:'Давайте в 14:00 👍' },
    { from:'them', day:'Сегодня', time:'10:47', text:'Подскажите, интервью будет онлайн или в офисе?' },
  ]},
  { id:'c2', candidateId:2, name:'Иван Петренко', vacancy:'Региональный менеджер по продажам', unread:1, messages:[
    { from:'me', day:'Вчера', time:'18:20', read:true, text:'Иван, добрый вечер! Напоминаю про тестовое задание — дедлайн завтра в 18:00 ⏰' },
    { from:'them', day:'Сегодня', time:'09:15', text:'Добрый день! Да, помню 🙂 Отправлю сегодня вечером' },
  ]},
  { id:'c3', candidateId:3, name:'Мария Корнеева', vacancy:'HR-дженералист', online:true, unread:0, messages:[
    { from:'them', day:'Сегодня', time:'08:02', text:'Анна, доброе утро! Готова пройти тест 💪' },
    { from:'me', day:'Сегодня', time:'08:30', read:true, text:'Супер! Отправила ссылку на тест — 25 минут, лучше проходить с компьютера 🖥️ Удачи! ✨' },
  ]},
  { id:'c4', candidateId:4, name:'Олег Талалаев', vacancy:'DevOps-инженер', unread:0, messages:[
    { from:'them', day:'Вчера', time:'13:05', text:'Спасибо за встречу! Было интересно 🙌' },
    { from:'me', day:'Вчера', time:'13:12', read:true, text:'Взаимно, Олег! Вернёмся с обратной связью до пятницы 🤞' },
  ]},
  { id:'c5', candidateId:5, name:'Анна Лебедева', vacancy:'Региональный менеджер по продажам', unread:0, messages:[
    { from:'me', day:'Вчера', time:'11:40', read:true, text:'Анна, добрый день! По зарплате: вилка 120–150 тыс. + квартальные бонусы 💰 Подробности пришлю письмом' },
    { from:'them', day:'Вчера', time:'12:02', text:'Хорошо, жду деталей 🙂' },
  ]},
  { id:'c6', candidateId:8, name:'Никита Зайцев', vacancy:'Региональный менеджер по продажам', unread:0, messages:[
    { from:'me', day:'Вчера', time:'10:15', read:false, text:'Никита, добрый день! Это Анна из «Глафиры» 👩🏻 Ищем руководителя направления — ваш опыт выглядит 🔥 Будет минутка пообщаться?' },
  ]},
];

function ChatPopup({ chats, setChats, onClose, onOpenResume }) {
  const { useState, useEffect, useRef } = React;
  const [sel, setSel] = useState(null);
  const [q, setQ] = useState('');
  const [draft, setDraft] = useState('');
  const msgsRef = useRef(null);

  useEffect(() => {
    const h = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  useEffect(() => { if (msgsRef.current) msgsRef.current.scrollTop = msgsRef.current.scrollHeight; }, [sel, chats]);

  const openDlg = (id) => {
    setSel(id); setDraft('');
    setChats(cs => cs.map(c => c.id === id ? { ...c, unread: 0 } : c));
  };
  const send = () => {
    const text = draft.trim();
    if (!text || !sel) return;
    const now = new Date();
    const time = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    setChats(cs => cs.map(c => c.id === sel ? { ...c, messages: [...c.messages, { from:'me', day:'Сегодня', time, read:false, text }] } : c));
    setDraft('');
  };

  const filtered = chats.filter(c => (c.name + ' ' + c.vacancy).toLowerCase().includes(q.toLowerCase()));
  const cur = chats.find(c => c.id === sel);
  const unreadTotal = chats.reduce((s, c) => s + c.unread, 0);

  const Ticks = ({ read }) => <span className={`chp-ticks ${read ? '' : 'one'}`}>{read ? '✓✓' : '✓'}</span>;

  return (
    <>
      <div className="chp-overlay" onClick={onClose}></div>
      <div className="chp" role="dialog" aria-label="Чаты с кандидатами">
        <div className="chp-list">
          <div className="chp-list-head">
            <h3>Чаты</h3>
            {unreadTotal > 0 && <span className="chp-unread-chip">{unreadTotal}</span>}
            <button className="icon-btn" aria-label="Закрыть" onClick={onClose}><Icon name="x" size={16}/></button>
          </div>
          <div className="chp-search">
            <Icon name="search" size={13} style={{color:'var(--fg-3)', flex:'none'}}/>
            <input placeholder="Поиск по чатам…" value={q} onChange={e => setQ(e.target.value)}/>
          </div>
          <div className="chp-dialogs">
            {filtered.length === 0 && <div className="chp-empty-search">Ничего не найдено</div>}
            {filtered.map(c => {
              const last = c.messages[c.messages.length - 1];
              return (
                <div key={c.id} className={`chp-dlg ${sel === c.id ? 'chp-cur' : ''}`} onClick={() => openDlg(c.id)}>
                  <Avatar name={c.name} size="sm"/>
                  <div className="chp-dlg-main">
                    <div className="chp-dlg-top">
                      <span className="chp-dlg-name">{c.name}</span>
                      <span className="chp-dlg-time">{last.from === 'me' && <Ticks read={last.read}/>}{last.day === 'Сегодня' ? last.time : 'вчера'}</span>
                    </div>
                    <div className="chp-dlg-vac">{c.vacancy}</div>
                    <div className="chp-dlg-prev">
                      <span className="chp-dlg-text">{last.from === 'me' ? 'Вы: ' : ''}{last.text}</span>
                      {c.unread > 0 && <span className="chp-dlg-badge">{c.unread}</span>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="chp-thread">
          {!cur ? (
            <div className="chp-empty">
              <div className="chp-empty-art">
                <span className="chp-spark s1">✨</span>
                <span className="chp-spark s2">💬</span>
                <span className="chp-spark s3">💃</span>
                <div className="chp-bub chp-bub-1">👩🏻</div>
                <div className="chp-bub chp-bub-2">🙂</div>
              </div>
              <h4>Начните общаться с кандидатами</h4>
              <p>Выберите диалог слева — вся переписка сохранится в карточке кандидата</p>
            </div>
          ) : (
            <>
              <div className="chp-th">
                <Avatar name={cur.name} size="sm"/>
                <div className="chp-th-info">
                  <div className="chp-th-name">{cur.name}{cur.online && <span className="chp-online" title="Онлайн"></span>}</div>
                  <div className="chp-th-vac">{cur.vacancy}</div>
                </div>
                <button className="chp-resume-btn" onClick={() => onOpenResume(cur.candidateId)}><Icon name="open" size={13}/> Резюме</button>
              </div>
              <div className="chp-msgs" ref={msgsRef}>
                {cur.messages.map((m, i) => {
                  const prev = cur.messages[i - 1];
                  const newRun = !prev || prev.from !== m.from || prev.day !== m.day;
                  return (
                    <React.Fragment key={i}>
                      {(!prev || prev.day !== m.day) && <div className="chp-day">{m.day}</div>}
                      <div className={`chp-msg ${m.from === 'me' ? 'out' : 'in'}`}>
                        {newRun && <div className="chp-msg-who">{m.from === 'me' ? 'Анна Седова' : cur.name}</div>}
                        {m.text}
                        <div className="chp-msg-meta">{m.time}{m.from === 'me' && <Ticks read={m.read}/>}</div>
                      </div>
                    </React.Fragment>
                  );
                })}
              </div>
              <div className="chp-composer">
                <div className="chp-input">
                  <input placeholder="Напишите сообщение…" value={draft} onChange={e => setDraft(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') send(); }}/>
                  <button className="chp-emoji-btn" aria-label="Эмодзи" onClick={() => setDraft(d => d + ' 🙂')}>🙂</button>
                </div>
                <button className="chp-send" aria-label="Отправить" disabled={!draft.trim()} onClick={send}><Icon name="arrowUp" size={16}/></button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

window.ChatPopup = ChatPopup;
