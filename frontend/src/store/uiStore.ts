import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UiState {
  vacanciesOpen: boolean;
  analyticsOpen: boolean;
  vacancySearch: string;
  analyticsReportId: string;
  toggleVacancies: () => void;
  toggleAnalytics: () => void;
  setVacancySearch: (v: string) => void;
  setAnalyticsReportId: (id: string) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      vacanciesOpen: true,
      analyticsOpen: false,
      vacancySearch: '',
      analyticsReportId: 'overview',
      toggleVacancies: () => set((s) => ({ vacanciesOpen: !s.vacanciesOpen })),
      toggleAnalytics: () => set((s) => ({ analyticsOpen: !s.analyticsOpen })),
      setVacancySearch: (v) => set({ vacancySearch: v }),
      setAnalyticsReportId: (id) => set({ analyticsReportId: id }),
    }),
    { name: 'glafira-ui' }
  )
);