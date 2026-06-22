import { useRef } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useCandidateDetail } from '@/api/hooks/useCandidateDetail';
import { useEvaluation } from '@/api/hooks/useEvaluation';
import { useUploadDocument } from '@/api/mutations/candidateDetail';
import { AIVerdictCard } from '@/components/candidates/AIVerdictCard';

// Разбор периодов опыта (перенос проверенной логики бэка app/services/candidate.py).
// Сортировка свежих позиций сверху + расчёт длительности каждой позиции и общего стажа,
// чтобы заголовок совпадал с суммой длительностей (бэковый total_experience теряет месяцы).
const PRESENT_RE = /наст|present|сейчас|н\.?\s?в|текущ/i;
const RU_MONTHS: Record<string, number> = {
  янв: 1, фев: 2, мар: 3, апр: 4, май: 5, мая: 5, июн: 6,
  июл: 7, авг: 8, сен: 9, окт: 10, ноя: 11, дек: 12,
};
type ExpPt = { y: number; m: number } | null;

function parseExpPoint(raw: string): ExpPt {
  const s = (raw || '').trim().toLowerCase();
  if (!s) return null;
  if (PRESENT_RE.test(s)) {
    const t = new Date();
    return { y: t.getFullYear(), m: t.getMonth() + 1 };
  }
  let m = s.match(/(\d{4})\s*[-./]\s*(\d{1,2})/); // YYYY-MM (формат hh)
  if (m) return { y: +m[1], m: Math.min(12, Math.max(1, +m[2])) };
  m = s.match(/([а-яё]{3,})\.?\s*(\d{4})/); // «Апрель 2005»
  if (m) { const mo = RU_MONTHS[m[1].slice(0, 3)]; if (mo) return { y: +m[2], m: mo }; }
  m = s.match(/(?:19|20)\d{2}/); // голый год
  if (m) return { y: +m[0], m: 1 };
  return null;
}

function parseExpPeriod(period?: string | null): { start: ExpPt; end: ExpPt } {
  if (!period) return { start: null, end: null };
  // делим ТОЛЬКО по разделителю диапазона: тире в ОКРУЖЕНИИ пробелов или « по »
  // (внутренний дефис в «2005-04» не трогаем — у него нет пробелов вокруг)
  const parts = period.split(/\s+[—–-]\s+|\s+по\s+/i);
  const start = parseExpPoint(parts[0] ?? '');
  const end = parts.length > 1 ? parseExpPoint(parts[1] ?? '') : null;
  return { start, end };
}

function expMonths(period?: string | null): number {
  const { start, end } = parseExpPeriod(period);
  if (!start || !end) return 0;
  return Math.max(0, (end.y - start.y) * 12 + (end.m - start.m));
}

function expRecencyKey(period?: string | null): number {
  const { start, end } = parseExpPeriod(period);
  const pt = end || start;
  return pt ? pt.y * 12 + pt.m : -1; // непарсибельные — вниз
}

function pluralYears(n: number): string {
  const a = n % 10, b = n % 100;
  if (a === 1 && b !== 11) return 'год';
  if (a >= 2 && a <= 4 && !(b >= 12 && b <= 14)) return 'года';
  return 'лет';
}

function formatExpDuration(months: number): string | null {
  if (months <= 0) return null;
  const y = Math.floor(months / 12), mo = months % 12;
  const parts: string[] = [];
  if (y) parts.push(`${y} ${pluralYears(y)}`);
  if (mo) parts.push(`${mo} мес`);
  return parts.join(' ') || null;
}

// Разбор свободного описания позиции на пункты: каждая непустая строка — пункт,
// строки-заголовки (оканчивающиеся на ':') рендерятся жирным подзаголовком.
type JobItem = string | { h: string };
function parseJobItems(description?: string | null): JobItem[] {
  if (!description) return [];
  return description.split('\n').map((l) => l.trim()).filter(Boolean)
    .map((l) => (l.endsWith(':') ? { h: l } : l));
}

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
  applicationId?: string;
  onOpenAI?: () => void;
};

