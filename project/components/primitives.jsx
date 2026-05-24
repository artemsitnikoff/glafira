// Icons (Lucide-style inline SVG)
const Icon = ({ name, size = 18, ...rest }) => {
  const paths = {
    home:    <><path d="M3 12 12 4l9 8M5 10v9h14v-9"/></>,
    briefcase: <><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 13h18"/></>,
    users:   <><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M21.5 18a4.5 4.5 0 0 0-6.5-4"/></>,
    chart:   <><path d="M3 3v18h18"/><path d="M7 14l4-4 3 3 5-7"/></>,
    heart:   <><path d="M12 20s-7-4.5-9.5-9A5 5 0 0 1 12 6a5 5 0 0 1 9.5 5C19 15.5 12 20 12 20z"/></>,
    settings:<><circle cx="12" cy="12" r="3"/><path d="M19 12c0-.4 0-.8-.1-1.2l2-1.5-2-3.4-2.3.9c-.6-.5-1.3-.9-2-1.2L14 3h-4l-.6 2.6c-.7.3-1.4.7-2 1.2l-2.3-.9-2 3.4 2 1.5C5 11.2 5 11.6 5 12s0 .8.1 1.2l-2 1.5 2 3.4 2.3-.9c.6.5 1.3.9 2 1.2L10 21h4l.6-2.6c.7-.3 1.4-.7 2-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/></>,
    search:  <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    plus:    <><path d="M12 5v14M5 12h14"/></>,
    bell:    <><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9z"/><path d="M10 21h4"/></>,
    chevR:   <><path d="M9 6l6 6-6 6"/></>,
    chevD:   <><path d="M6 9l6 6 6-6"/></>,
    chevL:   <><path d="M15 6l-6 6 6 6"/></>,
    more:    <><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></>,
    archive: <><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/></>,
    clock:   <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    flame:   <><path d="M12 2c1 4 5 5 5 10a5 5 0 1 1-10 0c0-3 2-4 2-7 1 1 2 2 3 2"/></>,
    alert:   <><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.01"/></>,
    calClock:<><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/><circle cx="16" cy="15" r="3" fill="#fff"/><path d="M16 13.5V15l1 1"/></>,
    sort:    <><path d="M3 6h18M6 12h12M10 18h4"/></>,
    filter:  <><path d="M3 5h18l-7 9v6l-4-2v-4z"/></>,
    sparkle: <><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/><circle cx="12" cy="12" r="3"/></>,
    check:   <><path d="M5 12l5 5 9-11"/></>,
    x:       <><path d="M6 6l12 12M18 6L6 18"/></>,
    pause:   <><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></>,
    user:    <><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></>,
    refresh: <><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/></>,
    download:<><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></>,
    copy:    <><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></>,
    open:    <><path d="M14 3h7v7M21 3l-9 9M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/></>,
    star:    <><path d="M12 3l2.6 5.6 6.4.6-4.7 4.4 1.4 6.4L12 17l-5.7 3 1.4-6.4L3 9.2l6.4-.6z"/></>,
    phone:   <><path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/></>,
    mail:    <><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></>,
    message: <><path d="M21 12a8 8 0 0 1-12.5 6.6L3 20l1.5-5A8 8 0 1 1 21 12z"/></>,
    pin:     <><path d="M12 22s7-7 7-12a7 7 0 1 0-14 0c0 5 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/></>,
    arrowDown: <><path d="M12 4v16M5 13l7 7 7-7"/></>,
    arrowUp:   <><path d="M12 20V4M5 11l7-7 7 7"/></>,
    arrowRight:<><path d="M4 12h16M13 5l7 7-7 7"/></>,
    'pin-an': <><path d="M12 22s7-7 7-12a7 7 0 1 0-14 0c0 5 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/></>,
    funnel:   <><path d="M3 5h18l-7 9v6l-4-2v-4z"/></>,
    antenna:  <><path d="M5 21l4-9M19 21l-4-9M9 12h6M7 7a5 5 0 0 1 10 0M4.5 4.5a8 8 0 0 1 15 0"/></>,
    down:     <><path d="M3 6l4 4 4-4 4 4 4-4M3 14l4 4 4-4 4 4 4-4"/></>,
    telegram: <><path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4 20-7z"/></>,
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...rest}>
      {paths[name]}
    </svg>
  );
};

// Avatar
const AVATAR_COLORS = ['#E26B7E','#E08A3C','#C9A227','#59A861','#3FA3B3','#4F86E0','#8865D8','#B85F9E'];
function avatarColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_COLORS[Math.abs(h) % AVATAR_COLORS.length];
}
function initials(name) {
  return name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase();
}
function Avatar({ name, size = 'md' }) {
  const px = { sm: 28, md: 34, lg: 44 }[size];
  return (
    <div style={{
      width: px, height: px, borderRadius: '50%',
      background: avatarColor(name), color: '#fff',
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontWeight: 600, fontSize: size === 'sm' ? 11 : 13, flex: 'none',
    }}>{initials(name)}</div>
  );
}

Object.assign(window, { Icon, Avatar, avatarColor, initials });
