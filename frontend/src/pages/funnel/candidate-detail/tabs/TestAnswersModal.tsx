import type { ReactNode } from 'react';
import { Icon } from '@/components/ui/Icon';
import { MatrixCell, type CellParams } from '@/pages/public/MatrixCell';
import type { TestAnswerRow } from '@/api/hooks/useTests';
import './TestAnswersModal.css';

// openapi протух (модуль «Тесты» не в сгенерированном контракте) → локальные типы
// новых полей ответа + as-cast (§3 CLAUDE.md). Бек расширяет TestResultOut.answers[]
// параллельно: item_kind / body / chosen / correct. Существующие поля строки ответа
// (index/item_id/chosen_option_id/is_correct/time_ms) — из TestAnswerRow.
type MatrixBody = { cells: (CellParams | null)[][]; question_cell: [number, number] };
type TextBody = {
  kind: 'exclusion' | 'analogy' | 'series' | 'generalization';
  terms?: unknown;
  prompt?: string | null;
};
type AnswerChoice = { params?: CellParams | null; text?: string | null } | null;

type ReviewAnswer = TestAnswerRow & {
  item_kind?: 'matrix' | 'text';
  body?: MatrixBody | TextBody;
  chosen?: AnswerChoice;
  correct?: { params?: CellParams | null; text?: string | null };
};

type Props = {
  answers: TestAnswerRow[];
  testName: string;
  candidateName: string;
  onClose: () => void;
};

function msToClock(ms: number | null): string {
  if (ms == null) return '—';
  const total = Math.round(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

/** Матрица-вопрос 3×3 из body.cells (пустая клетка question_cell = пунктирный «?»). */
function renderMatrixQuestion(body?: MatrixBody): ReactNode {
  const cells = body?.cells ?? [];
  return (
    <div className="tans-matrix">
      {cells.flatMap((row, r) =>
        row.map((cell, c) =>
          cell == null ? (
            <div key={`${r}-${c}`} className="tans-mc q">
              ?
            </div>
          ) : (
            <div key={`${r}-${c}`} className="tans-mc">
              <MatrixCell params={cell} />
            </div>
          ),
        ),
      )}
    </div>
  );
}

/** Текст-вопрос: аналогия «a:b=c:?», числовой ряд моноширинно, слова списком. */
function renderTextQuestion(body?: TextBody): ReactNode {
  if (!body) return null;
  const kind = body.kind;
  const prompt = typeof body.prompt === 'string' ? body.prompt : '';

  let visual: ReactNode = null;
  if (kind === 'analogy' && body.terms && typeof body.terms === 'object' && !Array.isArray(body.terms)) {
    const t = body.terms as { a?: string; b?: string; c?: string };
    visual = (
      <div className="tans-analogy">
        {t.a} <span className="op">:</span> {t.b} <span className="op">=</span> {t.c} <span className="op">:</span>{' '}
        <span className="qm">?</span>
      </div>
    );
  } else if (kind === 'series' && Array.isArray(body.terms)) {
    const seq = (body.terms as (number | string)[]).map(String);
    visual = <div className="tans-series">{seq.join('   ')}   …   ?</div>;
  } else if (kind === 'generalization' && Array.isArray(body.terms)) {
    const words = (body.terms as (number | string)[]).map(String);
    visual = (
      <div className="tans-analogy">
        {words.join(' · ')} <span className="op">·</span> <span className="qm">?</span>
      </div>
    );
  } else if (kind === 'exclusion' && Array.isArray(body.terms)) {
    const words = (body.terms as (number | string)[]).map(String);
    visual = (
      <div className="tans-words">
        {words.map((w, i) => (
          <span key={i} className="tans-word">
            {w}
          </span>
        ))}
      </div>
    );
  }

  return (
    <>
      {visual}
      {prompt && <p className="tans-instr">{prompt}</p>}
    </>
  );
}

/** Разбор сессии: по каждому заданию — вопрос + выбор кандидата + правильный ответ. */
export function TestAnswersModal({ answers, testName, candidateName, onClose }: Props) {
  return (
    <div className="tans-ovl" onClick={onClose}>
      <div className="tans-modal" onClick={(e) => e.stopPropagation()}>
        <div className="tans-head">
          <div>
            <h3>Разбор ответов</h3>
            <div className="sub">
              {candidateName} · {testName}
            </div>
          </div>
          <button className="x" onClick={onClose} aria-label="Закрыть">
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="tans-body">
          {answers.map((raw) => {
            const a = raw as ReviewAnswer;
            const isMatrix =
              a.item_kind === 'matrix' || (a.body != null && 'cells' in (a.body as object));
            const noAnswer = a.chosen_option_id == null && a.chosen == null;
            const status: 'ok' | 'no' | 'none' = noAnswer ? 'none' : a.is_correct ? 'ok' : 'no';

            return (
              <div className="tans-item" key={a.item_id}>
                <div className="tans-item-head">
                  <span className="tans-num">Задание {a.index + 1}</span>
                  <span className={`tans-badge ${status}`}>
                    {status === 'ok' ? 'верно' : status === 'no' ? 'неверно' : 'нет ответа'}
                  </span>
                  <span className="tans-time">{msToClock(a.time_ms)}</span>
                </div>

                <div className="tans-q">
                  <span className="tans-lbl">Вопрос</span>
                  {isMatrix
                    ? renderMatrixQuestion(a.body as MatrixBody | undefined)
                    : renderTextQuestion(a.body as TextBody | undefined)}
                </div>

                <div className="tans-compare">
                  <div className="tans-side">
                    <span className="tans-lbl">Ответ кандидата</span>
                    <div className={`tans-ansbox ${status}`}>
                      {noAnswer ? (
                        <span className="tans-empty">нет ответа</span>
                      ) : isMatrix ? (
                        a.chosen?.params ? (
                          <div className="tans-cell">
                            <MatrixCell params={a.chosen.params} />
                          </div>
                        ) : (
                          <span className="tans-empty">—</span>
                        )
                      ) : (
                        <span className="tans-txt">{a.chosen?.text ?? '—'}</span>
                      )}
                    </div>
                  </div>

                  <div className="tans-side">
                    <span className="tans-lbl">Правильный ответ</span>
                    <div className="tans-ansbox ok">
                      {isMatrix ? (
                        a.correct?.params ? (
                          <div className="tans-cell">
                            <MatrixCell params={a.correct.params} />
                          </div>
                        ) : (
                          <span className="tans-empty">—</span>
                        )
                      ) : (
                        <span className="tans-txt">{a.correct?.text ?? '—'}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
