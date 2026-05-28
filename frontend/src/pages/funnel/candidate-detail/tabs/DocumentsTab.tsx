import { useRef, useState } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useDocuments } from '@/api/hooks/useDocuments';
import { useUploadDocument, useDeleteDocument, useDownloadDocument } from '@/api/mutations/candidateDetail';

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
      <div className="tab-content">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
          <Icon name="loader" size={24} />
          <p>Загружаются документы...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="tab-content">
      <h2 style={{ margin: '0 0 var(--space-4) 0', fontSize: '18px', fontWeight: '600' }}>
        Документы
      </h2>

      {/* Upload Zone */}
      <div
        className={`upload-zone ${dragOver ? 'upload-zone--dragover' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="upload-zone__icon">
          <Icon name="upload" size={32} />
        </div>
        <p className="upload-zone__text">
          Перетащите файлы сюда или нажмите кнопку для выбора
        </p>
        <button
          className="upload-zone__btn"
          onClick={handleUploadClick}
          disabled={uploadMutation.isPending}
        >
          <Icon name={uploadMutation.isPending ? "loader" : "plus"} size={16} />
          Выбрать файлы
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileChange}
          className="upload-zone__input"
        />
      </div>

      {uploadMutation.isError && (
        <div style={{ marginBottom: 'var(--space-4)', color: 'var(--stage-rejected)', fontSize: '14px' }}>
          Ошибка загрузки: {uploadMutation.error?.message}
        </div>
      )}

      {/* Documents List */}
      {documents && documents.length > 0 ? (
        <div className="list-container">
          {documents.map((doc) => (
            <div key={doc.id} className="list-item">
              <div className="list-item__header">
                <h4 className="list-item__title">
                  <Icon name="file" size={16} style={{ marginRight: 'var(--space-2)' }} />
                  {doc.filename}
                </h4>
                <span className="list-item__meta">
                  {doc.source && (
                    <span style={{ marginRight: 'var(--space-2)', textTransform: 'uppercase', fontSize: '10px' }}>
                      {doc.source}
                    </span>
                  )}
                  {new Date(doc.created_at).toLocaleDateString('ru')}
                </span>
              </div>
              <div className="list-item__content">
                <p style={{ margin: 0, color: 'var(--fg-3)', fontSize: '14px' }}>
                  {doc.size_bytes ? `${Math.round(doc.size_bytes / 1024)} КБ` : 'Размер неизвестен'}
                  {doc.file_type && ` • ${doc.file_type}`}
                </p>
              </div>
              <div className="list-item__actions">
                <button
                  className="list-item__btn"
                  onClick={() => handleDownload(doc.id, doc.filename)}
                  disabled={downloadMutation.isPending}
                >
                  <Icon name={downloadMutation.isPending ? "loader" : "download"} size={12} />
                  Скачать
                </button>
                <button
                  className="list-item__btn list-item__btn--danger"
                  onClick={() => handleDelete(doc.id)}
                  disabled={deleteMutation.isPending}
                >
                  <Icon name={deleteMutation.isPending ? "loader" : "trash"} size={12} />
                  Удалить
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty-state">
          <Icon name="file" size={48} className="empty-state__icon" />
          <p className="empty-state__text">Документов пока нет</p>
        </div>
      )}
    </div>
  );
}