import { useEffect, useState } from 'react';
import axios from 'axios';
import './survey-public.css';

// Публичная страница опроса. Открывается по секретной ссылке /pulse/survey/#<token>.
// Токен — в URL-хеше (на сервер/в логи не уходит). Авторизации нет: используем
// «голый» axios без интерсепторов проекта (иначе 401→redirect на /login).
const publicApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
});

type Question = {
  id: string;
  text: string;
  kind: 'emoji5' | 'scale5' | 'yesno' | 'nps11' | 'text';
  scale?: string | null;
  optional?: boolean;
};

type SurveyData = {
  company_name: string;
  employee_first_name: string;
  type: string;
  answered: boolean;
  questions: Question[];
};

const EMOJI = ['😡', '😞', '😐', '🙂', '😄'];

function getTokenFromHash(): string {
  // /pulse/survey/#<token>
  const hash = window.location.hash || '';
  return decodeURIComponent(hash.replace(/^#/, '').trim());
}

export default function SurveyPublicPage() {
  const [token] = useState(getTokenFromHash);
  const [survey, setSurvey] = useState<SurveyData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) {
      setLoadError('Ссылка повреждена — нет кода опроса.');
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await publicApi.get<SurveyData>(`/public/surveys/${token}`);
        if (cancelled) return;
        setSurvey(res.data);
        if (res.data.answered) setDone(true);
      } catch (e: any) {
        if (cancelled) return;
        const code = e?.response?.status;
        setLoadError(
          code === 404
            ? 'Опрос не найден. Возможно, ссылка устарела.'
            : 'Не удалось загрузить опрос. Попробуйте позже.'
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  const setAnswer = (id: string, value: string) =>
    setAnswers((prev) => ({ ...prev, [id]: value }));

  const handleSubmit = async () => {
    if (!survey) return;
    // Проверка обязательных вопросов на клиенте (бэк тоже валидирует)
    const missing = survey.questions.find(
      (q) => !q.optional && !(answers[q.id] && answers[q.id].trim())
    );
    if (missing) {
      setSubmitError('Пожалуйста, ответьте на все обязательные вопросы.');
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      await publicApi.post(`/public/surveys/${token}/answers`, {
        answers: survey.questions
          .filter((q) => answers[q.id] != null)
          .map((q) => ({ id: q.id, answer: answers[q.id] })),
      });
      setDone(true);
    } catch (e: any) {
      const code = e?.response?.status;
      const msg = e?.response?.data?.error?.message;
      setSubmitError(
        code === 409
          ? 'Этот опрос уже пройден. Спасибо!'
          : msg || 'Не удалось отправить ответы. Попробуйте ещё раз.'
      );
      if (code === 409) setDone(true);
    } finally {
      setSubmitting(false);
    }
  };

  const renderInput = (q: Question) => {
    const val = answers[q.id] ?? '';
    switch (q.kind) {
      case 'emoji5':
        return (
          <div className="spub-emoji-row">
            {EMOJI.map((e, i) => {
              const v = String(i + 1);
              return (
                <button
                  key={v}
                  type="button"
                  className={`spub-emoji ${val === v ? 'active' : ''}`}
                  onClick={() => setAnswer(q.id, v)}
                  aria-label={`Оценка ${v}`}
                >
                  {e}
                </button>
              );
            })}
          </div>
        );
      case 'scale5':
        return (
          <div className="spub-pills">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                key={n}
                type="button"
                className={`spub-pill ${val === String(n) ? 'active' : ''}`}
                onClick={() => setAnswer(q.id, String(n))}
              >
                {n}
              </button>
            ))}
          </div>
        );
      case 'nps11':
        return (
          <div className="spub-pills spub-pills-nps">
            {Array.from({ length: 11 }, (_, n) => (
              <button
                key={n}
                type="button"
                className={`spub-pill ${val === String(n) ? 'active' : ''}`}
                onClick={() => setAnswer(q.id, String(n))}
              >
                {n}
              </button>
            ))}
          </div>
        );
      case 'yesno':
        return (
          <div className="spub-yesno">
            {[
              { v: 'Да', label: 'Да' },
              { v: 'Нет', label: 'Нет' },
            ].map((o) => (
              <button
                key={o.v}
                type="button"
                className={`spub-yn ${val === o.v ? 'active' : ''}`}
                onClick={() => setAnswer(q.id, o.v)}
              >
                {o.label}
              </button>
            ))}
          </div>
        );
      case 'text':
      default:
        return (
          <textarea
            className="spub-textarea"
            value={val}
            onChange={(e) => setAnswer(q.id, e.target.value)}
            placeholder="Ваш ответ…"
            rows={3}
          />
        );
    }
  };

  return (
    <div className="spub-bg">
      <div className="spub-card">
        <div className="spub-brandbar" />
        {loading ? (
          <div className="spub-state">Загрузка опроса…</div>
        ) : loadError ? (
          <div className="spub-state spub-state-err">{loadError}</div>
        ) : done ? (
          <div className="spub-thanks">
            <div className="spub-thanks-emoji">🙏</div>
            <h2>Спасибо за ответы!</h2>
            <p>
              Ваше мнение помогает нам сделать работу{survey?.company_name ? ` в «${survey.company_name}»` : ''} лучше.
              Ответы анонимны для коллег и видны только HR.
            </p>
          </div>
        ) : survey ? (
          <>
            <div className="spub-header">
              <div className="spub-company">{survey.company_name || 'Опрос'}</div>
              <h1 className="spub-title">
                {survey.employee_first_name
                  ? `${survey.employee_first_name}, как у вас дела?`
                  : 'Как у вас дела?'}
              </h1>
              <p className="spub-sub">
                Короткий опрос об адаптации. Это займёт пару минут — отвечайте честно,
                ответы видит только HR.
              </p>
            </div>

            <div className="spub-questions">
              {survey.questions.map((q, idx) => (
                <div key={q.id} className="spub-q">
                  <div className="spub-q-text">
                    <span className="spub-q-num">{idx + 1}</span>
                    <span>
                      {q.text}
                      {q.optional && <span className="spub-opt"> · по желанию</span>}
                    </span>
                  </div>
                  {renderInput(q)}
                </div>
              ))}
            </div>

            {submitError && <div className="spub-error">{submitError}</div>}

            <button
              type="button"
              className="spub-submit"
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? 'Отправляем…' : 'Отправить ответы'}
            </button>
            <div className="spub-foot">Глафира · забота о людях</div>
          </>
        ) : null}
      </div>
    </div>
  );
}
