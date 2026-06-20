export interface SourceConfig {
  label: string;
  color: string;
}

export const SOURCE_CONFIG: Record<string, SourceConfig> = {
  hh: { label: 'hh.ru', color: 'var(--src-hh)' },
  avito: { label: 'Авито Работа', color: 'var(--src-avito)' },
  superjob: { label: 'SuperJob', color: 'var(--ark-yellow-600)' },
  linkedin: { label: 'LinkedIn', color: 'var(--ark-blue-700)' },
  telegram: { label: 'Telegram-бот Глафиры', color: 'var(--src-tg)' },
  potok: { label: 'Поток', color: 'var(--ark-violet-500)' },
  smart: { label: 'Умный подбор', color: 'var(--ark-violet-500)' },
  habr: { label: 'Хабр Карьера', color: 'var(--ark-gray-600)' },
  referral: { label: 'Рефералы', color: 'var(--stage-added)' },
  direct: { label: 'Прямые отклики', color: 'var(--stage-recruiter)' },
  agency: { label: 'Агентства', color: 'var(--stage-manager)' },
  import: { label: 'Импорт', color: 'var(--fg-2)' },
  manual: { label: 'Вручную', color: 'var(--fg-3)' },
  other: { label: 'Прочее', color: 'var(--fg-3)' },
};