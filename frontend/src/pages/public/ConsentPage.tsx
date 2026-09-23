import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { publicClient } from '@/api/publicClient';
import './ConsentPage.css';

// Публичная страница подписания согласия на обработку ПдН (БЕЗ авторизации).
// company_id — ТОЛЬКО из токена ссылки. Контракт сверен с бэкендом v1.9.0.
type ConsentInfo = {
  company_name: string | null;
  candidate_name: string | null;
  consent_text: string;
  status: 'pending' | 'signed' | 'revoked' | string;
  expires_at: string | null;
  can_sign: boolean;
  already_signed: boolean;
  expired: boolean;
};

function formatSignedAt(iso: string): string {
  try {
    return new Intl.DateTimeFormat('ru-RU', {
      day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function ConsentPage() {
  const { token } = useParams<{ token: string }>();

  const [info, setInfo] = useState<ConsentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState(false);

  const [agreed, setAgreed] = useState(false);
  const [signing, setSigning] = useState(false);
  const [signError, setSignError] = useState<string | null>(null);
  const [justSigned, setJustSigned] = useState(false);
  const [signedAt, setSignedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setLoadErr(true);
      setLoading(false);
      return;
    }
    let alive = true;
    publicClient
      .get<ConsentInfo>(`/public/consent/${token}`)
      .then((r) => { if (alive) setInfo(r.data); })
      .catch(() => { if (alive) setLoadErr(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [token]);

  const sign = async () => {
    if (!token || signing || !agreed) return;
    setSigning(true);
    setSignError(null);
    try {
      const r = await publicClient.post<{ status: string; signed_at: string }>(
        `/public/consent/${token}/sign`,
      );
      // Идемпотентно: повтор по подписанному тоже приходит 200.
      setJustSigned(true);
      setSignedAt(r.data?.signed_at ?? null);
    } catch (e: unknown) {
      const err = e as {
        response?: { status?: number; data?: { error?: { code?: string; message?: string } } };
      };
      const status = err?.response?.status;
      const code = err?.response?.data?.error?.code;
      const message = err?.response?.data?.error?.message;
      if (status === 410 || code === 'LINK_EXPIRED') {
        setSignError('Срок действия ссылки истёк. Обратитесь к рекрутёру за новой ссылкой.');
      } else if (status === 400 || code === 'CONSENT_REVOKED') {
        setSignError('Согласие было отозвано. Обратитесь к рекрутёру.');
      } else if (status === 429 || code === 'RATE_LIMITED') {
        setSignError('Слишком много попыток. Подождите минуту и попробуйте снова.');
      } else {
        setSignError(message || 'Не удалось подписать согласие. Попробуйте ещё раз.');
      }
    } finally {
      setSigning(false);
    }
  };

  const brand = (
    <div className="cns-brand">
      <span className="cns-mark">👩🏻</span> Глафира
      {info?.company_name && <span className="cns-co">· {info.company_name}</span>}
    </div>
  );

  const shell = (content: React.ReactNode) => (
    <div className="cns-bg"><div className="cns-page">{brand}{content}</div></div>
  );

  if (loading) {
    return shell(
      <div className="cns-card cns-center">
        <div className="cns-spinner" />
        <p className="cns-sub">Загрузка…</p>
      </div>,
    );
  }

  // Любая ошибка загрузки / нет токена → ссылка недействительна.
  if (loadErr || !info) {
    return shell(
      <div className="cns-card">
        <h1>Ссылка недействительна</h1>
        <p className="cns-sub">Ссылка недействительна или устарела. Обратитесь к рекрутёру за актуальной ссылкой.</p>
      </div>,
    );
  }

  // Только что подписали в этой сессии.
  if (justSigned) {
    return shell(
      <div className="cns-success">
        <div className="cns-ok">✓</div>
        <h2>Спасибо! Согласие подписано</h2>
        <p>{signedAt ? `Подписано ${formatSignedAt(signedAt)}.` : ''} Можно закрыть эту страницу.</p>
      </div>,
    );
  }

  if (info.expired) {
    return shell(
      <div className="cns-card">
        <h1>Срок действия ссылки истёк</h1>
        <p className="cns-sub">Обратитесь к рекрутёру — он пришлёт новую ссылку для подписания.</p>
      </div>,
    );
  }

  // Согласие уже было подписано ранее (дата в этом ответе не приходит).
  if (info.already_signed || info.status === 'signed') {
    return shell(
      <div className="cns-success">
        <div className="cns-ok">✓</div>
        <h2>Согласие уже подписано</h2>
        <p>Повторно подписывать не нужно. Можно закрыть эту страницу.</p>
      </div>,
    );
  }

  if (info.can_sign) {
    return shell(
      <div className="cns-card">
        <h1>Согласие на обработку персональных данных</h1>
        {info.candidate_name && <p className="cns-name">{info.candidate_name}</p>}
        <div className="cns-text">{info.consent_text}</div>

        <label className="cns-check">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>Я ознакомлен(а) с текстом и даю согласие на обработку моих персональных данных</span>
        </label>

        <button className="cns-submit" disabled={!agreed || signing} onClick={sign}>
          {signing ? 'Подписываю…' : 'Подписать'}
        </button>

        {signError && <p className="cns-err" role="alert">{signError}</p>}
      </div>,
    );
  }

  // Прочие состояния (например, отозвано) → ссылка недействительна.
  return shell(
    <div className="cns-card">
      <h1>Ссылка недействительна</h1>
      <p className="cns-sub">Подписать согласие по этой ссылке сейчас нельзя. Обратитесь к рекрутёру.</p>
    </div>,
  );
}
