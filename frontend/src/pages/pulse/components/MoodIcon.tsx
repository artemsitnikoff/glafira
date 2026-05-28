type Props = {
  mood: number | null | undefined;
};

export function MoodIcon({ mood }: Props) {
  if (!mood) return <span style={{ color: 'var(--fg-3)' }}>—</span>;

  // Mood маппинг согласно ТЗ:
  // < 2.5 → 👎
  // 2.5 ≤ mood ≤ 3.5 → 😐
  // > 3.5 → 👍

  if (mood < 2.5) return <span>👎</span>;
  if (mood <= 3.5) return <span>😐</span>;
  return <span>👍</span>;
}