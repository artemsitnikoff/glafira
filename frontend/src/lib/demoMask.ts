// Демо-маскировка персональных данных на фронте (для показа/записи экрана).
// ⚠️ ТОЛЬКО отображение — данные в БД НЕ меняются. Маскировка активна ТОЛЬКО пока
// открыта одна из демо-вакансий (проверка по URL); на остальных страницах и вакансиях
// показываются реальные данные. Работает в response-интерцепторе axios (client.ts) —
// один вход, поэтому ничего не «протекает» мимо отдельных компонентов.

// Вакансии, для которых включена маскировка (демо-показ).
const DEMO_VACANCY_IDS = new Set<string>([
  'cfbf5cd5-5686-4d28-bac9-e4d52b0f674d',
]);

/** true — если сейчас открыта демо-вакансия (по пути /vacancies/{id}/...). */
export function demoMaskActive(): boolean {
  if (typeof window === 'undefined') return false;
  const m = window.location.pathname.match(/\/vacancies\/([0-9a-fA-F-]{36})/);
  return !!m && DEMO_VACANCY_IDS.has(m[1].toLowerCase());
}

// Один фейк на пол (по просьбе заказчика). Пол определяем ПО ИСХОДНОМУ ФИО (скан всех
// токенов: отчество на вна/вич или женское окончание фамилии) — а НЕ по полю gender,
// которого нет в строке списка. Список и карточка держат одно и то же full_name → пол
// определяется одинаково → фейк в списке и карточке СОВПАДАЕТ.
const MALE_NAME: readonly [string, string, string] = ['Иванов', 'Иван', 'Иванович'];
const FEMALE_NAME: readonly [string, string, string] = ['Дементьева', 'Глафира', 'Ивановна'];

function nameIsFemale(o: Record<string, unknown>): boolean {
  const full = String(
    o.full_name || `${o.last_name || ''} ${o.first_name || ''} ${o.middle_name || ''}`
  ).toLowerCase();
  const toks = full.split(/\s+/).filter(Boolean);
  for (const t of toks) {
    if (/(вна|чна)$/.test(t)) return true;   // женское отчество
    if (/(ич|ыч)$/.test(t)) return false;    // мужское отчество
  }
  for (const t of toks) {
    if (/(ова|ева|ёва|ина|ына|ская|цкая|ая)$/.test(t)) return true;  // женская фамилия
  }
  return false;  // по умолчанию — мужской
}

const MASK_PHONE = '+7 (XXX) XXX-XX-XX';
const MASK_EMAIL = 'скрыто@demo.local';

/**
 * Рекурсивно маскирует ПДн в объекте ответа API (мутирует на месте).
 * Маскируются: ФИО (first/last/middle/full_name), телефон, email, фото (avatar/photo_url),
 * дата рождения, мессенджеры, source_url (в нём логин). Технические поля/id не трогаем.
 * Обёрнуто в try на стороне вызова — маскировка не должна ломать ответ.
 */
export function maskPiiDeep(data: unknown): void {
  if (data == null || typeof data !== 'object') return;
  if (Array.isArray(data)) {
    for (const item of data) maskPiiDeep(item);
    return;
  }
  const o = data as Record<string, unknown>;

  const hasName = 'first_name' in o || 'last_name' in o || 'full_name' in o;
  if (hasName) {
    const [last, first, middle] = nameIsFemale(o) ? FEMALE_NAME : MALE_NAME;
    if ('first_name' in o && o.first_name) o.first_name = first;
    if ('last_name' in o && o.last_name) o.last_name = last;
    if ('middle_name' in o && o.middle_name) o.middle_name = middle;
    if ('full_name' in o && o.full_name) o.full_name = `${last} ${first} ${middle}`;
  }
  if ('phone' in o && o.phone) o.phone = MASK_PHONE;
  if ('email' in o && o.email) o.email = MASK_EMAIL;
  if ('avatar_url' in o && o.avatar_url) o.avatar_url = null;
  if ('photo_url' in o && o.photo_url) o.photo_url = null;
  if ('source_url' in o && o.source_url) o.source_url = null;
  if ('birth_date' in o && o.birth_date) o.birth_date = null;
  if ('messengers' in o && Array.isArray(o.messengers)) o.messengers = [];
  // Свободный текст резюме может содержать имя/телефон внутри — прячем целиком.
  if ('resume_summary' in o && o.resume_summary) o.resume_summary = '(скрыто для показа)';
  if ('resume_text' in o && o.resume_text) o.resume_text = '(скрыто для показа)';

  for (const key of Object.keys(o)) {
    const v = o[key];
    if (v && typeof v === 'object') maskPiiDeep(v);
  }
}
