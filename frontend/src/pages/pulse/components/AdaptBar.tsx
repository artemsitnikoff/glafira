type Props = {
  adaptDay: number;
  probationDays: number;
  riskLevel: string;
  variant?: 'compact' | 'large';
};

export function AdaptBar({ adaptDay, probationDays, riskLevel, variant = 'compact' }: Props) {
  const progress = Math.min(100, (adaptDay / probationDays) * 100);

  // Цвет полосы на основе риска
  const riskColors = {
    low: 'var(--risk-low)',
    mid: 'var(--risk-mid)',
    high: 'var(--risk-high)',
  };

  const barColor = riskColors[riskLevel as keyof typeof riskColors] || riskColors.low;
  const height = variant === 'large' ? '12px' : '6px';
  const radius = variant === 'large' ? '6px' : '3px';

  if (variant === 'large') {
    // Большая версия с подписями фаз и метками событий
    const phases = [
      { label: 'Welcome', end: 7 },
      { label: 'Месяц 1', end: 30 },
      { label: 'Месяц 2', end: 60 },
      { label: 'Месяц 3', end: 90 },
    ];

    return (
      <div style={{ marginTop: 'var(--space-4)' }}>
        {/* Подписи фаз */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 'var(--space-2)', fontSize: '11px', color: 'var(--fg-3)' }}>
          {phases.map((phase, index) => (
            <div key={index} style={{ textAlign: index === 0 ? 'left' : index === phases.length - 1 ? 'right' : 'center' }}>
              {phase.label}
            </div>
          ))}
        </div>

        {/* Полоса прогресса */}
        <div style={{ position: 'relative' }}>
          <div
            style={{
              width: '100%',
              height,
              backgroundColor: 'var(--bg-3)',
              borderRadius: radius,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: '100%',
                backgroundColor: barColor,
                borderRadius: radius,
                transition: 'width 0.3s ease',
              }}
            />
          </div>

          {/* Маркер текущей позиции */}
          <div
            style={{
              position: 'absolute',
              left: `${progress}%`,
              top: '50%',
              transform: 'translate(-50%, -50%)',
              width: '16px',
              height: '16px',
              backgroundColor: barColor,
              border: '2px solid white',
              borderRadius: '50%',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
            }}
          />
        </div>

        {/* День N из M */}
        <div style={{ textAlign: 'center', marginTop: 'var(--space-2)', fontSize: '12px', color: 'var(--fg-2)' }}>
          День {adaptDay} из {probationDays}
        </div>
      </div>
    );
  }

  // Компактная версия для таблицы
  return (
    <div style={{ width: '80px' }}>
      <div
        style={{
          width: '100%',
          height,
          backgroundColor: 'var(--bg-3)',
          borderRadius: radius,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${progress}%`,
            height: '100%',
            backgroundColor: barColor,
            borderRadius: radius,
            transition: 'width 0.3s ease',
          }}
        />
      </div>
    </div>
  );
}