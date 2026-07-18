import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../../components/ui/Icon';
import { useAuthStore } from '@/store/authStore';
import { useCreateRequest, type RequestCreateBody } from '@/api/hooks/useRequests';
import './requests.css';

export default function NewRequestPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isMgr = user?.role === 'hiring_manager';
  const createM = useCreateRequest();
  const [err, setErr] = useState<string | null>(null);

  const [f, setF] = useState({
    title: '', authorName: '', authorRole: '', authorContact: '', dept: '',
    positions: 1, city: '', fmt: 'office' as 'office' | 'hybrid' | 'remote',
    deadline: '', noRush: false, salaryFrom: '', salaryTo: '',
    priority: 'normal' as 'normal' | 'high', desc: '',
  });
  const set = (k: keyof typeof f, v: any) => setF((s) => ({ ...s, [k]: v }));
  const ok = f.title.trim() && f.desc.trim();

  const submit = async () => {
    if (!ok) return;
    setErr(null);
    const body: RequestCreateBody = {
      title: f.title.trim(),
      description: f.desc.trim(),
      department: f.dept.trim() || null,
      city: f.city.trim() || null,
      positions: Number(f.positions) || 1,
      deadline: f.noRush ? null : (f.deadline || null),
      salary_from: f.salaryFrom.trim() ? Number(f.salaryFrom) : null,
      salary_to: f.salaryTo.trim() ? Number(f.salaryTo) : null,
      employment_format: f.fmt,
      priority: f.priority,
    };
    if (!isMgr) {
      body.author_name = f.authorName.trim() || null;
      body.author_role = f.authorRole.trim() || null;
      body.author_contact = f.authorContact.trim() || null;
    }
    try {
      await createM.mutateAsync(body);
      navigate('/requests');
    } catch (e: any) {
      setErr(e?.response?.data?.error?.message || 'Не удалось создать заявку');
    }
  };

  return (
    <div className="nv-wrap">
      <div className="nv-topbar">
        <div className="nv-crumbs">
          <span className="nv-crumb-home" onClick={() => navigate('/requests')}><Icon name="inbox" size={13} /> Заявки</span>
          <span className="nv-crumb-sep">/</span>
          <span className="nv-crumb-cur">Новая заявка</span>
        </div>
        <div className="nv-top-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/requests')}><Icon name="x" size={13} /> Отмена</button>
          <button className="btn btn-primary btn-sm" disabled={!ok || createM.isPending} onClick={submit}>
            <Icon name="check" size={13} /> Создать заявку
          </button>
        </div>
      </div>
      <div className="req-fp-scroll">
        <div className="req-fp-card">
          <div className="req-fp-h1">Заявка на подбор</div>
          <p className="req-fp-sub">{isMgr
            ? 'Опишите, кто вам нужен, — рекрутинг возьмёт заявку в работу и вернётся с уточнениями. Обязательны только два поля.'
            : 'Внесите заявку со слов заказчика — если она пришла голосом или в мессенджере.'}</p>

          {err && <div className="error-banner" role="alert" style={{ marginBottom: 14 }}>{err}</div>}

          <div className="req-fp-row2">
            <label className="req-fp-field"><span>Заказчик</span>
              {isMgr ? (
                <input className="nv-input" value={`${user?.full_name || ''}${(user as any)?.position ? ` · ${(user as any).position}` : ''}`} disabled />
              ) : (
                <input className="nv-input" placeholder="Имя заказчика" value={f.authorName} onChange={(e) => set('authorName', e.target.value)} />
              )}
            </label>
            <label className="req-fp-field"><span>{isMgr ? 'Отдел' : 'Должность заказчика'}</span>
              {isMgr ? (
                <input className="nv-input" placeholder="Отдел продаж" value={f.dept} onChange={(e) => set('dept', e.target.value)} />
              ) : (
                <input className="nv-input" placeholder="Руководитель отдела" value={f.authorRole} onChange={(e) => set('authorRole', e.target.value)} />
              )}
            </label>
          </div>
          {!isMgr && (
            <div className="req-fp-row2">
              <label className="req-fp-field"><span>Отдел</span><input className="nv-input" placeholder="Отдел продаж" value={f.dept} onChange={(e) => set('dept', e.target.value)} /></label>
              <label className="req-fp-field"><span>Контакт заказчика</span><input className="nv-input" placeholder="Телефон / @username" value={f.authorContact} onChange={(e) => set('authorContact', e.target.value)} /></label>
            </div>
          )}

          <label className="req-fp-field"><span>Кто нужен <b className="req-fp-req">*</b></span>
            <input className="nv-input" placeholder="Например: Менеджер по продажам B2B" value={f.title} onChange={(e) => set('title', e.target.value)} />
          </label>
          <div className="req-fp-row3">
            <label className="req-fp-field"><span>Сколько человек</span><input className="nv-input" type="number" min={1} value={f.positions} onChange={(e) => set('positions', e.target.value)} /></label>
            <label className="req-fp-field"><span>Город</span><input className="nv-input" placeholder="Москва" value={f.city} onChange={(e) => set('city', e.target.value)} /></label>
            <label className="req-fp-field"><span>Формат</span>
              <select className="nv-input" value={f.fmt} onChange={(e) => set('fmt', e.target.value)}>
                <option value="office">Офис</option><option value="hybrid">Гибрид</option><option value="remote">Удалённо</option>
              </select>
            </label>
          </div>
          <div className="req-fp-row2">
            <div className="req-fp-field"><span>К какому сроку</span>
              <div className="req-fp-inline">
                <input className="nv-input" type="date" style={{ flex: 1 }} disabled={f.noRush} value={f.deadline} onChange={(e) => set('deadline', e.target.value)} />
                <label className="req-fp-check"><input type="checkbox" checked={f.noRush} onChange={(e) => set('noRush', e.target.checked)} /> не срочно</label>
              </div>
            </div>
            <div className="req-fp-field"><span>Приоритет</span>
              <div className="req-fp-seg">
                <button type="button" className={f.priority === 'normal' ? 'on' : ''} onClick={() => set('priority', 'normal')}>Обычный</button>
                <button type="button" className={f.priority === 'high' ? 'on' : ''} onClick={() => set('priority', 'high')}>🔥 Срочно</button>
              </div>
            </div>
          </div>
          <div className="req-fp-field"><span>Зарплатная вилка <span className="req-fp-hint">— если не знаете, оставьте пустым</span></span>
            <div className="req-fp-salary">
              <span className="req-fp-suf"><input className="nv-input" placeholder="от" inputMode="numeric" value={f.salaryFrom} onChange={(e) => set('salaryFrom', e.target.value)} /><i>₽</i></span>
              <span className="req-fp-suf"><input className="nv-input" placeholder="до" inputMode="numeric" value={f.salaryTo} onChange={(e) => set('salaryTo', e.target.value)} /><i>₽</i></span>
            </div>
          </div>
          <label className="req-fp-field"><span>Кратко: кто нужен и зачем <b className="req-fp-req">*</b></span>
            <textarea className="nv-input req-page-ta" rows={5} placeholder="Задачи, обязательный опыт и навыки, условия." value={f.desc} onChange={(e) => set('desc', e.target.value)} />
          </label>
          <button className="req-fp-submit" disabled={!ok || createM.isPending} onClick={submit}>Создать заявку</button>
          <p className="req-fp-note">{isMgr ? 'Рекрутер увидит заявку сразу; уточнения и статусы появятся здесь, в разделе «Мои заявки».' : 'Заявка будет создана со статусом «Новая».'}</p>
        </div>
      </div>
    </div>
  );
}
