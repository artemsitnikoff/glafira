import {
  Home,
  Briefcase,
  Users,
  Activity,
  BarChart3,
  Settings,
  Search,
  Plus,
  Archive,
  Bell,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  Send,
  X,
  Check,
  MessageCircle,
  Flag,
  AlertTriangle,
  Clock,
  RefreshCw,
  Bookmark,
  Filter,
  ArrowRight,
  ExternalLink,
  Funnel,
  Sparkles,
  MoreHorizontal,
  Pause,
  Calendar,
} from 'lucide-react';

const iconMap = {
  home: Home,
  briefcase: Briefcase,
  users: Users,
  activity: Activity,
  'bar-chart': BarChart3,
  settings: Settings,
  search: Search,
  plus: Plus,
  archive: Archive,
  bell: Bell,
  'chevron-down': ChevronDown,
  'chevron-right': ChevronRight,
  'chevron-left': ChevronLeft,
  send: Send,
  x: X,
  check: Check,
  'message-circle': MessageCircle,
  flag: Flag,
  'alert-triangle': AlertTriangle,
  clock: Clock,
  refresh: RefreshCw,
  bookmark: Bookmark,
  filter: Filter,
  'arrow-right': ArrowRight,
  open: ExternalLink,
  funnel: Funnel,
  sparkle: Sparkles,
  more: MoreHorizontal,
  pause: Pause,
  'cal-clock': Calendar,
  // Для совместимости с prototype
  chart: BarChart3,
  chevD: ChevronDown,
  chevR: ChevronRight,
  chevL: ChevronLeft,
  arrowRight: ArrowRight,
  calClock: Calendar,
  heart: Activity, // Пульс-Онбординг → Activity (Pulse icon)
} as const;

export type IconName = keyof typeof iconMap;

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
  color?: string;
  style?: React.CSSProperties;
}

export function Icon({ name, size = 20, className, color, style }: IconProps) {
  const IconComponent = iconMap[name];
  if (!IconComponent) {
    console.warn(`Icon "${name}" not found in iconMap`);
    return null;
  }

  return (
    <IconComponent
      size={size}
      className={className}
      color={color}
      style={style}
    />
  );
}