import { useEffect, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { PageHead, Card, FormRow, TextInput, Switch } from '../components/FormComponents';
import { useTestDetail, type TestCategoryBand } from '@/api/hooks/useTests';
import { useUpdateTest } from '@/api/mutations/tests';
import { testCatClass, testMarkerClass } from '@/lib/testCategory';
import type { ApiError } from '@/api/aliases';

type Props = {
  testId: string;
  onBack: () => void;
  readOnly: boolean;
};

const KIND_LABEL: Record<string, string> = {
  single: 'Одиночный тест',
  blocked: 'Тест с блоками',
};

function secToMin(sec: number | null | undefined): number {
  return sec ? Math.round(sec / 60) : 0;
}

/** Экран 9 — настройка одного теста. PATCH admin-only → readOnly для рекрутёра. */
export function TestConfig({ testId, onBack, readOnly }: Props) {
  const { data: test, isLoading } = useTestDetail(testId);
  const updateTest = useUpdateTest(testId);

  // Редактируемый черновик — инициализируется из конфига теста при загрузке.
  // ⚠️ «Перемешивать варианты» больше не настраивается: сервер ВСЕГДА перемешивает варианты
  // секретным per-attempt seed (анти-утечка — иначе позиция верного выводима из индекса задания).
  // Тумблер показан как всегда-включённый (locked), в PATCH уходит true.
  const [allowBack, setAllowBack] = useState(false);
  const [autoRejectOn, setAutoRejectOn] = useState(false);
  const [autoRejectVal, setAutoRejectVal] = useState(0);
  const [bands, setBands] = useState<TestCategoryBand[]>([]);
  const [blockMins, setBlockMins] = useState<Record<string, number>>({});
  const [dirty, setDirty] = useState(false);
  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (!test) return;
    setAllowBack(test.allow_back);
    setAutoRejectOn(test.auto_reject_below !== null);
    setAutoRejectVal(test.auto_reject_below ?? 0);
    setBands((test.category_thresholds ?? []).map((b) => ({ ...b })));
    setBlockMins(Object.fromEntries(test.blocks.map((b) => [b.id, secToMin(b.duration_sec)])));
    setDirty(false);
  }, [test]);

  const touch = () => setDirty(true);

  const patchBand = (i: number, key: 'min' | 'max', value: number) => {
    setBands((prev) => prev.map((b, x) => (x === i ? { ...b, [key]: value } : b)));
    touch();
  };

  const handleSave = () => {
    if (readOnly || !test) return;
    updateTest.mutate(
      {
        randomize_options: true, // всегда on: анти-утечка (см. коммент выше)
        allow_back: allowBack,
        auto_reject_below: autoRejectOn ? autoRejectVal : null,
        category_thresholds: bands.length ? bands : null,
        // Блоки: время на блок (минуты → секунды). duration_sec ≥ 1 на беке.
        blocks: test.blocks.length
          ? test.blocks.map((b) => ({
              id: b.id,
              duration_sec: Math.max(1, Math.round((blockMins[b.id] || 0) * 60)),
            }))
          : null,
      },
      {
        onSuccess: () => {
          setDirty(false);
          setNotice({ type: 'success', text: 'Настройки теста сохранены' });
        },
        onError: (e) => {
          const msg = (e as unknown as ApiError)?.error?.message || 'Не удалось сохранить';
          setNotice({ type: 'error', text: msg });
        },
      },
    );
  };

  if (isLoading || !test) {
    return (
      <div className="set-content-inner st-tests">
        <button className="ts-back" onClick={onBack}>
          <Icon name="chevL" size={13} /> Все тесты
        </button>
        <div className="ts-empty-note">Загрузка настроек теста…</div>
      </div>
    );
  }

  const isBlocked = test.blocks.length > 0;
  const totalQ = isBlocked ? test.blocks.reduce((a, b) => a + b.item_count, 0) : test.item_count;
  const totalM = isBlocked
    ? test.blocks.reduce((a, b) => a + (blockMins[b.id] || 0), 0)
    : secToMin(test.duration_sec);

  // Категория для превью автоотказа: бэнд, в диапазон которого попал порог.
  const autoRejectBand = bands.find((b) => autoRejectVal >= b.min && autoRejectVal <= b.max);

  return (
    <div className="set-content-inner st-tests">
      <button className="ts-back" onClick={onBack}>
        <Icon name="chevL" size={13} /> Все тесты
      </button>

      <PageHead
        title={test.name}
        subtitle={`${KIND_LABEL[test.kind] || test.kind} · настройка теста`}
        dirty={dirty && !readOnly}
        onSave={handleSave}
        saving={updateTest.isPending}
      />

      {notice && (
        <div
          className={notice.type === 'success' ? 'info-banner' : 'error-banner'}
          style={{
            background: notice.type === 'success' ? 'var(--success-bg)' : 'var(--error-bg)',
            borderColor: notice.type === 'success' ? 'var(--success-border)' : 'var(--error-border)',
            color: notice.type === 'success' ? 'var(--success-fg)' : 'var(--error-fg)',
          }}
        >
          <Icon name={notice.type === 'success' ? 'check' : 'x'} size={16} />
          <div>{notice.text}</div>
        </div>
      )}

      {/* Общее — название/тип/состав read-only (нет PATCH этих полей), тумблеры редактируемые */}
      <Card title="Общее">
        <div className="ts-grid2">
          <FormRow label="Название">
            <TextInput value={test.name} locked />
          </FormRow>
          <FormRow label="Тип">
            <TextInput value={KIND_LABEL[test.kind] || test.kind} locked />
          </FormRow>
          <FormRow label="Заданий" hint="Сколько заданий увидит кандидат">
            <TextInput value={String(totalQ)} mono locked />
          </FormRow>
          <FormRow label="Длительность" hint="Общий лимит времени">
            <TextInput value={totalM ? String(totalM) : '—'} mono suffix="мин" locked />
          </FormRow>
        </div>
        <div className="ts-switches">
          <Switch
            value={true}
            onChange={() => {}}
            label="Перемешивать варианты ответов"
            desc="Всегда включено: порядок вариантов у каждого кандидата свой (защита от передачи ответов)."
            disabled
          />
          <Switch
            value={allowBack}
            onChange={(v) => { setAllowBack(v); touch(); }}
            label="Разрешить возврат к заданиям"
            desc="Кандидат сможет вернуться к предыдущему заданию внутри блока."
            disabled={readOnly}
          />
        </div>
      </Card>

      {/* Блоки — только для тестов с блоками, редактируется время на блок */}
      {isBlocked && (
        <Card title="Блоки" desc="Время считается по каждому блоку отдельно.">
          {test.blocks.map((b, i) => (
            <div key={b.id} className="ts-blk">
              <span className="n">{i + 1}</span>
              <span className="nm">{b.title}</span>
              <span className="qn">{b.item_count} заданий</span>
              <span className="mins">
                <input
                  type="number"
                  min={1}
                  value={blockMins[b.id] ?? 0}
                  disabled={readOnly}
                  onChange={(e) => {
                    setBlockMins((prev) => ({ ...prev, [b.id]: Number(e.target.value) || 0 }));
                    touch();
                  }}
                />{' '}
                мин
              </span>
            </div>
          ))}
          <div className="ts-total">
            Всего: <b>{totalQ}</b> заданий · <b>{totalM}</b> мин
          </div>
        </Card>
      )}

      {/* Пороги — границы категорий по баллу (светофорные метки из marker) */}
      {bands.length > 0 && (
        <Card
          title="Пороги"
          desc="Границы категорий по баллу. Категория показывается рекрутёру в карточке кандидата — кандидат её не видит."
        >
          <div className="ts-thresholds">
            {bands.map((b, i) => (
              <div key={b.key} className="ts-thr">
                <span className={`lamp ${testMarkerClass(b.marker)}`} />
                <span className="nm">{b.label}</span>
                <input
                  type="number"
                  value={b.min}
                  disabled={readOnly}
                  onChange={(e) => patchBand(i, 'min', Number(e.target.value) || 0)}
                />
                <input
                  type="number"
                  value={b.max}
                  disabled={readOnly}
                  onChange={(e) => patchBand(i, 'max', Number(e.target.value) || 0)}
                />
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Автоматика (на уровне ТЕСТА) — только автоотказ ниже порога.
          Автоотправка на этапе настраивается per-vacancy в форме вакансии. */}
      <Card
        title="Автоматика"
        desc="Глафира может отсеивать кандидатов по результату теста без участия рекрутёра. Порог — на уровне теста: применяется КО ВСЕМ вакансиям, использующим этот тест."
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Switch
            value={autoRejectOn}
            onChange={(v) => { setAutoRejectOn(v); touch(); }}
            label="Автоматически отклонять при результате ниже порога"
            desc="Отказ уходит с причиной «Не прошёл тест». Рекрутёр видит это в ленте действий."
            disabled={readOnly}
          />
          {autoRejectOn && (
            <div className="ts-auto-row">
              <span className="ts-auto-lbl">Порог, баллов:</span>
              <input
                type="number"
                className="ts-num"
                min={0}
                value={autoRejectVal}
                disabled={readOnly}
                onChange={(e) => { setAutoRejectVal(Number(e.target.value) || 0); touch(); }}
              />
              {autoRejectBand && (
                <span className={`ts-cat ${testCatClass(autoRejectBand.key)}`}>
                  {autoRejectBand.label.toLowerCase()}
                </span>
              )}
            </div>
          )}
          <div className="ts-note">
            Автоотправку теста на этапе воронки настраивайте в форме вакансии
            (шаг «Автоматизация»).
          </div>
        </div>
      </Card>
    </div>
  );
}
