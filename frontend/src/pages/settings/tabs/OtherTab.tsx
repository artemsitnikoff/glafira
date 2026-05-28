import { useState, useEffect } from 'react';
import { Icon } from '@/components/ui/Icon';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

const DATE_FORMATS = [
  { value: 'dd.mm.yyyy', label: '28.05.2026', example: '28.05.2026' },
  { value: 'yyyy-mm-dd', label: '2026-05-28', example: '2026-05-28' },
  { value: 'dd mmm yyyy', label: '28 May 2026', example: '28 мая 2026' },
];

export function OtherTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const [dateFormat, setDateFormat] = useState('dd.mm.yyyy');

  // OtherTab doesn't have persistent dirty state for now
  useEffect(() => {
    onDirtyChange(false);
    onSaveHandler(null);
    onDiscardHandler(null);
  }, [onDirtyChange, onSaveHandler, onDiscardHandler]);

  return (
    <div className="settings-content-inner">
      {/* General Settings */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Общие настройки</h2>
          <p className="settings-card-desc">Язык интерфейса, формат отображения данных</p>
        </div>
        <div className="settings-card-body">
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label">Язык интерфейса</label>
              <select className="form-select" value="ru" disabled>
                <option value="ru">Русский</option>
              </select>
              <div className="form-help">
                Дополнительные языки будут добавлены в следующих версиях
              </div>
            </div>

            <div className="form-field">
              <label className="form-label">Формат даты</label>
              <select
                className="form-select"
                value={dateFormat}
                onChange={(e) => setDateFormat(e.target.value)}
              >
                {DATE_FORMATS.map((format) => (
                  <option key={format.value} value={format.value}>
                    {format.label}
                  </option>
                ))}
              </select>
              <div className="form-help">
                Пример: {DATE_FORMATS.find(f => f.value === dateFormat)?.example}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* API & Webhooks */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">API и Webhooks</h2>
          <p className="settings-card-desc">Настройка интеграций через API и веб-хуки</p>
        </div>
        <div className="settings-card-body">
          {/* TODO: API/Webhooks — заглушка по ТЗ §3.8, помеченная TODO; показывай блок с заголовком «Webhooks» и текстом «Функция в разработке» (это разрешено) */}
          <div className="empty-state">
            <Icon name="link" size={48} />
            <h3>Webhooks</h3>
            <p>Функция в разработке</p>
            {/* TODO: Implement webhooks configuration when backend provides endpoints */}
          </div>
        </div>
      </div>
    </div>
  );
}