import { useState, useEffect, useMemo } from 'react';
import { useGlafiraSettings } from '@/api/hooks/useGlafiraSettings';
import { useUpdateGlafiraSettings } from '@/api/mutations/settings';
import { FieldDot } from '../components/FieldDot';
import { Icon } from '@/components/ui/Icon';
import type { GlafiraSettingsOut } from '@/api/aliases';

type Props = {
  onDirtyChange: (dirty: boolean) => void;
  onSaveHandler: (handler: (() => Promise<void>) | null) => void;
  onDiscardHandler: (handler: (() => void) | null) => void;
};

// Static examples for tone cards (as allowed in TZ)
const TONE_OPTIONS = [
  {
    value: 'friendly',
    name: 'Дружеский',
    description: 'Неформальный, тёплый тон',
    example: 'Привет! Рассмотрел ваше резюме, очень интересный опыт. Хотелось бы побеседовать!'
  },
  {
    value: 'formal',
    name: 'Формальный',
    description: 'Официальный деловой стиль',
    example: 'Добрый день! Ваш профиль соответствует требованиям вакансии. Приглашаем на собеседование.'
  },
  {
    value: 'business',
    name: 'Деловой',
    description: 'Профессиональный и краткий',
    example: 'Здравствуйте. Вы подходите на позицию. Готовы обсудить детали?'
  }
];

const MODE_OPTIONS = [
  { value: 'A', label: 'Режим A', description: 'Автоматический скрининг' },
  { value: 'B', label: 'Режим B', description: 'Полуавтоматический' },
  { value: 'C', label: 'Режим C', description: 'Ручное управление' },
];

