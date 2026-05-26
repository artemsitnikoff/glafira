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
  channel: Channel;
  size?: 'sm' | 'md' | 'lg';
}

export function MessIconRound({ channel, size = 'md' }: MessIconRoundProps) {
  const dimensions = size === 'sm' ? 20 : size === 'lg' ? 32 : 24;
  const iconSize = size === 'sm' ? 10 : size === 'lg' ? 16 : 12;

  return (
    <div
      style={{
        width: dimensions,
        height: dimensions,
        borderRadius: '50%',
        background: colors[channel],
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontSize: iconSize,
        flexShrink: 0,
      }}
    >
      <Icon name={iconNames[channel]} size={iconSize} />
    </div>
  );
}