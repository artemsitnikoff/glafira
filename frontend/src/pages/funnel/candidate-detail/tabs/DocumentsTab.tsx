import { useRef, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useDocuments } from '@/api/hooks/useDocuments';
import { useUploadDocument, useDeleteDocument, useDownloadDocument } from '@/api/mutations/candidateDetail';
import type { ApiError } from '@/api/aliases';

type Props = {
  candidateId?: string;
  candidate?: any;
  fromPool?: boolean;
};

export function DocumentsTab({ candidateId, candidate }: Props) {
  const actualCandidateId = candidateId || candidate?.id;
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const { data: documents, isLoading } = useDocuments(actualCandidateId);
  const uploadMutation = useUploadDocument(actualCandidateId);
  const deleteMutation = useDeleteDocument();
  const downloadMutation = useDownloadDocument();

  function getFileTypeLabel(filename: string, file_type?: string): string {
    // Получаем расширение из имени файла
    const ext = filename.split('.').pop()?.toLowerCase() || '';

    // Приоритет file_type, если есть
    if (file_type) {
      const type = file_type.toLowerCase();
      if (type.includes('pdf')) return 'PDF';
      if (type.includes('image') || ['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(type)) return 'IMG';
      if (type.includes('word') || type.includes('document')) return 'DOC';
      if (type.includes('spreadsheet') || type.includes('excel')) return 'XLS';
    }

    // Определяем по расширению
    if (ext === 'pdf') return 'PDF';
    if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext)) return 'IMG';
    if (['doc', 'docx'].includes(ext)) return 'DOC';
    if (['xls', 'xlsx'].includes(ext)) return 'XLS';

    // Если расширение не более 4 символов, возвращаем в UPPERCASE
    if (ext && ext.length <= 4) {
      return ext.toUpperCase();
    }

    return 'FILE';
  }

  function formatFileMeta(doc: any): string {
    const parts: string[] = [];

    // Размер
    if (doc.size_bytes) {
      parts.push(`${Math.round(doc.size_bytes / 1024)} КБ`);
    }

    // Дата
    parts.push(new Date(doc.created_at).toLocaleDateString('ru'));

    // Источник
    parts.push(doc.source || '—');

    return parts.join(' · ');
  }

  function handleUploadClick() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files || []);
    files.forEach(file => {
      uploadMutation.mutate([file]);
    });
    e.target.value = '';
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(true);
  }

  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    files.forEach(file => {
      uploadMutation.mutate([file]);
    });
  }

  function handleDownload(documentId: string, filename: string) {
    downloadMutation.mutate(documentId, {
      onSuccess: ({ blob, filename: downloadFilename }) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = downloadFilename || filename || 'document';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      },
    });
  }

  function handleDelete(documentId: string) {
    if (confirm('Удалить документ? Это действие нельзя отменить.')) {
      deleteMutation.mutate(documentId);
    }
  }

  if (isLoading) {
    return (
      <div className="card-block">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '16px' }}>
          <Icon name="loader" size={16} />
          <span style={{ fontSize: '13px', color: 'var(--fg-2)' }}>Загружаются документы...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="card-block">
      <div className="docs-grid">
        {documents?.map((doc) => (
          <div key={doc.id} className="doc-tile">
            <div className="file-icon">{getFileTypeLabel(doc.filename, doc.file_type)}</div>
            <div className="file-info">
              <div className="file-name">{doc.filename}</div>
              <div className="file-meta">{formatFileMeta(doc)}</div>
            </div>
            <button
              className="icon-btn"
              onClick={() => handleDownload(doc.id, doc.filename)}
              disabled={downloadMutation.isPending}
            >
              <Icon name={downloadMutation.isPending ? "loader" : "download"} size={16} />
            </button>
            <button
              className="icon-btn"
              onClick={() => handleDelete(doc.id)}
              disabled={deleteMutation.isPending}
            >
              <Icon name={deleteMutation.isPending ? "loader" : "trash"} size={16} />
            </button>
          </div>
        ))}
        <div
          className={`doc-tile doc-drop ${dragOver ? 'doc-drop-dragover' : ''}`}
          onClick={handleUploadClick}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <Icon name="plus" size={20} />
          <span>Перетащите файл или нажмите</span>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        onChange={handleFileChange}
        style={{ display: 'none' }}
      />

      {uploadMutation.isError && (
        <div style={{ marginTop: '10px', color: 'var(--stage-rejected)', fontSize: '12px' }}>
          {(uploadMutation.error as unknown as ApiError)?.error?.message || 'Не удалось загрузить файл'}
        </div>
      )}
    </div>
  );
}