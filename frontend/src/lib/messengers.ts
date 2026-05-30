// Поле Candidate.messengers исторически двухформатное:
//  • засиженные/старые кандидаты — список строк-каналов: ["telegram","whatsapp","max"]
//  • новые из формы добавления — объекты соцсетей: [{type:"tg",url:"https://t.me/x"}]
// Эти хелперы приводят обе формы к единому виду для отображения.

export type MessengerEntry = string | { type?: string; url?: string };

// Словарь формы соцсетей (tg/wa/in) → канонический канал для иконок/бейджей.
// max/vk/linkedin/telegram/whatsapp совпадают и остаются как есть.
const TYPE_TO_CHANNEL: Record<string, string> = {
  tg: 'telegram',
  wa: 'whatsapp',
  in: 'linkedin',
};

/** Канонический строковый канал из записи мессенджера (строка ИЛИ объект). */
export function messengerChannel(m: MessengerEntry): string {
  const t = typeof m === 'string' ? m : (m?.type ?? '');
  return TYPE_TO_CHANNEL[t] ?? t;
}

/** URL соцсети, если запись объектная (у строковых каналов URL нет). */
export function messengerUrl(m: MessengerEntry): string | undefined {
  return typeof m === 'string' ? undefined : m?.url;
}
