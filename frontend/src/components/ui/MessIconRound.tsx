import { Icon, type IconName } from './Icon';

type Channel = 'telegram' | 'whatsapp' | 'hh' | 'avito' | 'max' | 'viber' | 'sms' | 'email';

const colors: Record<Channel, string> = {
  telegram: 'var(--src-tg)',
  whatsapp: 'var(--src-whatsapp)',
  hh: 'var(--src-hh)',
  avito: 'var(--src-avito)',
  max: 'var(--src-max)',
  viber: 'var(--src-viber)',
  sms: 'var(--fg-3)',
  email: 'var(--fg-3)',
};

const iconNames: Record<Channel, IconName> = {
  telegram: 'send',
  whatsapp: 'message-circle',
  hh: 'briefcase',
  avito: 'briefcase',
  max: 'briefcase',
  viber: 'message-circle',
  sms: 'message-circle',
  email: 'send',
};

interface MessIconRoundProps {
  // Строкой, т.к. источник — Candidate.messengers (нормализованный канал),
  // где помимо чат-каналов могут быть соцсети (vk/linkedin). Неизвестные —
  // деградируют в нейтральную иконку, а не ломают рендер undefined-иконкой.
  channel: string;
  size?: 'sm' | 'md' | 'lg';
}

export function MessIconRound({ channel, size = 'md' }: MessIconRoundProps) {
  const dimensions = size === 'sm' ? 20 : size === 'lg' ? 32 : 24;
  const iconSize = size === 'sm' ? 10 : size === 'lg' ? 16 : 12;

  const background = colors[channel as Channel] ?? 'var(--fg-3)';
  const iconName = iconNames[channel as Channel] ?? 'message-circle';

  return (
    <div
      style={{
        width: dimensions,
        height: dimensions,
        borderRadius: '50%',
        background,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontSize: iconSize,
        flexShrink: 0,
      }}
    >
      <Icon name={iconName} size={iconSize} />
    </div>
  );
}