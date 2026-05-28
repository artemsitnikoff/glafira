export type StageKey = 'response' | 'added' | 'selected' | 'recruiter' | 'interview' | 'manager' | 'offer' | 'hired' | 'rejected';

export interface StageConfig {
  key: StageKey;
  label: string;       // русский
  color: string;       // CSS var: 'var(--stage-response)' etc
  terminal: boolean;   // hired, rejected
}

export const STAGES: Record<StageKey, StageConfig> = {
  response: { key: 'response', label: 'Отклик', color: 'var(--stage-response)', terminal: false },
  added: { key: 'added', label: 'Добавлен', color: 'var(--stage-added)', terminal: false },
  selected: { key: 'selected', label: 'Отобран', color: 'var(--stage-selected)', terminal: false },
  recruiter: { key: 'recruiter', label: 'Контакт с рекрутёром', color: 'var(--stage-recruiter)', terminal: false },
  interview: { key: 'interview', label: 'Интервью', color: 'var(--stage-interview)', terminal: false },
  manager: { key: 'manager', label: 'Контакт с менеджером', color: 'var(--stage-manager)', terminal: false },
  offer: { key: 'offer', label: 'Оффер', color: 'var(--stage-offer)', terminal: false },
  hired: { key: 'hired', label: 'Нанят', color: 'var(--stage-hired)', terminal: true },
  rejected: { key: 'rejected', label: 'Отказ', color: 'var(--stage-rejected)', terminal: true },
};

export const getStage = (key: string): StageConfig | null =>
  (STAGES as Record<string, StageConfig>)[key] ?? null;