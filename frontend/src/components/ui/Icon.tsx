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
  ChevronUp,
  ChevronsUpDown,
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
  User,
  Loader2,
  Bot,
  Paperclip,
  Upload,
  Download,
  Trash2,
  File,
  Lock,
  Shield,
  Brain,
  Zap,
  Mail,
  AlertCircle,
  MessageSquare,
  CheckCircle,
  FileText,
  Clipboard,
  Info,
  Link,
  Pencil,
  Copy,
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
  edit: Pencil,
  copy: Copy,
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
  'refresh-cw': RefreshCw,
  bookmark: Bookmark,
  filter: Filter,
  'arrow-right': ArrowRight,
  open: ExternalLink,
  funnel: Funnel,
  sparkle: Sparkles,
  more: MoreHorizontal,
  pause: Pause,
  'cal-clock': Calendar,
  // New icons for candidate detail
  user: User,
  loader: Loader2,
  bot: Bot,
  paperclip: Paperclip,
  upload: Upload,
  download: Download,
  trash: Trash2,
  file: File,
  lock: Lock,
  shield: Shield,
  brain: Brain,
  zap: Zap,
  mail: Mail,
  'alert-circle': AlertCircle,
  'message-square': MessageSquare,
  'check-circle': CheckCircle,
  'file-text': FileText,
  clipboard: Clipboard,
  info: Info,
  'external-link': ExternalLink,
  link: Link,
  'chevron-up': ChevronUp,
  'chevron-up-down': ChevronsUpDown,
  spinner: Loader2,
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