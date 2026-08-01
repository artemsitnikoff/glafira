import { testCatClass } from '@/lib/testCategory';
import './TestPill.css';

type Props = {
  status?: string | null; // 'none' | 'sent' | 'started' | 'completed'
  score?: number | null;
  category?: string | null;
};

/**
 * Плашка теста в колонке воронки (экран 12). Читает test_status/test_score/test_category
 * из ApplicationRow — НЕ пересчитывает. Балл показывается только для completed с баллом.
 */
export function TestPill({ status, score, category }: Props) {
  if (status === 'sent' || status === 'started') {
    return <span className="ts-pill wait" title="Тест отправлен, ожидаем прохождения">⏳ ожидаем</span>;
  }
  if (status === 'completed' && score != null) {
    return (
      <span className={`ts-pill ${testCatClass(category)}`} title="Результат теста">
        {score}
      </span>
    );
  }
  return <span className="ts-dash">—</span>;
}
