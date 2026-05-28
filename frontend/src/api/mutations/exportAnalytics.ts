import { useMutation } from '@tanstack/react-query';
import { api } from '@/api/client';
import type { AnalyticsFilters } from '@/api/aliases';

export interface ExportAnalyticsParams extends AnalyticsFilters {
  report: string;
  format: 'xlsx';
}

async function exportAnalytics(params: ExportAnalyticsParams): Promise<void> {
  const urlParams = new URLSearchParams();

  // Add all parameters
  urlParams.append('report', params.report);
  urlParams.append('format', params.format);
  urlParams.append('period', params.period);

  if (params.date_from) urlParams.append('date_from', params.date_from);
  if (params.date_to) urlParams.append('date_to', params.date_to);
  if (params.compare !== undefined) urlParams.append('compare', params.compare.toString());

  // Add array parameters
  if (params.vacancy_ids?.length) {
    params.vacancy_ids.forEach(id => urlParams.append('vacancy_ids', id));
  }
  if (params.recruiter_ids?.length) {
    params.recruiter_ids.forEach(id => urlParams.append('recruiter_ids', id));
  }

  const response = await api.get(`/analytics/export?${urlParams.toString()}`, {
    responseType: 'blob',
  });

  // Extract filename from Content-Disposition header or use fallback
  let filename = `analytics_${params.report}.xlsx`;
  const contentDisposition = response.headers['content-disposition'];
  if (contentDisposition) {
    const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
    if (matches?.[1]) {
      filename = matches[1].replace(/['"]/g, '');
    }
  }

  // Create download link and click it
  const blob = response.data as Blob;
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export function useExportAnalytics() {
  return useMutation({
    mutationFn: exportAnalytics,
  });
}