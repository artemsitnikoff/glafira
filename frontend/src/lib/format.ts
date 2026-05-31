// Единый формат зарплаты — раньше было 3 разных реализации (разный разделитель/валюта).
// «220 000 ₽» (ru-локаль). RUB → ₽, иначе показываем код валюты.
export function formatSalary(amount: number | null | undefined, currency?: string | null): string {
  if (amount == null) return '';
  const sym = !currency || currency === 'RUB' ? '₽' : currency;
  return `${amount.toLocaleString('ru-RU')} ${sym}`;
}
