const PALETTE = [
  '#F2A2A2', '#A2E8A3', '#A2C8F2', '#F2C2A2',
  '#C2A2F2', '#A2F2E8', '#F2E8A2', '#E8A2F2'
];

function hashName(s: string): number {
  let h = 0;
  for (const ch of s) {
    h = (h * 31 + (ch.codePointAt(0) ?? 0)) | 0;
  }
  return Math.abs(h);
}

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0][0]?.toUpperCase() ?? '?';
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

interface AvatarProps {
  name: string;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  src?: string | null;
}

export function Avatar({ name, size = 'md', src }: AvatarProps) {
  const px = size === 'xs' ? 16 : size === 'sm' ? 22 : size === 'lg' ? 64 : 28;
  const bg = PALETTE[hashName(name) % PALETTE.length];

  if (src) {
    return (
      <img
        src={src}
        alt={name}
        style={{
          width: px,
          height: px,
          borderRadius: '50%',
          objectFit: 'cover'
        }}
      />
    );
  }

  return (
    <div
      style={{
        width: px,
        height: px,
        borderRadius: '50%',
        background: bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        fontWeight: 600,
        fontSize: px * 0.4
      }}
    >
      {initials(name)}
    </div>
  );
}