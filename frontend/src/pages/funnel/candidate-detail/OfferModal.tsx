import { useCallback, useEffect, useRef, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import type { ApiError } from '@/api/aliases';
import { useGenerateOffer, useSendOffer } from '@/api/mutations/offer';
import './OfferModal.css';

// Ограничения вложения (финальная валидация — на беке, здесь честная подсказка).
const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 МБ
const FILE_ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt,.rtf';

/** Человекочитаемый размер файла: «240 КБ» / «1,3 МБ». */
function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} МБ`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${bytes} Б`;
}

// Попап «Отправить оффер»: при открытии Глафира (LLM) генерирует тело письма,
// рекрутёр правит его и отправляет кандидату на email. Приветствие (header) и
// подпись (footer) берутся из настроек и показываются read-only вокруг тела —
// сервер сам обрамляет header + body + footer при отправке.
type Props = {
  applicationId: string;
  candidateId: string;
  candidateName: string;
  isOpen: boolean;
  onClose: () => void;
};

export function OfferModal({ applicationId, candidateId, candidateName, isOpen, onClose }: Props) {
  const [body, setBody] = useState('');
  const [header, setHeader] = useState('');
  const [footer, setFooter] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const generate = useGenerateOffer(applicationId);
  const sendOffer = useSendOffer(applicationId, candidateId);
  const { mutate: generateOffer } = generate;

  // Запуск генерации тела оффера (при открытии + повторно по кнопке «Сгенерировать заново»).
  const runGenerate = useCallback(() => {
    setBody('');
    setHeader('');
    setFooter('');
    setGenError(null);
    setSendError(null);
    generateOffer(undefined, {
      onSuccess: (data) => {
        setBody(data.body);
        setHeader(data.header);
        setFooter(data.footer);
      },
      onError: (e) => {
        setGenError((e as unknown as ApiError)?.error?.message || 'Не удалось сгенерировать оффер');
      },
    });
  }, [generateOffer]);

  // При открытии попапа — сгенерировать тело оффера и сбросить вложение.
  useEffect(() => {
    if (isOpen) {
      setFile(null);
      runGenerate();
    }
  }, [isOpen, applicationId, runGenerate]);

  // Выбор файла: мягкая проверка размера (бек проверит окончательно).
  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    // Сбрасываем value, чтобы повторный выбор того же файла снова триггерил onChange.
    e.target.value = '';
    if (!picked) return;
    if (picked.size > MAX_FILE_BYTES) {
      setSendError('Файл больше 10 МБ. Выберите файл поменьше.');
      setFile(null);
      return;
    }
    setSendError(null);
    setFile(picked);
  }

  function resetFile() {
    setFile(null);
    setSendError(null);
  }

  function handleSend() {
    if (!body.trim()) return;
    setSendError(null);
    sendOffer.mutate(
      { body, file },
      {
        onSuccess: () => onClose(),
        onError: (e) => {
          setSendError((e as unknown as ApiError)?.error?.message || 'Не удалось отправить оффер');
        },
      },
    );
  }

  if (!isOpen) return null;

  const generating = generate.isPending;

  return (
    <div className="offer-modal-backdrop" onClick={onClose}>
      <div className="offer-modal" onClick={(e) => e.stopPropagation()}>
        <div className="offer-head">
          <div>
            <h3>Отправить оффер</h3>
            <div className="offer-sub">{candidateName}</div>
          </div>
          <button className="offer-close" onClick={onClose} aria-label="Закрыть">
            <Icon name="x" size={18} />
          </button>
        </div>

        <div className="offer-body">
          {genError ? (
            <div className="offer-gen-error">
              <div className="offer-error">{genError}</div>
              <button className="btn btn-secondary btn-sm" onClick={runGenerate}>
                <Icon name="refresh-cw" size={14} />
                Сгенерировать заново
              </button>
            </div>
          ) : generating ? (
            <div className="offer-loading">
              <Icon name="loader" size={18} className="offer-spin" />
              <span>Глафира готовит оффер…</span>
            </div>
          ) : (
            <>
              {header && <div className="offer-fixed">{header}</div>}
              <textarea
                className="offer-textarea"
                value={body}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Тело письма с оффером…"
                rows={12}
              />
              {footer && <div className="offer-fixed">{footer}</div>}
              <div className="offer-note">
                Приветствие и подпись берутся из «Настройки → Шаблоны сообщений» и добавятся
                к письму автоматически. Отредактируйте только тело оффера.
              </div>
              <div className="offer-note">
                Можно прикрепить один файл (PDF, Word, Excel, изображение или текст, до 10 МБ) —
                он уйдёт вложением в письме кандидату.
              </div>
            </>
          )}
        </div>

        {sendError && <div className="offer-error offer-error-send">{sendError}</div>}

        <div className="offer-actions">
          <div className="offer-file">
            <input
              ref={fileInputRef}
              type="file"
              className="offer-file-input"
              accept={FILE_ACCEPT}
              onChange={handleFilePick}
            />
            {file ? (
              <div className="offer-file-picked">
                <Icon name="paperclip" size={14} />
                <span className="offer-file-name">{file.name}</span>
                <span className="offer-file-size">{formatFileSize(file.size)}</span>
                <button
                  type="button"
                  className="offer-file-reset"
                  title="Убрать файл"
                  aria-label="Убрать файл"
                  onClick={resetFile}
                  disabled={sendOffer.isPending}
                >
                  <Icon name="x" size={13} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="offer-attach"
                onClick={() => fileInputRef.current?.click()}
                disabled={sendOffer.isPending}
              >
                <Icon name="paperclip" size={14} />
                Прикрепить файл
              </button>
            )}
          </div>
          <button className="btn btn-secondary btn-sm" onClick={onClose} disabled={sendOffer.isPending}>
            Отмена
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSend}
            disabled={generating || !!genError || !body.trim() || sendOffer.isPending}
          >
            {sendOffer.isPending ? 'Отправка…' : 'Отправить'}
          </button>
        </div>
      </div>
    </div>
  );
}
