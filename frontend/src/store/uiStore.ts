import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UiState {
  vacanciesOpen: boolean;
  analyticsOpen: boolean;
  vacancySearch: string;
  analyticsReportId: string;
  greeting: boolean;
  kpiExtended: boolean;
  showSources: boolean;
  toggleVacancies: () => void;
  toggleAnalytics: () => void;
  setVacancySearch: (v: string) => void;
  setAnalyticsReportId: (id: string) => void;
  setGreeting: (v: boolean) => void;
  setKpiExtended: (v: boolean) => void;
  setShowSources: (v: boolean) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      vacanciesOpen: true,
      analyticsOpen: false,
      vacancySearch: '',
      analyticsReportId: 'overview',
      greeting: false,
      kpiExtended: false,
      showSources: true,
      toggleVacancies: () => set((s) => ({ vacanciesOpen: !s.vacanciesOpen })),
      toggleAnalytics: () => set((s) => ({ analyticsOpen: !s.analyticsOpen })),
      setVacancySearch: (v) => set({ vacancySearch: v }),
      setAnalyticsReportId: (id) => set({ analyticsReportId: id }),
      setGreeting: (v) => set({ greeting: v }),
      setKpiExtended: (v) => set({ kpiExtended: v }),
      setShowSources: (v) => set({ showSources: v }),
      // TODO(post-MVP): UI-панель тыков (settings dropdown в шапке)
    }),
    { name: 'glafira-ui' }
  )
);