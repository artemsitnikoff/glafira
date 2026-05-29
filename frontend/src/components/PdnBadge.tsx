interface PdnBadgeProps {
  size?: 'sm' | 'md' | 'lg';
}

export function PdnBadge({ size = 'md' }: PdnBadgeProps) {
  const sizes = {
    sm: { fontSize: '10px', padding: '2px 6px', iconSize: 8 },
    md: { fontSize: '12px', padding: '3px 8px', iconSize: 10 },
    lg: { fontSize: '13px', padding: '4px 10px', iconSize: 11 }
  };

  const config = sizes[size];

  return (
    <span
      className={`pdn-badge pdn-${size}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        padding: config.padding,
        background: '#E8F4EC',
        color: '#16A34A',
        fontSize: config.fontSize,
        fontWeight: 600,
        borderRadius: '6px'
      }}
      title="Согласие на обработку персональных данных подписано"
    >
      <svg width={config.iconSize} height={config.iconSize} viewBox="0 0 12 12" fill="none">
        <path d="M2.5 6.2l2.4 2.4L9.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
      ПдН
    </span>
  );
}