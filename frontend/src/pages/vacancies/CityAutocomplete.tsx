import { useState, useEffect, useRef } from 'react';
import { api } from '@/api/client';

interface CitySuggestion {
  value: string;
  label: string;
  region?: string | null;
}

interface Props {
  value: string | null;
  onChange: (city: string | null) => void;
}

/**
 * Автокомплит города через онлайн-справочник DaData (бек-прокси
 * GET /suggestions/cities). Свободный ввод сохраняется как есть; выбор подсказки
 * пишет чистое имя города.
 */
export function CityAutocomplete({ value, onChange }: Props) {
  const [query, setQuery] = useState(value || '');
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<CitySuggestion[]>([]);
  const [activeIdx, setActiveIdx] = useState(-1);
  const wrapRef = useRef<HTMLDivElement>(null);
  const justPicked = useRef(false);

  // Синхронизация с внешним значением (предзаполнение в режиме редактирования)
  useEffect(() => {
    setQuery(value || '');
  }, [value]);

  // Дебаунс-запрос подсказок
  useEffect(() => {
    const q = query.trim();
    if (justPicked.current) {
      justPicked.current = false;
      return;
    }
    if (q.length < 2) {
      setItems([]);
      setOpen(false);
      return;
    }
    let cancelled = false;
    const t = setTimeout(async () => {
      try {
        const resp = await api.get('/suggestions/cities', { params: { query: q } });
        if (!cancelled) {
          const list = resp.data as CitySuggestion[];
          setItems(list);
          setOpen(list.length > 0);
        }
      } catch {
        if (!cancelled) {
          setItems([]);
          setOpen(false);
        }
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [query]);

  // Закрытие по клику вне
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const pick = (s: CitySuggestion) => {
    justPicked.current = true;
    setQuery(s.value);
    onChange(s.value);
    setItems([]);
    setOpen(false);
    setActiveIdx(-1);
  };

  return (
    <div className="nv-city" ref={wrapRef}>
      <input
        className="nv-input"
        placeholder="Начните вводить город…"
        value={query}
        autoComplete="off"
        onChange={(e) => {
          const v = e.target.value;
          setQuery(v);
          onChange(v || null);
          setActiveIdx(-1);
        }}
        onFocus={() => {
          if (items.length > 0) setOpen(true);
        }}
        onKeyDown={(e) => {
          if (!open || items.length === 0) return;
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveIdx((i) => Math.min(i + 1, items.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveIdx((i) => Math.max(i - 1, 0));
          } else if (e.key === 'Enter' && activeIdx >= 0) {
            e.preventDefault();
            pick(items[activeIdx]);
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
      />
      {open && items.length > 0 && (
        <div className="nv-city-menu">
          {items.map((s, i) => (
            <button
              type="button"
              key={s.label + i}
              className={`nv-city-opt ${i === activeIdx ? 'active' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(s);
              }}
            >
              <span className="nv-city-name">{s.label}</span>
              {s.region && s.region !== s.label && (
                <span className="nv-city-region">{s.region}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
