import { create } from 'zustand';

/**
 * Стор попапа «Чаты» — один инстанс на приложение (попап монтируется в AppLayout).
 * Кнопка в сайдбаре тогглит `open`; `openWith(candidateId)` открывает попап и
 * предвыбирает диалог (задел под будущую кнопку «Написать кандидату»).
 */
interface ChatStore {
  open: boolean;
  selectedCandidateId: string | null;
  openWith: (candidateId?: string) => void;
  close: () => void;
  toggle: () => void;
  select: (candidateId: string | null) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  open: false,
  selectedCandidateId: null,
  openWith: (candidateId) => set({ open: true, selectedCandidateId: candidateId ?? null }),
  close: () => set({ open: false }),
  toggle: () => set((s) => ({ open: !s.open })),
  select: (candidateId) => set({ selectedCandidateId: candidateId }),
}));
