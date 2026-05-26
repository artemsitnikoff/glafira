import { create } from 'zustand';

interface UiState {
  // На этом шаге пусто — store существует для дальнейшего наполнения
  // Sidebar-state, modal-state, etc. — добавятся со следующими шагами
  _placeholder?: never;
}

export const useUiStore = create<UiState>(() => ({}));