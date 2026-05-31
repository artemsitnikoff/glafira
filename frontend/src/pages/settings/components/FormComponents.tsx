import { Icon } from '@/components/ui/Icon';
import type { ReactNode } from 'react';

// Form primitives from reference

type FormRowProps = {
  label?: string;
  hint?: string;
  required?: boolean;
  children: ReactNode;
  span?: number;
};

export function FormRow({ label, hint, required, children, span }: FormRowProps) {
  return (
    <div className={`fld ${span === 2 ? 'fld-span2' : ''}`}>
      {label && (
        <label className="fld-lbl">
          {label}
          {required && <span className="req">*</span>}
        </label>
      )}
      <div className="fld-ctrl">{children}</div>
      {hint && <div className="fld-hint">{hint}</div>}
    </div>
  );
}

type TextInputProps = {
  value?: string;
  placeholder?: string;
  onChange?: (value: string) => void;
  type?: string;
  mono?: boolean;
  suffix?: string;
  locked?: boolean;
};

export function TextInput({ value, placeholder, onChange, type = 'text', mono, suffix, locked }: TextInputProps) {
  return (
    <div className={`txt ${mono ? 'txt-mono' : ''} ${locked ? 'txt-locked' : ''}`}>
      <input
        type={type}
        value={value ?? ''}
        placeholder={placeholder}
        onChange={e => onChange && onChange(e.target.value)}
        readOnly={locked}
      />
      {suffix && <span className="txt-suffix">{suffix}</span>}
    </div>
  );
}

type TextareaProps = {
  value?: string;
  placeholder?: string;
  rows?: number;
  onChange?: (value: string) => void;
};

export function Textarea({ value, placeholder, rows = 3, onChange }: TextareaProps) {
  return (
    <textarea
      className="txt-area"
      rows={rows}
      value={value ?? ''}
      placeholder={placeholder}
      onChange={e => onChange && onChange(e.target.value)}
    />
  );
}

type SelectOption = {
  value: string;
  label: string;
} | string;

type SelectProps = {
  value?: string;
  options: SelectOption[];
  onChange?: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
};

export function Select({ value, options, onChange, placeholder, disabled }: SelectProps) {
  return (
    <div className="sel">
      <select
        value={value ?? ''}
        onChange={e => onChange && onChange(e.target.value)}
        disabled={disabled}
      >
        {placeholder && <option value="" disabled>{placeholder}</option>}
        {options.map(o => {
          const val = typeof o === 'string' ? o : o.value;
          const label = typeof o === 'string' ? o : o.label;
          return <option key={val} value={val}>{label}</option>;
        })}
      </select>
      <Icon name="chevD" size={14}/>
    </div>
  );
}

type SwitchProps = {
  value?: boolean;
  onChange?: (value: boolean) => void;
  label?: string;
  desc?: string;
  disabled?: boolean;
};

export function Switch({ value, onChange, label, desc, disabled }: SwitchProps) {
  return (
    <label className="sw-row">
      <button
        type="button"
        className={`sw ${value ? 'on' : ''}`}
        onClick={() => !disabled && onChange && onChange(!value)}
        aria-pressed={!!value}
        disabled={disabled}
      >
        <span className="sw-knob"/>
      </button>
      <div className="sw-text">
        {label && <div className="sw-label">{label}</div>}
        {desc && <div className="sw-desc">{desc}</div>}
      </div>
    </label>
  );
}

type RadioProps = {
  checked?: boolean;
  onChange?: () => void;
  label: string;
  desc?: string;
  right?: ReactNode;
  disabled?: boolean;
};

export function Radio({ checked, onChange, label, desc, right, disabled }: RadioProps) {
  return (
    <label
      className={`rd-row ${checked ? 'on' : ''} ${disabled ? 'disabled' : ''}`}
      onClick={() => !disabled && onChange && onChange()}
    >
      <span className={`rd ${checked ? 'on' : ''}`}><span/></span>
      <div className="rd-text">
        <div className="rd-label">{label}</div>
        {desc && <div className="rd-desc">{desc}</div>}
      </div>
      {right}
    </label>
  );
}

type PageHeadProps = {
  title: string;
  subtitle?: string;
  dirty?: boolean;
  onSave?: () => void;
  onDiscard?: () => void;
  saving?: boolean;
};

export function PageHead({ title, subtitle, dirty, onSave, onDiscard, saving }: PageHeadProps) {
  return (
    <div className="set-page-head">
      <div>
        <h1 className="set-h1">{title}</h1>
        {subtitle && <div className="set-sub">{subtitle}</div>}
      </div>
      <div className="set-head-actions">
        {dirty && <span className="dirty-pill">Есть несохранённые изменения</span>}
        {onDiscard && dirty && (
          <button className="btn btn-secondary" disabled={saving} onClick={onDiscard}>
            Отменить
          </button>
        )}
        <button
          className={`btn ${dirty ? 'btn-primary' : 'btn-secondary'}`}
          disabled={!dirty || saving}
          onClick={onSave}
        >
          {saving ? 'Сохранение…' : 'Сохранить изменения'}
        </button>
      </div>
    </div>
  );
}

type CardProps = {
  title?: string;
  desc?: string;
  children: ReactNode;
  foot?: ReactNode;
};

export function Card({ title, desc, children, foot }: CardProps) {
  return (
    <section className="set-card">
      {(title || desc) && (
        <header className="set-card-head">
          {title && <div className="set-card-title">{title}</div>}
          {desc && <div className="set-card-desc">{desc}</div>}
        </header>
      )}
      <div className="set-card-body">{children}</div>
      {foot && <footer className="set-card-foot">{foot}</footer>}
    </section>
  );
}