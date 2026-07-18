import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { publicClient } from '@/api/publicClient';
import './ApplyPage.css';

/** Публичная форма подачи заявки на подбор (БЕЗ авторизации). company — из токена. */
export default function ApplyPage() {
  const { token } = useParams<{ token: string }>();
  const [company, setCompany] = useState<string | null>(null);
  const [loadErr, setLoadErr] = useState(false);
  const [done, setDone] = useState<number | null | 'sent'>(null);
  const [submitting, setSubmitting] = useState(false);
  const [touched, setTouched] = useState(false);

  const [f, setF] = useState({
    authorName: '', authorRole: '', dept: '', contact: '',
    title: '', positions: 1, city: '', fmt: 'office' as 'office' | 'hybrid' | 'remote',
    deadline: '', noRush: false, priority: 'normal' as 'normal' | 'high',
    salaryFrom: '', salaryTo: '', desc: '', website: '', // website = honeypot
  });
  const set = (k: keyof typeof f, v: any) => setF((s) => ({ ...s, [k]: v }));

  useEffect(() => {
    let alive = true;
    publicClient.get(`/public/request-form/${token}`)
      .then((r) => { if (alive) setCompany(r.data.company_name); })
      .catch(() => { if (alive) setLoadErr(true); });
    return () => { alive = false; };
  }, [token]);

  const titleErr = touched && !f.title.trim();
  const descErr = touched && !f.desc.trim();

  const submit = async () => {
    setTouched(true);
    if (!f.title.trim() || !f.desc.trim()) return;
    setSubmitting(true);
    try {
      const res = await publicClient.post(`/public/request-form/${token}`, {
        title: f.title.trim(), description: f.desc.trim(),
        author_name: f.authorName.trim() || null, author_role: f.authorRole.trim() || null,
        author_contact: f.contact.trim() || null, department: f.dept.trim() || null,
        city: f.city.trim() || null, positions: Number(f.positions) || 1,
        deadline: f.noRush ? null : (f.deadline || null),
        salary_from: f.salaryFrom.trim() ? Number(f.salaryFrom) : null,
        salary_to: f.salaryTo.trim() ? Number(f.salaryTo) : null,
        employment_format: f.fmt, priority: f.priority,
        website: f.website || null,
      });
      window.scrollTo(0, 0);
      setDone(res.data.num ?? 'sent');
    } catch {
      setDone(null);
      setSubmitting(false);
    }
  };

  if (loadErr) {
    return (
      <div className="fm-bg"><div className="fm-page">
        <div className="fm-brand"><span className="fm-mark">👩🏻</span> Глафира</div>
        <div className="fm-card"><h1>Форма недоступна</h1>
          <p className="fm-sub">Ссылка недействительна или устарела. Обратитесь к рекрутеру за актуальной ссылкой.</p>
        </div>
      </div></div>
    );
  }

  return (
    <div className="fm-bg"><div className="fm-page">
      <div className="fm-brand">
        <span className="fm-mark">👩🏻</span> Глафира
        {company && <span className="co">· для сотрудников «{company}»</span>}
      </div>

      {done !== null ? (
        <div className="fm-success">
          <div className="ok">✓</div>
          <h2>{typeof done === 'number' ? `Заявка №${done} отправлена` : 'Заявка отправлена'}</h2>
          <p>Рекрутер получил её и возьмёт в работу — обычно в течение рабочего дня.
            {f.contact.trim() ? ' Он свяжется с вами по указанному контакту.' : ' Оставьте контакт, чтобы рекрутер мог связаться с вами по уточнениям.'}</p>
        </div>
      ) : (
        <div className="fm-card">
          <h1>Заявка на подбор сотрудника</h1>
          <p className="fm-sub">Опишите, кто вам нужен, — рекрутинг возьмёт заявку в работу и вернётся с уточнениями. Обычно в течение одного рабочего дня.</p>

          <div className="fm-row2">
            <label className="fm-field"><span>Ваше имя</span><input placeholder="Марина Ковалёва" value={f.authorName} onChange={(e) => set('authorName', e.target.value)} /></label>
            <label className="fm-field"><span>Ваша должность</span><input placeholder="Руководитель отдела продаж" value={f.authorRole} onChange={(e) => set('authorRole', e.target.value)} /></label>
          </div>
          <div className="fm-row2">
            <label className="fm-field"><span>Отдел</span><input placeholder="Отдел продаж" value={f.dept} onChange={(e) => set('dept', e.target.value)} /></label>
            <label className="fm-field"><span>Контакт для уточнений</span><input placeholder="Телефон или @username" value={f.contact} onChange={(e) => set('contact', e.target.value)} /></label>
          </div>
          <label className="fm-field"><span>Кто нужен <b className="req">*</b></span>
            <input className={titleErr ? 'err' : ''} placeholder="Например: Менеджер по продажам B2B" value={f.title} onChange={(e) => set('title', e.target.value)} /></label>
          <div className="fm-row3">
            <label className="fm-field"><span>Сколько человек</span><input type="number" min={1} value={f.positions} onChange={(e) => set('positions', e.target.value)} /></label>
            <label className="fm-field"><span>Город</span><input placeholder="Москва" value={f.city} onChange={(e) => set('city', e.target.value)} /></label>
            <label className="fm-field"><span>Формат</span>
              <select value={f.fmt} onChange={(e) => set('fmt', e.target.value)}>
                <option value="office">Офис</option><option value="hybrid">Гибрид</option><option value="remote">Удалённо</option>
              </select></label>
          </div>
          <div className="fm-row2">
            <div className="fm-field"><span>К какому сроку</span>
              <div className="fm-inline">
                <input type="date" style={{ flex: 1 }} disabled={f.noRush} value={f.deadline} onChange={(e) => set('deadline', e.target.value)} />
                <label className="fm-check"><input type="checkbox" checked={f.noRush} onChange={(e) => set('noRush', e.target.checked)} /> не срочно</label>
              </div></div>
            <div className="fm-field"><span>Приоритет</span>
              <div className="fm-seg">
                <button type="button" className={f.priority === 'normal' ? 'on' : ''} onClick={() => set('priority', 'normal')}>Обычный</button>
                <button type="button" className={f.priority === 'high' ? 'on' : ''} onClick={() => set('priority', 'high')}>🔥 Срочно</button>
              </div></div>
          </div>
          <div className="fm-field"><span>Зарплатная вилка <span className="fm-hint">— если не знаете, оставьте пустым</span></span>
            <div className="fm-salary">
              <span className="fm-suf"><input placeholder="от" inputMode="numeric" value={f.salaryFrom} onChange={(e) => set('salaryFrom', e.target.value)} /><i>₽</i></span>
              <span className="fm-suf"><input placeholder="до" inputMode="numeric" value={f.salaryTo} onChange={(e) => set('salaryTo', e.target.value)} /><i>₽</i></span>
            </div></div>
          <label className="fm-field"><span>Кратко: кто нужен и зачем <b className="req">*</b></span>
            <textarea className={descErr ? 'err' : ''} placeholder="Задачи, обязательный опыт и навыки, условия." value={f.desc} onChange={(e) => set('desc', e.target.value)} /></label>

          {/* honeypot: скрыто от людей, боты заполняют → заявка тихо отбрасывается */}
          <div className="fm-hp" aria-hidden="true">
            <label>Не заполняйте это поле<input tabIndex={-1} autoComplete="off" value={f.website} onChange={(e) => set('website', e.target.value)} /></label>
          </div>

          <button className="fm-submit" disabled={submitting} onClick={submit}>Отправить заявку</button>
          <p className="fm-note">Заявка попадёт к рекрутеру в CRM «Глафира» с пометкой «по ссылке-форме». Рекрутер свяжется с вами по указанному контакту.</p>
        </div>
      )}
      <div className="fm-foot">Работает на «Глафире» 💃</div>
    </div></div>
  );
}
