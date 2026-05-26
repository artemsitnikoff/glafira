import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCreateCandidate } from '@/api/mutations/candidates';
import type { components } from '@/api/types';

type CandidateCreate = components['schemas']['CandidateCreate'];

type Props = {
  vacancyId: string;
  onClose: () => void;
};

const SOURCES = [
  { id: 'hh', name: 'HeadHunter' },
  { id: 'avito', name: 'Avito Работа' },
  { id: 'superjob', name: 'SuperJob' },
  { id: 'telegram', name: 'Telegram-канал' },
  { id: 'referral', name: 'Реферальная программа' },
  { id: 'direct', name: 'Прямой контакт' },
  { id: 'agency', name: 'Кадровое агентство' },
  { id: 'other', name: 'Другое' },
];

const ADD_TYPES = [
  { id: 'manual', name: 'Ручное добавление' },
  { id: 'resume', name: 'Из резюме' },
  { id: 'pool', name: 'Из общей базы' },
  { id: 'hh_link', name: 'По ссылке HH' },
];

export default function NewCandidateModal({ vacancyId, onClose }: Props) {
  const createMutation = useCreateCandidate(vacancyId);
  const [formData, setFormData] = useState<CandidateCreate>({
    last_name: '',
    first_name: '',
    middle_name: null,
    source: '',
    phone: null,
    email: null,
    gender: null,
    birth_date: null,
    city: null,
    salary_expectation: null,
    currency: 'RUB',
    add_type: 'manual',
    vacancy_id: vacancyId,
    comment: null,
  });

  const [errors, setErrors] = useState<Record<string, string>>({});

  const isValid = formData.last_name.trim() && formData.first_name.trim() && formData.source;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isValid) return;

    try {
      await createMutation.mutateAsync(formData);
      onClose();
    } catch (error: any) {
      if (error.response?.status === 422) {
        // Validation errors
        const details = error.response?.data?.details || [];
        const fieldErrors: Record<string, string> = {};
        details.forEach((detail: any) => {
          if (detail.field) {
            fieldErrors[detail.field] = detail.message;
          }
        });
        setErrors(fieldErrors);
      } else {
        console.error('Failed to create candidate:', error);
        setErrors({ general: error.response?.data?.message || 'Произошла ошибка' });
      }
    }
  };

  const updateFormData = (updates: Partial<CandidateCreate>) => {
    setFormData(prev => ({ ...prev, ...updates }));
    // Clear errors for updated fields
    Object.keys(updates).forEach(key => {
      if (errors[key]) {
        setErrors(prev => ({ ...prev, [key]: '' }));
      }
    });
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Добавить кандидата</h2>
          <button className="modal-close" onClick={onClose}>
            <Icon name="x" size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          {errors.general && (
            <div className="error-banner">{errors.general}</div>
          )}

          {/* Source */}
          <div className="nv-field">
            <label className="nv-label">
              Источник <span className="nv-req">*</span>
              <span className="nv-mute"> · откуда узнали о кандидате</span>
            </label>
            <select
              className={`nv-input ${errors.source ? 'error' : ''}`}
              value={formData.source}
              onChange={e => updateFormData({ source: e.target.value })}
              required
            >
              <option value="">Выберите источник…</option>
              {SOURCES.map(source => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
            {errors.source && <div className="field-error">{errors.source}</div>}
          </div>

          {/* Name */}
          <div className="nv-grid-3">
            <div className="nv-field">
              <label className="nv-label">
                Фамилия <span className="nv-req">*</span>
              </label>
              <input
                className={`nv-input ${errors.last_name ? 'error' : ''}`}
                value={formData.last_name}
                onChange={e => updateFormData({ last_name: e.target.value })}
                required
              />
              {errors.last_name && <div className="field-error">{errors.last_name}</div>}
            </div>

            <div className="nv-field">
              <label className="nv-label">
                Имя <span className="nv-req">*</span>
              </label>
              <input
                className={`nv-input ${errors.first_name ? 'error' : ''}`}
                value={formData.first_name}
                onChange={e => updateFormData({ first_name: e.target.value })}
                required
              />
              {errors.first_name && <div className="field-error">{errors.first_name}</div>}
            </div>

            <div className="nv-field">
              <label className="nv-label">Отчество</label>
              <input
                className="nv-input"
                value={formData.middle_name || ''}
                onChange={e => updateFormData({ middle_name: e.target.value || null })}
              />
            </div>
          </div>

          {/* Contact */}
          <div className="nv-grid-2">
            <div className="nv-field">
              <label className="nv-label">Телефон</label>
              <input
                className="nv-input"
                type="tel"
                placeholder="+7 (___) ___-__-__"
                value={formData.phone || ''}
                onChange={e => updateFormData({ phone: e.target.value || null })}
              />
            </div>

            <div className="nv-field">
              <label className="nv-label">E-mail</label>
              <input
                className="nv-input"
                type="email"
                placeholder="name@example.com"
                value={formData.email || ''}
                onChange={e => updateFormData({ email: e.target.value || null })}
              />
            </div>
          </div>

          {/* Personal info */}
          <div className="nv-grid-3">
            <div className="nv-field">
              <label className="nv-label">Пол</label>
              <select
                className="nv-input"
                value={formData.gender || ''}
                onChange={e => updateFormData({ gender: e.target.value || null })}
              >
                <option value="">Не указан</option>
                <option value="female">Женский</option>
                <option value="male">Мужской</option>
              </select>
            </div>

            <div className="nv-field">
              <label className="nv-label">Дата рождения</label>
              <input
                className="nv-input"
                type="date"
                value={formData.birth_date || ''}
                onChange={e => updateFormData({ birth_date: e.target.value || null })}
              />
            </div>

            <div className="nv-field">
              <label className="nv-label">Город проживания</label>
              <input
                className="nv-input"
                placeholder="Введите название"
                value={formData.city || ''}
                onChange={e => updateFormData({ city: e.target.value || null })}
              />
            </div>
          </div>

          {/* Salary and type */}
          <div className="nv-grid-2">
            <div className="nv-field">
              <label className="nv-label">Ожидаемая ЗП</label>
              <div className="salary-input">
                <input
                  className="nv-input"
                  type="number"
                  placeholder="0"
                  value={formData.salary_expectation || ''}
                  onChange={e =>
                    updateFormData({ salary_expectation: Number(e.target.value) || null })
                  }
                />
                <select
                  className="nv-input currency-select"
                  value={formData.currency}
                  onChange={e => updateFormData({ currency: e.target.value })}
                >
                  <option value="RUB">руб.</option>
                  <option value="USD">$</option>
                  <option value="EUR">€</option>
                </select>
              </div>
            </div>

            <div className="nv-field">
              <label className="nv-label">Тип добавления</label>
              <select
                className="nv-input"
                value={formData.add_type}
                onChange={e => updateFormData({ add_type: e.target.value })}
              >
                {ADD_TYPES.map(type => (
                  <option key={type.id} value={type.id}>
                    {type.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Comment */}
          <div className="nv-field">
            <label className="nv-label">Комментарий</label>
            <textarea
              className="nv-textarea"
              rows={3}
              placeholder="Заметка для команды — что обсудили, какой стек, причина обращения…"
              value={formData.comment || ''}
              onChange={e => updateFormData({ comment: e.target.value || null })}
            />
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              Отмена
            </button>
            <button
              type="submit"
              className={`btn btn-primary ${!isValid ? 'is-disabled' : ''}`}
              disabled={!isValid || createMutation.isPending}
            >
              {createMutation.isPending ? 'Добавление...' : 'Добавить кандидата'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}