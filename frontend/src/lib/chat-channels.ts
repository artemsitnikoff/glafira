/**
 * Справочник каналов чата (ОТОБРАЖЕНИЕ). Единый источник цвета/названия канала
 * для селектора ответа во вкладке «Чат» (ChatTab) и точки канала в мете сообщения
 * (общий ChatThread, флаг showChannel).
 *
 * id = значение Message.channel в БД (CHECK: telegram|hh|whatsapp|max|sms|email).
 * Цвета — фирменные цвета логотипов мессенджеров (бренд-идентика, инлайн-hex как в
 * эталоне project/), НЕ палитра-токены темы. Реально ОТПРАВЛЯЕМЫЕ каналы —
 * только те, что вернул useChatMeta().available_channels (подмножество
 * ['telegram','hh']); остальные значения встречаются лишь в ИСТОРИИ переписки
 * (например email-оффер) и нужны только чтобы нарисовать чип канала у сообщения.
 */
export type ChannelMeta = { id: string; label: string; color: string };

export const CHANNELS: ChannelMeta[] = [
  { id: 'telegram', label: 'Telegram', color: '#229ED9' },
  { id: 'hh', label: 'hh.ru', color: '#D6001C' },
  { id: 'email', label: 'E-mail', color: '#5B6573' },
  { id: 'max', label: 'Max', color: '#0077FF' },
  { id: 'whatsapp', label: 'WhatsApp', color: '#25D366' },
  { id: 'sms', label: 'SMS', color: '#7A7F87' },
];

export function channelMeta(id?: string | null): ChannelMeta {
  return (
    CHANNELS.find((c) => c.id === id) ?? { id: id ?? 'telegram', label: id ?? 'Канал', color: '#7A7F87' }
  );
}
