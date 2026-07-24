import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';

// openapi не реген (бек-фича оффера) — эндпоинты /applications/{id}/offer/*
// ещё не в сгенерированном контракте, типы описываем локально.
export type OfferGenerateResponse = {
  /** Сгенерированное LLM тело оффера (плоский текст с \n, редактируемое). */
  body: string;
  /** Приветствие из настроек — read-only обрамление письма. */
  header: string;
  /** Подпись из настроек — read-only обрамление письма. */
  footer: string;
};

type OfferSendRequest = { body: string; file?: File | null };
type OfferSendResponse = { status: string };

/**
 * Генерация тела оффера (LLM) — вызывается при открытии попапа.
 * Может отвечать не мгновенно → показываем состояние загрузки в модалке.
 */
export function useGenerateOffer(applicationId: string) {
  return useMutation({
    mutationFn: async (): Promise<OfferGenerateResponse> => {
      const res = await api.post(`/applications/${applicationId}/offer/generate`);
      return res.data as OfferGenerateResponse;
    },
  });
}

/**
 * Отправка оффера кандидату на email. Фронт шлёт отредактированное тело и
 * НЕОБЯЗАТЕЛЬНОЕ вложение (один файл) — сервер сам обрамляет header + body + footer,
 * прикладывает файл и отправляет письмо. Тело уходит multipart/form-data (поля
 * `body` + опциональный `file`), идиом загрузки — как в useUploadDocument.
 * candidateId нужен для инвалидации кэша Чата (оффер отражается сообщением) и ленты.
 */
export function useSendOffer(applicationId: string, candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ body, file }: OfferSendRequest): Promise<OfferSendResponse> => {
      const fd = new FormData();
      fd.append('body', body);
      if (file) fd.append('file', file);
      // Content-Type: multipart/form-data — идиом проекта (useUploadDocument/useParseResume).
      // Для FormData браузерный адаптер axios сам подставит header с boundary, значение
      // без boundary не перебивает его (проверено — загрузка документов работает так же).
      const res = await api.post(`/applications/${applicationId}/offer/send`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data as OfferSendResponse;
    },
    onSuccess: () => {
      // Зеркалим ПдН + инвалидируем воронку: ApplicationRow.offer_sent_at, который
      // читает бейдж «Отправлен ✓», живёт в списке заявок ['vacancies', id, 'applications', ...].
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'messages'] });
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId] });
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['vacancies'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}
