export interface SourceConfig {
  label: string;
  color: string;
}

export const SOURCE_CONFIG: Record<string, SourceConfig> = {
  hh: { label: 'hh.ru', color: 'var(--src-hh)' },
  avito: { label: 'Авито Работа', color: 'var(--src-avito)' },
  telegram: { label: 'Telegram-бот Глафиры', color: 'var(--src-tg)' },
  referral: { label: 'Рефералы', color: 'var(--stage-added)' },
  direct: { label: 'Прямые отклики', color: 'var(--stage-recruiter)' },
  agency: { label: 'Агентства', color: 'var(--stage-manager)' },
  import: { label: 'Импорт', color: 'var(--fg-2)' },
  manual: { label: 'Вручную', color: 'var(--fg-3)' },
  other: { label: 'Прочее', color: 'var(--fg-3)' },
};