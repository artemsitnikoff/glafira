/**
 * PhoneInput — единый ввод телефона на базе react-international-phone.
 *
 * Флаг страны + код (+7) — в отдельном дропдауне (НЕ в поле ввода); флаг меняется
 * по коду страны. Человек вводит национальный номер, библиотека форматирует.
 *
 * Контракт наружу (формат ХРАНЕНИЯ): ЦИФРЫ БЕЗ '+' — '79991234567' или null.
 *   - value: цифры без '+' из БД (или null) → внутрь библиотеки уходит как '+'+digits.
 *   - onChange: отдаёт цифры без '+' (или null, если национальной части нет).
 */
import 'react-international-phone/style.css';
import './PhoneInput.css';
import { PhoneInput as IntlPhoneInput } from 'react-international-phone';

type Props = {
  value: string | null;
  onChange: (digits: string | null) => void;
  onBlur?: () => void;
  disabled?: boolean;
  error?: boolean;
  id?: string;
  placeholder?: string;
};

export function PhoneInput({ value, onChange, onBlur, disabled = false, error = false, id, placeholder }: Props) {
  return (
    <div className={['phi-wrap', error ? 'phi-error' : ''].filter(Boolean).join(' ')}>
      <IntlPhoneInput
        defaultCountry="ru"
        value={value ? '+' + value : ''}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(phone, meta) => {
          const digits = (phone || '').replace(/\D/g, '');
          const dial = meta?.country?.dialCode ?? '';
          // национальная часть = всё после кода страны; если пусто → телефон не введён
          const national = digits.slice(dial.length);
          onChange(national ? digits : null);
        }}
        inputProps={{ id, onBlur, 'aria-label': 'Номер телефона' }}
      />
    </div>
  );
}
