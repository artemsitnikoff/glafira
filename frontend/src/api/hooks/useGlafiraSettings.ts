import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { GlafiraSettingsOut } from '@/api/aliases';

// openapi не регенерён: бэк отдаёт turnover_source ('none' | 'bitrix24'),
// которого ещё нет в сгенерированном GlafiraSettingsOut — расширяем локально.
export type TurnoverSource = 'none' | 'bitrix24';

export type GlafiraSettings = GlafiraSettingsOut & {
  turnover_source?: TurnoverSource;
};

export function useGlafiraSettings() {
  return useQuery({
    queryKey: ['settings', 'glafira'],
    queryFn: async (): Promise<GlafiraSettings> => {
      const response = await api.get('/settings/glafira');
      return response.data as GlafiraSettings;
    },
  });
}