export function GlafiraTab({ onDirtyChange, onSaveHandler, onDiscardHandler }: Props) {
  const { data: settings, isLoading } = useGlafiraSettings();
  const updateSettings = useUpdateGlafiraSettings();

  const [formData, setFormData] = useState<Partial<GlafiraSettingsOut>>({});
  const [newStopWord, setNewStopWord] = useState('');

  // Initialize form with settings data
  useEffect(() => {
    if (settings) {
      setFormData(settings);
    }
  }, [settings]);

  // Check if form is dirty
  const isDirty = useMemo(() => {
    if (!settings) return false;

    return Object.keys(formData).some((key) => {
      const settingsKey = key as keyof GlafiraSettingsOut;
      if (key === 'stop_words') {
        return JSON.stringify(formData[settingsKey]) !== JSON.stringify(settings[settingsKey]);
      }
      return formData[settingsKey] !== settings[settingsKey];
    });
  }, [formData, settings]);

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  const handleSave = async () => {
    if (isDirty && settings) {
      const updates: Record<string, any> = {};
      Object.keys(formData).forEach((key) => {
        const settingsKey = key as keyof GlafiraSettingsOut;
        if (key === 'stop_words') {
          if (JSON.stringify(formData[settingsKey]) !== JSON.stringify(settings[settingsKey])) {
            updates[key] = formData[settingsKey];
          }
        } else if (formData[settingsKey] !== settings[settingsKey]) {
          updates[key] = formData[settingsKey];
        }
      });

      if (Object.keys(updates).length > 0) {
        await updateSettings.mutateAsync(updates);
      }
    }
  };

  const handleDiscard = () => {
    if (settings) {
      setFormData(settings);
    }
  };

  useEffect(() => {
    onSaveHandler(handleSave);
    onDiscardHandler(handleDiscard);
  }, [formData, settings, onSaveHandler, onDiscardHandler]);

  const updateField = (field: keyof GlafiraSettingsOut, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const isFieldDirty = (field: keyof GlafiraSettingsOut) => {
    if (!settings) return false;
    if (field === 'stop_words') {
      return JSON.stringify(formData[field]) !== JSON.stringify(settings[field]);
    }
    return formData[field] !== settings[field];
  };

  const handleAddStopWord = () => {
    if (newStopWord.trim()) {
      const currentStopWords = (formData.stop_words as Record<string, boolean>) || {};
      updateField('stop_words', {
        ...currentStopWords,
        [newStopWord.trim()]: true
      });
      setNewStopWord('');
    }
  };

  const handleRemoveStopWord = (word: string) => {
    const currentStopWords = (formData.stop_words as Record<string, boolean>) || {};
    const newStopWords = { ...currentStopWords };
    delete newStopWords[word];
    updateField('stop_words', newStopWords);
  };

  const stopWordsArray = formData.stop_words
    ? Object.keys(formData.stop_words as Record<string, boolean>)
    : [];

  if (isLoading) {
    return <div className="settings-loading">Загрузка...</div>;
  }

  return (
    <div className="settings-content-inner">
      {/* Tone Settings */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Голос и тон</h2>
          <p className="settings-card-desc">Настройка стиля общения Глафиры с кандидатами</p>
        </div>
        <div className="settings-card-body">
          <div className="form-field">
            <label className="form-label">
              <FieldDot dirty={isFieldDirty('tone')} />
              Тон общения
            </label>
            <div className="tone-cards">
              {TONE_OPTIONS.map((tone) => (
                <label key={tone.value} className={`tone-card ${formData.tone === tone.value ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="tone"
                    value={tone.value}
                    checked={formData.tone === tone.value}
                    onChange={(e) => updateField('tone', e.target.value)}
                  />
                  <div className="tone-card-header">
                    <h3 className="tone-name">{tone.name}</h3>
                    <p className="tone-description">{tone.description}</p>
                  </div>
                  <div className="tone-example">{tone.example}</div>
                </label>
              ))}
            </div>
          </div>

          <div className="form-row">
            <div className="form-field">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('use_informal')} />
                Обращение
              </label>
              <div className="toggle-group">
                <label className="toggle-item">
                  <input
                    type="radio"
                    name="use_informal"
                    checked={!formData.use_informal}
                    onChange={() => updateField('use_informal', false)}
                  />
                  <span>На «Вы»</span>
                </label>
                <label className="toggle-item">
                  <input
                    type="radio"
                    name="use_informal"
                    checked={formData.use_informal}
                    onChange={() => updateField('use_informal', true)}
                  />
                  <span>На «ты»</span>
                </label>
              </div>
            </div>

            <div className="form-field">
              <label className="form-label">
                <FieldDot dirty={isFieldDirty('emoji_level')} />
                Использование эмодзи
              </label>
              <select
                className="form-select"
                value={formData.emoji_level || 'none'}
                onChange={(e) => updateField('emoji_level', e.target.value)}
              >
                <option value="none">Без эмодзи</option>
                <option value="moderate">Умеренно</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Auto-actions */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Правила автодействий</h2>
          <p className="settings-card-desc">Настройка автоматических действий на основе AI-скоринга</p>
        </div>
        <div className="settings-card-body">
          <div className="auto-rules">
            <div className="auto-rule">
              <div className="auto-rule-text">
                <span>Если AI-скоринг менее чем</span>
                <div className="auto-rule-value">
                  <FieldDot dirty={isFieldDirty('auto_reject_below')} />
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={formData.auto_reject_below || 0}
                    onChange={(e) => updateField('auto_reject_below', parseInt(e.target.value))}
                    className="range-slider"
                  />
                  <span className="range-value">{formData.auto_reject_below || 0}</span>
                </div>
                <span>→ Отклонить автоматически</span>
              </div>
            </div>

            <div className="auto-rule">
              <div className="auto-rule-text">
                <span>Если AI-скоринг более чем</span>
                <div className="auto-rule-value">
                  <FieldDot dirty={isFieldDirty('auto_select_above')} />
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={formData.auto_select_above || 100}
                    onChange={(e) => updateField('auto_select_above', parseInt(e.target.value))}
                    className="range-slider"
                  />
                  <span className="range-value">{formData.auto_select_above || 100}</span>
                </div>
                <span>→ Автоматически отобрать</span>
              </div>
            </div>

            <div className="auto-rule">
              <div className="auto-rule-text">
                <span>Если</span>
                <div className="auto-rule-value">
                  <FieldDot dirty={isFieldDirty('days_no_response')} />
                  <input
                    type="range"
                    min="1"
                    max="30"
                    value={formData.days_no_response || 7}
                    onChange={(e) => updateField('days_no_response', parseInt(e.target.value))}
                    className="range-slider"
                  />
                  <span className="range-value">{formData.days_no_response || 7}</span>
                </div>
                <span>дней нет ответа → Закрыть «Не вышел на связь»</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Stop Words */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Стоп-слова</h2>
          <p className="settings-card-desc">Слова и фразы, при наличии которых кандидат автоматически отклоняется</p>
        </div>
        <div className="settings-card-body">
          <div className="form-field">
            <label className="form-label">
              <FieldDot dirty={isFieldDirty('stop_words')} />
              Список стоп-слов
            </label>
            <div className="stop-words-container">
              <div className="stop-words-list">
                {stopWordsArray.map((word) => (
                  <span key={word} className="stop-word-chip">
                    {word}
                    <button
                      type="button"
                      onClick={() => handleRemoveStopWord(word)}
                      className="stop-word-remove"
                    >
                      <Icon name="x" size={12} />
                    </button>
                  </span>
                ))}
              </div>
              <div className="stop-words-input">
                <input
                  type="text"
                  className="form-input"
                  placeholder="Введите стоп-слово"
                  value={newStopWord}
                  onChange={(e) => setNewStopWord(e.target.value)}
                  onKeyPress={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddStopWord();
                    }
                  }}
                />
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={handleAddStopWord}
                  disabled={!newStopWord.trim()}
                >
                  Добавить
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Default Mode */}
      <div className="settings-card">
        <div className="settings-card-header">
          <h2 className="settings-card-title">Режим по умолчанию</h2>
          <p className="settings-card-desc">Режим работы Глафиры для новых вакансий</p>
        </div>
        <div className="settings-card-body">
          <div className="form-field">
            <label className="form-label">
              <FieldDot dirty={isFieldDirty('default_mode')} />
              Режим
            </label>
            <div className="mode-cards">
              {MODE_OPTIONS.map((mode) => (
                <label key={mode.value} className={`mode-card ${formData.default_mode === mode.value ? 'selected' : ''}`}>
                  <input
                    type="radio"
                    name="default_mode"
                    value={mode.value}
                    checked={formData.default_mode === mode.value}
                    onChange={(e) => updateField('default_mode', e.target.value)}
                  />
                  <div className="mode-card-content">
                    <h3 className="mode-label">{mode.label}</h3>
                    <p className="mode-description">{mode.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}