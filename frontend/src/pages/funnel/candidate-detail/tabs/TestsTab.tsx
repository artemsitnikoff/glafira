import { useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useAuthStore } from '@/store/authStore';
import type { Candidate } from '@/api/aliases';
import {
  useApplicationTests,
  useTestDetail,
  type TestAssignmentOut,
  type TestAnswerRow,
} from '@/api/hooks/useTests';
import { useRemindTest, useCancelTest } from '@/api/mutations/tests';
import { testCatClass } from '@/lib/testCategory';
import { AssignTestModal } from './AssignTestModal';
import { TestAnswersModal } from './TestAnswersModal';
import './TestsTab.css';

type Props = {
  applicationId: string;
  candidate?: Candidate | null;
};

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
}

function msToClock(ms: number | null): string {
  if (ms == null) return '—';
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Экран 11 — вкладка «Тесты» карточки кандидата. */
export function TestsTab({ applicationId, candidate }: Props) {
  const role = useAuthStore((s) => s.user?.role);
  const canManage = role !== 'manager'; // manager: только просмотр результатов
  const [assignOpen, setAssignOpen] = useState(false);
  const [answersOpen, setAnswersOpen] = useState(false);
  // Разбор ОДНОГО задания: строка ответа, открытая «глазом» в таблице (null = закрыто).
  const [reviewAnswer, setReviewAnswer] = useState<TestAnswerRow | null>(null);

  const { data: assignments, isLoading } = useApplicationTests(applicationId);
  const list: TestAssignmentOut[] = assignments ?? [];

  const activePending = list.find((a) => a.status === 'sent' || a.status === 'started');
  const lastCompleted = list.find((a) => a.status === 'completed' && a.result);

  // Профиль по блокам требует названий/размеров блоков из справочника (admin/recruiter).
  const resultTestId = canManage && !activePending && lastCompleted ? lastCompleted.test_id : null;
  const { data: resultTestDetail } = useTestDetail(resultTestId);

  const remind = useRemindTest(applicationId);
  const cancel = useCancelTest(applicationId);

  const modal = assignOpen && (
    <AssignTestModal
      applicationId={applicationId}
      candidate={candidate}
      onClose={() => setAssignOpen(false)}
    />
  );

  if (isLoading) {
    return <div className="tst-tab"><div className="ts-empty">Загрузка тестов…</div></div>;
  }

  // ── Пусто: тест не назначен (или прошлые назначения отменены/просрочены) ──
  if (!activePending && !lastCompleted) {
    return (
      <div className="tst-tab">
        <div className="ts-empty">
          <div className="empty-illust" style={{ margin: '0 auto' }}>
            <Icon name="clipboard" size={34} />
          </div>
          <h3>Тест не назначен</h3>
          <p>
            Отправьте кандидату тест способностей — ссылка уйдёт в предпочтительный канал,
            результат придёт сюда.
          </p>
          {canManage ? (
            <button className="btn btn-primary btn-sm" onClick={() => setAssignOpen(true)}>
              Назначить тест
            </button>
          ) : (
            <p style={{ color: 'var(--fg-3)' }}>Кандидату ещё не назначен тест.</p>
          )}
        </div>
        {modal}
      </div>
    );
  }

  // ── Назначен, но не пройден ──
  if (activePending) {
    const a = activePending;
    return (
      <div className="tst-tab">
        <div className="ts-res">
          <div className="ts-pending">
            <span className="ico"><Icon name="clock" size={17} /></span>
            <div className="tx">
              <b>«{a.test_name}» — ожидаем прохождения</b>
              <span>
                Ссылка отправлена {formatDateTime(a.created_at)}
                {a.channel ? ` · ${a.channel}` : ''}
                {a.expires_at ? ` · действует до ${formatDateTime(a.expires_at)}` : ''}
              </span>
            </div>
            {canManage && (
              <>
                <button
                  className="btn btn-secondary btn-sm"
                  onClick={() => remind.mutate(a.id)}
                  disabled={remind.isPending}
                >
                  {remind.isPending ? 'Отправка…' : 'Напомнить'}
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => cancel.mutate(a.id)}
                  disabled={cancel.isPending}
                >
                  {cancel.isPending ? 'Отмена…' : 'Отменить'}
                </button>
              </>
            )}
          </div>
        </div>
        {modal}
      </div>
    );
  }

  // ── Пройден: результат ──
  const a = lastCompleted!;
  const r = a.result!;
  const catCls = testCatClass(r.category);
  const blockScores = r.block_scores || {};
  const showBlocks = resultTestDetail && Object.keys(blockScores).length > 0;

  return (
    <div className="tst-tab">
      <div className="ts-res">
        <div className="ts-res-card">
          <div className="ts-res-head">
            <div className="ttl">
              <h4>{a.test_name}</h4>
              <div className="when">
                {formatDateTime(r.completed_at)}
                {r.duration_sec != null && ` · ${Math.round(r.duration_sec / 60)} мин`}
              </div>
            </div>
            <div className="ts-score">
              {r.raw_score}
              <span className="of">&thinsp;/&thinsp;{r.max_score}</span>
            </div>
            {r.category_label && <span className={`ts-cat ${catCls}`}>{r.category_label}</span>}
          </div>

          <div className="ts-res-body">
            {r.validity_flags.length > 0 && (
              <div className="ts-flag">
                <Icon name="alert-triangle" size={16} style={{ flex: 'none', marginTop: 1 }} />
                <div>
                  <b>Результат может быть недостоверен</b>
                  {r.validity_messages.length > 0 ? (
                    <ul>
                      {r.validity_messages.map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </div>
            )}

            {showBlocks && (
              <div>
                <div className="ts-subhead" style={{ marginBottom: 10 }}>Профиль по блокам</div>
                <div className="ts-bars">
                  {resultTestDetail!.blocks
                    .filter((b) => b.key in blockScores)
                    .map((b) => {
                      const val = blockScores[b.key] ?? 0;
                      const max = b.item_count || 1;
                      const p = val / max;
                      return (
                        <div key={b.key} className="ts-bar">
                          <span className="nm">{b.title}</span>
                          <span className="track">
                            <i
                              className={p >= 0.75 ? 'strong' : p < 0.65 ? 'weak' : ''}
                              style={{ width: `${Math.min(100, p * 100)}%` }}
                            />
                          </span>
                          <span className="val">{val}/{max}</span>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {/* Перцентиль — ТОЛЬКО если пришёл (база компании ≥ 30), иначе не показываем */}
            {r.percentile != null && (
              <div className="ts-pct">
                <Icon name="chart" size={15} /> Результат выше, чем у&nbsp;<b>{r.percentile}%</b>
                &nbsp;кандидатов на схожие позиции
              </div>
            )}

            <div className="ts-exp">
              <button className="ts-exp-btn" onClick={() => setAnswersOpen((o) => !o)}>
                <Icon name={answersOpen ? 'chevD' : 'chevR'} size={14} /> Ответы по заданиям
              </button>
              {answersOpen && (
                <table className="ts-ans">
                  <thead>
                    <tr>
                      <th style={{ width: 70 }}>Задание</th>
                      <th style={{ width: 90 }}>Ответ</th>
                      <th style={{ width: 110 }}>Результат</th>
                      <th>Время</th>
                      <th style={{ width: 44 }} aria-label="Разбор" />
                    </tr>
                  </thead>
                  <tbody>
                    {r.answers.map((ans) => (
                      <tr key={ans.item_id}>
                        <td className="mono">{ans.index + 1}</td>
                        <td className="mono">{ans.chosen_option_id ?? '—'}</td>
                        <td className={ans.is_correct ? 'ok' : 'no'}>
                          {ans.is_correct ? 'верно' : ans.chosen_option_id == null ? 'нет ответа' : 'неверно'}
                        </td>
                        <td className="mono">{msToClock(ans.time_ms)}</td>
                        <td className="rev">
                          <button
                            className="icon-btn"
                            onClick={() => setReviewAnswer(ans)}
                            title="Разбор задания"
                            aria-label="Разбор задания"
                          >
                            <Icon name="eye" size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>

        <div className="ts-res-actions">
          {canManage && (
            <button className="btn btn-secondary btn-sm" onClick={() => setAssignOpen(true)}>
              Назначить ещё тест
            </button>
          )}
        </div>
      </div>
      {modal}
      {reviewAnswer && (
        <TestAnswersModal
          answer={reviewAnswer}
          testName={a.test_name}
          onClose={() => setReviewAnswer(null)}
        />
      )}
    </div>
  );
}
