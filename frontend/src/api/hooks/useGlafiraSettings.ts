import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { GlafiraSettingsOut } from '@/api/aliases';

// openapi не регенерён: бэк отдаёт turnover_source ('none' | 'bitrix24'),
// которого ещё нет в сгенерированном GlafiraSettingsOut — расширяем локально.
export type TurnoverSource = 'none' | 'bitrix24';

export type GlafiraSettings = GlafiraSettingsOut & {
  turnover_source?: TurnoverSource;
  default_rejection_text?: string | null;
  // openapi не реген (бек-фича оффера): приветствие/подпись письма с оффером.
  offer_email_header?: string | null;
  offer_email_footer?: string | null;
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
