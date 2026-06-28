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
  LogOut,
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
  Star,
  MoreHorizontal,
  Pause,
  Play,
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
  MapPin,
  Heart,
  Key,
  Phone,
  Save,
  Cpu,
  Database,
  Radio,
} from 'lucide-react';

const iconMap = {
  home: Home,
  briefcase: Briefcase,
  users: Users,
  activity: Activity,
  'bar-chart': BarChart3,
  chart: BarChart3,
  settings: Settings,
  search: Search,
  plus: Plus,
  edit: Pencil,
  copy: Copy,
  archive: Archive,
  bell: Bell,
  'log-out': LogOut,
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
  sparkles: Sparkles,
  sparkle: Sparkles, // alias для совместимости
  star: Star,
  pin: MapPin,
  more: MoreHorizontal,
  'more-horizontal': MoreHorizontal,
  pause: Pause,
  play: Play,
  'cal-clock': Calendar,
  // New icons for candidate detail
  user: User,
  key: Key,
  phone: Phone,
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
  chevD: ChevronDown,
  chevR: ChevronRight,
  chevL: ChevronLeft,
  arrowRight: ArrowRight,
  calClock: Calendar,
  heart: Heart, // Пульс-Онбординг → Heart icon
  save: Save,
  cpu: Cpu,
  database: Database,
  radio: Radio, // antenna-эквивалент для «Автоподбор»
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