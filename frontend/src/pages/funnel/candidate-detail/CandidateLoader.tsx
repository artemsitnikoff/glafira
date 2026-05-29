export function CandidateLoader() {
  return (
    <div className="candidate-detail__loader">
      <div className="cd-dancer" style={{
        fontSize: '76px',
        lineHeight: 1,
        marginBottom: '16px',
        animation: 'dancerBounce 1.2s ease-in-out infinite'
      }}>
        💃
      </div>
      <p style={{ margin: '0 0 8px', color: 'var(--fg-1)', fontSize: '15px', fontWeight: '500' }}>
        Глафира собирает профиль
      </p>
      <div className="cd-load-dots" style={{
        display: 'flex',
        gap: '4px',
        justifyContent: 'center'
      }}>
        {[0, 1, 2].map(i => (
          <div
            key={i}
            style={{
              width: '6px',
              height: '6px',
              background: 'var(--fg-3)',
              borderRadius: '50%',
              animation: `dotBounce 1.4s ease-in-out infinite`,
              animationDelay: `${i * 0.16}s`
            }}
          />
        ))}
      </div>
    </div>
  );
}