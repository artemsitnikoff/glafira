import { useMemo, useRef, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import type { Candidate, ApiError } from '@/api/aliases';
import { useTests } from '@/api/hooks/useTests';
import { useAssignTest } from '@/api/mutations/tests';
import { messengerChannel } from '@/lib/messengers';
import './TestsTab.css';

type Channel = 'telegram' | 'email' | 'hh';

type Props = {
  applicationId: string;
  candidate?: Candidate | null;
  onClose: () => void;
};

function firstName(full: string | null | undefined): string {
  if (!full) return 'Кандидат';
  const parts = full.trim().split(/\s+/);
  // full_name = «Фамилия Имя [Отчество]» → имя = второй токен, иначе первый.
  return parts[1] || parts[0];
}

/** Экран 10 — назначение теста кандидату по заявке. */
export function AssignTestModal({ applicationId, candidate, onClose }: Props) {
  const { data: tests, isLoading: testsLoading } = useTests();
  const assign = useAssignTest(applicationId);
  const msgRef = useRef<HTMLTextAreaElement>(null);

  const activeTests = useMemo(() => (tests ?? []).filter((t) => t.status === 'active'), [tests]);

  // Доступность каналов по контактам кандидата (предпочтительный помечается).
  const hasTelegram =
    (candidate?.messengers ?? []).some((m) => messengerChannel(m) === 'telegram') ||
    candidate?.preferred_channel === 'telegram';
  const hasEmail = !!candidate?.email;
  const hasHh = candidate?.source === 'hh';
  const preferred: Channel | null =
    candidate?.preferred_channel === 'telegram'
      ? 'telegram'
      : candidate?.preferred_channel === 'email'
        ? 'email'
        : null;

  const channelDefs: { id: Channel; label: string; available: boolean }[] = [
    { id: 'telegram', label: 'Telegram', available: hasTelegram },
    { id: 'email', label: 'E-mail', available: hasEmail },
    { id: 'hh', label: 'hh.ru', available: hasHh },
  ];

  const defaultChannel: Channel | '' =
    preferred && channelDefs.find((c) => c.id === preferred)?.available
      ? preferred
      : (channelDefs.find((c) => c.available)?.id ?? '');

  const [pick, setPick] = useState<string>('');
  const [days, setDays] = useState(7);
  const [channel, setChannel] = useState<Channel | ''>(defaultChannel);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Первый активный тест выбираем по умолчанию, когда список загрузился.
  const effectivePick = pick || activeTests[0]?.id || '';
  const pickedTest = activeTests.find((t) => t.id === effectivePick);

  const name = firstName(candidate?.full_name);
  const template = pickedTest
    ? `${name}, здравствуйте! Следующий шаг — короткий тест «${pickedTest.name}». ` +
      `Проходить лучше в спокойной обстановке: таймер идёт непрерывно. ` +
      `Ссылка действует ${days} ${days === 1 ? 'день' : days < 5 ? 'дня' : 'дней'} — она придёт вам в сообщении.`
    : '';

  const handleSend = () => {
    if (!effectivePick) return;
    setError(null);
    assign.mutate(
      {
        test_id: effectivePick,
        ttl_days: days,
        channel: channel || undefined,
        message: msgRef.current?.value.trim() || undefined,
      },
      {
        onSuccess: () => setSent(true),
        onError: (e) => setError((e as unknown as ApiError)?.error?.message || 'Не удалось назначить тест'),
      },
    );
  };

  const channelLabel = (c: Channel | ''): string =>
    c === 'telegram' ? 'в Telegram' : c === 'email' ? 'на e-mail' : c === 'hh' ? 'в чат hh.ru' : 'в предпочтительный канал';

  return (
    <div className="tst-modal-ovl" onClick={onClose}>
      <div className="ts-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ts-modal-head">
          <div>
            <h3>Назначить тест</h3>
            <div className="sub">{candidate?.full_name || 'Кандидат'}</div>
          </div>
          <button className="x" onClick={onClose} aria-label="Закрыть">
            <Icon name="x" size={16} />
          </button>
        </div>

        {sent ? (
          <div className="ts-modal-body">
            <div className="ts-sent">
              <Icon name="check" size={16} /> Ссылка отправлена, ожидаем прохождения
            </div>
            <div style={{ fontSize: 13, color: 'var(--fg-2)', lineHeight: 1.6 }}>
              «{pickedTest?.name}» ушёл {channelLabel(channel)} и действует {days}{' '}
              {days === 1 ? 'день' : days < 5 ? 'дня' : 'дней'}. Результат появится во вкладке
              «Тесты» сразу после прохождения.
            </div>
          </div>
        ) : (
          <div className="ts-modal-body">
            <div>
              <span className="ts-lbl">Что назначаем</span>
              {testsLoading ? (
                <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>Загрузка тестов…</div>
              ) : activeTests.length === 0 ? (
                <div style={{ fontSize: 13, color: 'var(--fg-3)' }}>
                  Нет активных тестов. Активируйте тест в Настройках → Тесты.
                </div>
              ) : (
                <div className="ts-pick">
                  {activeTests.map((t) => (
                    <button
                      key={t.id}
                      className={`ts-pick-opt ${effectivePick === t.id ? 'on' : ''}`}
                      onClick={() => setPick(t.id)}
                    >
                      <span className="ts-pico">
                        <Icon name="clipboard" size={15} />
                      </span>
                      <span className="nm">{t.name}</span>
                      <span className="mt">{t.item_count} заданий</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div>
              <span className="ts-lbl">Срок действия ссылки</span>
              <div className="ts-days">
                <input
                  type="number"
                  min={1}
                  max={90}
                  value={days}
                  onChange={(e) => setDays(Math.min(90, Math.max(1, Number(e.target.value) || 1)))}
                />
                <span>дней — после этого ссылка перестанет открываться</span>
              </div>
            </div>

            <div>
              <span className="ts-lbl">Канал отправки</span>
              <div className="ts-chan">
                {channelDefs.map((c) => (
                  <button
                    key={c.id}
                    className={channel === c.id ? 'on' : ''}
                    disabled={!c.available}
                    title={c.available ? undefined : 'Нет контакта для этого канала'}
                    onClick={() => setChannel(c.id)}
                  >
                    {preferred === c.id && c.available && <span className="pref">предпочитает</span>}
                    {c.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <span className="ts-lbl">Текст сообщения</span>
              <textarea
                ref={msgRef}
                className="ts-tpl"
                defaultValue={template}
                key={`${effectivePick}-${days}`}
              />
            </div>
          </div>
        )}

        {error && <div className="ts-modal-err">{error}</div>}

        <div className="ts-modal-foot">
          <span className="sp" />
          {sent ? (
            <button className="btn btn-primary btn-sm" onClick={onClose}>
              Готово
            </button>
          ) : (
            <>
              <button className="btn btn-secondary btn-sm" onClick={onClose} disabled={assign.isPending}>
                Отмена
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleSend}
                disabled={!effectivePick || assign.isPending}
              >
                {assign.isPending ? 'Отправка…' : 'Отправить'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
