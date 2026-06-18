/**
 * PhoneInput — единый компонент ввода российского телефона с маской.
 *
 * Контракт onChange:
 *   - 0 цифр → onChange(null)
 *   - 1–10 цифр → onChange('+7' + digits)  (E.164-стиль; неполный — родитель валидирует на сабмите)
 *
 * Формат отображения: флаг 🇷🇺 + «+7» зафиксированы вне поля ввода, пользователь
 * вводит ТОЛЬКО 10 цифр локального номера. Маска: (999) 123-45-67.
 *
 * Входящий value (E.164, «8...», форматированный или null) нормализуется: берутся
 * последние 10 цифр (если 11 цифр и начинается с 7 или 8 — пропускаем первую).
 */
import './PhoneInput.css';
import { useEffect, useState, useCallback } from 'react';

type Props = {
  value: string | null;
  onChange: (e164: string | null) => void;
  onBlur?: () => void;
  disabled?: boolean;
  error?: boolean;
  id?: string;
  placeholder?: string;
};

/** Извлекает ≤10 цифр локального номера из строки в любом формате. */
function extractDigits(raw: string | null | undefined): string {
  if (!raw) return '';
  const digits = raw.replace(/\D/g, '');
  if (digits.length === 11 && (digits[0] === '7' || digits[0] === '8')) {
    return digits.slice(1, 11);
  }
  // берём последние 10 (обрезаем лишние слева)
  return digits.slice(-10).slice(0, 10);
}

/** Форматирует 0–10 цифр в читаемый вид: (999) 123-45-67 по мере ввода. */
function formatDisplay(digits: string): string {
  const d = digits.slice(0, 10);
  if (d.length === 0) return '';
  let out = '(';
  out += d.slice(0, 3);
  if (d.length > 3) out += ') ' + d.slice(3, 6);
  if (d.length > 6) out += '-' + d.slice(6, 8);
  if (d.length > 8) out += '-' + d.slice(8, 10);
  return out;
}

export function PhoneInput({ value, onChange, onBlur, disabled = false, error = false, id, placeholder }: Props) {
  const [digits, setDigits] = useState<string>(() => extractDigits(value));

  // Синхронизируем внутреннее состояние при изменении value извне (редактирование)
  useEffect(() => {
    const extracted = extractDigits(value);
    setDigits(extracted);
  }, [value]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    // Оставляем только цифры, отрезаем до 10
    const cleaned = raw.replace(/\D/g, '').slice(0, 10);
    setDigits(cleaned);
    if (cleaned.length === 0) {
      onChange(null);
    } else {
      onChange('+7' + cleaned);
    }
  }, [onChange]);

  const handlePaste = useCallback((e: React.ClipboardEvent<HTMLInputElement>) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData('text');
    const extracted = extractDigits(pasted);
    const cleaned = extracted.slice(0, 10);
    setDigits(cleaned);
    if (cleaned.length === 0) {
      onChange(null);
    } else {
      onChange('+7' + cleaned);
    }
  }, [onChange]);

  const cls = [
    'phi-wrap',
    error ? 'phi-error' : '',
    disabled ? 'phi-disabled' : '',
  ].filter(Boolean).join(' ');

  const displayValue = formatDisplay(digits);
  const placeholderText = placeholder ?? '(999) 000-00-00';

  return (
    <div className={cls}>
      <span className="phi-prefix">
        <span>🇷🇺</span>
        <span className="phi-prefix-code">+7</span>
      </span>
      <input
        id={id}
        type="tel"
        inputMode="numeric"
        className="phi-input"
        value={displayValue}
        placeholder={placeholderText}
        disabled={disabled}
        onChange={handleChange}
        onPaste={handlePaste}
        onBlur={onBlur}
        autoComplete="tel-national"
        aria-label="Номер телефона"
      />
    </div>
  );
}
