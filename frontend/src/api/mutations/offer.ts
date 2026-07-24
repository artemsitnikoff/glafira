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

type OfferSendRequest = { body: string };
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
 * Отправка оффера кандидату на email. Фронт шлёт только отредактированное тело —
 * сервер сам обрамляет header + body + footer и отправляет письмо.
 * candidateId нужен для инвалидации кэша Чата (оффер отражается сообщением) и ленты.
 */
export function useSendOffer(applicationId: string, candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: OfferSendRequest): Promise<OfferSendResponse> => {
      const res = await api.post(`/applications/${applicationId}/offer/send`, data);
      return res.data as OfferSendResponse;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates', candidateId, 'messages'] });
      queryClient.invalidateQueries({ queryKey: ['home', 'events'] });
    },
  });
}
