import { useState, type FormEvent } from 'react';
import { useLogin } from '@/api/hooks/useLogin';
import './LoginPage.css';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const login = useLogin();

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ email, password });
  };

  const errCode = (login.error as any)?.error?.code;
  const errMsg =
    errCode === 'INVALID_CREDENTIALS' ? 'Неверный email или пароль' :
    errCode === 'USER_INACTIVE' ? 'Пользователь деактивирован' :
    (login.error as any)?.error?.message ?? (login.error as any)?.message;

  return (
    <div className="login-page">
      <div className="login-brand">👩🏻 Глафира 💃</div>

      <form onSubmit={onSubmit} className="login-form">
        <h1>Вход в систему</h1>

        <label className="login-field">
          <span>Email</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="your.email@example.com"
          />
        </label>

        <label className="login-field">
          <span>Пароль</span>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Введите пароль"
          />
        </label>

        {errMsg && <div className="login-error">{errMsg}</div>}

        <button type="submit" disabled={login.isPending} className="login-submit">
          {login.isPending ? 'Вход…' : 'Войти'}
        </button>
      </form>
    </div>
  );
}