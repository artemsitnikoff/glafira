type Segment = {
  id: string;
  label: string;
  count?: number;
};

type Props = {
  segments: Segment[];
  activeSegment: string;
  onSegmentChange: (segmentId: string) => void;
};

export function SegmentChips({ segments, activeSegment, onSegmentChange }: Props) {
  return (
    <div style={{
      display: 'flex',
      gap: 'var(--space-2)',
      flexWrap: 'wrap',
      marginBottom: 'var(--space-4)'
    }}>
      {segments.map((segment) => (
        <button
          key={segment.id}
          onClick={() => onSegmentChange(segment.id)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-1)',
            padding: '6px 12px',
            fontSize: '13px',
            fontWeight: 500,
            backgroundColor: activeSegment === segment.id ? 'var(--accent)' : 'var(--bg-3)',
            color: activeSegment === segment.id ? 'white' : 'var(--fg-2)',
            border: 'none',
            borderRadius: 'var(--radius-chip)',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            if (activeSegment !== segment.id) {
              e.currentTarget.style.backgroundColor = 'var(--bg-3-hover)';
            }
          }}
          onMouseLeave={(e) => {
            if (activeSegment !== segment.id) {
              e.currentTarget.style.backgroundColor = 'var(--bg-3)';
            }
          }}
        >
          <span>{segment.label}</span>
          {segment.count !== undefined && (
            <span style={{
              backgroundColor: activeSegment === segment.id ? 'rgba(255,255,255,0.2)' : 'var(--fg-4)',
              color: activeSegment === segment.id ? 'white' : 'var(--fg-2)',
              padding: '1px 6px',
              borderRadius: '10px',
              fontSize: '11px',
              fontWeight: 600,
              minWidth: '20px',
              textAlign: 'center'
            }}>
              {segment.count}
            </span>
          )}
        </button>
      ))}
    </div>
  );
}