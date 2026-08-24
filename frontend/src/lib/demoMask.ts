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

// Пул фейковых ФИО [Фамилия, Имя, Отчество] — назначается детерминированно по исходному
// имени (одно и то же реальное имя → всегда одно фейковое, чтобы в списке и карточке совпадало).
const FAKE_NAMES: ReadonlyArray<readonly [string, string, string]> = [
  ['Иванов', 'Иван', 'Иванович'],
  ['Петров', 'Пётр', 'Сергеевич'],
  ['Смирнов', 'Алексей', 'Андреевич'],
  ['Кузнецов', 'Дмитрий', 'Николаевич'],
  ['Соколов', 'Максим', 'Викторович'],
  ['Попова', 'Анна', 'Сергеевна'],
  ['Новикова', 'Мария', 'Александровна'],
  ['Морозов', 'Артём', 'Игоревич'],
  ['Волкова', 'Елена', 'Дмитриевна'],
  ['Лебедев', 'Игорь', 'Олегович'],
];

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
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
    const seed =
      String(o.last_name || '') + '|' + String(o.first_name || '') + '|' + String(o.full_name || '');
    const [last, first, middle] = FAKE_NAMES[hashStr(seed) % FAKE_NAMES.length];
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
