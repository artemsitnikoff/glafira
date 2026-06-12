import { useMutation } from '@tanstack/react-query';
import { api } from '../client';

type ResumeFormat = 'pdf' | 'docx';

interface DownloadResumeParams {
  candidateId: string;
  format: ResumeFormat;
  fileName?: string;
}

function parseContentDisposition(header: string | undefined): string | null {
  if (!header) return null;

  // Ищем filename*=UTF-8''<encoded-filename> (RFC 5987)
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      // Fallback if decoding fails
    }
  }

  // Ищем обычный filename="filename" или filename=filename
  const normalMatch = header.match(/filename=["']?([^"';]+)["']?/);
  if (normalMatch) {
    return normalMatch[1];
  }

  return null;
}

async function downloadResume({ candidateId, format, fileName }: DownloadResumeParams) {
  const response = await api.get(`/candidates/${candidateId}/resume`, {
    params: { format },
    responseType: 'blob',
  });

  // Извлекаем имя файла из Content-Disposition или используем fallback
  const contentDisposition = response.headers['content-disposition'] as string | undefined;
  const downloadFileName =
    parseContentDisposition(contentDisposition) ||
    fileName ||
    `resume.${format}`;

  // Создаем blob и скачиваем
  const contentType = response.headers['content-type'] as string | undefined;
  const blob = new Blob([response.data], {
    type: contentType || (format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
  });

  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = downloadFileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  return downloadFileName;
}

export function useResumeDownload() {
  return useMutation({
    mutationFn: downloadResume,
  });
}