export function ResumeTab({ candidateId, candidate: candidateProps, fromPool, applicationId, onOpenAI }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const actualCandidateId = candidateId || candidateProps?.id;

  // If candidate is passed as prop (fromPool), use it; otherwise fetch
  const { data: candidateFromApi, isLoading } = useCandidateDetail(
    fromPool ? null : actualCandidateId
  );
  const candidate = fromPool ? candidateProps : candidateFromApi;

  // Get evaluation for AI verdict card
  const { data: evaluation } = useEvaluation(actualCandidateId, applicationId);

  const uploadMutation = useUploadDocument(actualCandidateId);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      uploadMutation.mutate([file, 'resume']);
    }
    // Clear input для повторной загрузки того же файла
    e.target.value = '';
  }

  if (isLoading) {
    return (
      <div className="tab-content">
        <Icon name="loader" size={24} />
        <p>Загружается...</p>
      </div>
    );
  }

  if (!candidate) {
    return (
      <div className="tab-content">
        <div className="empty-state">
          <Icon name="user" size={48} className="empty-state__icon" />
          <p className="empty-state__text">Данные кандидата не найдены</p>
        </div>
      </div>
    );
  }

  // Опыт: копия (НЕ мутируем данные React Query), свежие позиции сверху,
  // общий стаж тем же парсером (совпадает с суммой длительностей позиций).
  const sortedExperience = [...(candidate.experience || [])].sort(
    (a: any, b: any) => expRecencyKey(b.period) - expRecencyKey(a.period)
  );
  const totalMonths = sortedExperience.reduce((sum: number, e: any) => sum + expMonths(e.period), 0);
  const totalExpLabel = formatExpDuration(totalMonths) || (candidate as any).total_experience || null;

  return (
    <div className="resume-single">
      {/* Hidden upload input - preserve upload functionality */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.doc,.docx"
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

      {/* AI Verdict Card */}
      {evaluation && <AIVerdictCard evaluation={evaluation} mini onOpenAI={onOpenAI} />}

      {/* About Me Section */}
      {(candidate as any).resume_summary && (
        <>
          <h3 className="cc-sec-title">Обо мне</h3>
          <div className="job-desc" style={{ whiteSpace: 'pre-line' }}>
            {(candidate as any).resume_summary}
          </div>
        </>
      )}

      {candidate.experience && candidate.experience.length > 0 && (
        <>
          <h3 className="cc-sec-title">
            Опыт работы
            {totalExpLabel && (
              <span style={{ color: 'var(--fg-3)', fontWeight: 400, fontSize: '13px' }}>
                {' · '}общий стаж {totalExpLabel}
              </span>
            )}
          </h3>
          {sortedExperience.map((exp: any, index: number) => {
            const dur = formatExpDuration(expMonths(exp.period));
            const items = parseJobItems(exp.description);
            return (
              <div key={index} className="job">
                <div className="job-when">
                  {exp.period && <div className="job-period">{exp.period}</div>}
                  {dur && <div className="job-dur">{dur}</div>}
                </div>
                <div className="job-main">
                  {exp.company && <div className="job-co">{exp.company}</div>}
                  {exp.sphere && <div className="job-sphere">{exp.sphere}</div>}
                  {exp.position && <div className="job-title">{exp.position}</div>}
                  {items.length > 0 && (
                    <ul className="job-bullets">
                      {items.map((it: JobItem, i: number) =>
                        typeof it === 'string'
                          ? <li key={i}>{it}</li>
                          : <li key={i} className="job-subhead">{it.h}</li>
                      )}
                    </ul>
                  )}
                </div>
              </div>
            );
          })}
        </>
      )}

      {candidate.skills && candidate.skills.length > 0 && (
        <>
          <h3 className="cc-sec-title">Навыки</h3>
          <div className="skill-row">
            {candidate.skills.map((skill: any, index: number) => (
              <span key={index} className="skill-chip">
                {skill}
              </span>
            ))}
          </div>
        </>
      )}

      {candidate.education && candidate.education.length > 0 && (
        <>
          <h3 className="cc-sec-title">Образование</h3>
          {candidate.education.map((edu: any, index: number) => (
            <div key={index} className="job">
              <div className="job-when">
                {edu.years && <div className="job-period">{edu.years}</div>}
              </div>
              <div className="job-main">
                <div className="job-co">{edu.institution}</div>
                {edu.specialty && <div className="job-title">{edu.specialty}{edu.city ? ` · ${edu.city}` : ''}</div>}
              </div>
            </div>
          ))}
        </>
      )}

      {candidate.extra && (
        candidate.extra.languages?.length > 0 ||
        candidate.extra.relocation ||
        candidate.extra.business_trips ||
        candidate.extra.remote
      ) && (
        <>
          <h3 className="cc-sec-title">Дополнительно</h3>
          <div className="extra-grid">
            {candidate.extra.languages?.length > 0 && (
              <div><span className="extra-k">Языки:</span> {candidate.extra.languages.join(' · ')}</div>
            )}
            {candidate.extra.relocation && (
              <div><span className="extra-k">Переезд:</span> {candidate.extra.relocation}</div>
            )}
            {candidate.extra.business_trips && (
              <div><span className="extra-k">Командировки:</span> {candidate.extra.business_trips}</div>
            )}
            {candidate.extra.remote && (
              <div><span className="extra-k">Удалёнка:</span> {candidate.extra.remote}</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}