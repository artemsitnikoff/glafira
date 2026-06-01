import { useState, useMemo } from 'react';
import { Icon } from '@/components/ui/Icon';
import { useB24Departments, useB24ImportCandidates, useB24ImportUsers } from '@/api/hooks/useBitrix24Import';
import type { B24ImportResult } from '@/api/hooks/useBitrix24Import';

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Администратор' },
  { value: 'recruiter', label: 'Рекрутёр' },
  { value: 'manager', label: 'Нанимающий менеджер' },
];

type ImportStep = 'select' | 'result';

export function BitrixImportModal({ isOpen, onClose }: Props) {
  const [nameFilter, setNameFilter] = useState('');
  const [departmentFilter, setDepartmentFilter] = useState('');
  const [selectedUsers, setSelectedUsers] = useState<Set<string>>(new Set());
  const [selectedRole, setSelectedRole] = useState('recruiter');
  const [step, setStep] = useState<ImportStep>('select');
  const [importResult, setImportResult] = useState<B24ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data: departments = [], isLoading: departmentsLoading } = useB24Departments();
  const { data: candidates = [], isLoading: candidatesLoading } = useB24ImportCandidates();
  const importMutation = useB24ImportUsers();

  const departmentOptions = useMemo(() => {
    return [
      { value: '', label: 'Все отделы' },
      ...departments.map((dept) => ({ value: dept.id, label: dept.name }))
    ];
  }, [departments]);

  const filteredCandidates = useMemo(() => {
    return candidates.filter((candidate) => {
      const nameMatch = !nameFilter ||
        `${candidate.name} ${candidate.last_name}`.toLowerCase().includes(nameFilter.toLowerCase());
      const deptMatch = !departmentFilter || candidate.department_ids.includes(departmentFilter);
      return nameMatch && deptMatch;
    });
  }, [candidates, nameFilter, departmentFilter]);

  const handleSelectAll = () => {
    const selectableUsers = filteredCandidates.filter(c => c.email).map(c => c.b24_id);
    if (selectedUsers.size === selectableUsers.length) {
      setSelectedUsers(new Set());
    } else {
      setSelectedUsers(new Set(selectableUsers));
    }
  };

  const handleUserToggle = (userId: string) => {
    const newSelected = new Set(selectedUsers);
    if (newSelected.has(userId)) {
      newSelected.delete(userId);
    } else {
      newSelected.add(userId);
    }
    setSelectedUsers(newSelected);
  };

  const handleImport = async () => {
    if (selectedUsers.size === 0) return;

    setError(null);
    try {
      const result = await importMutation.mutateAsync({
        b24_user_ids: Array.from(selectedUsers),
        role: selectedRole,
        delivery: 'email'
      });
      setImportResult(result);
      setStep('result');
    } catch (err: any) {
      setError(err?.error?.message || 'Произошла ошибка при импорте');
    }
  };

  const handleClose = () => {
    setStep('select');
    setImportResult(null);
    setError(null);
    setSelectedUsers(new Set());
    setNameFilter('');
    setDepartmentFilter('');
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content modal-lg" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Импорт пользователей из Битрикс24</h2>
          <button
            type="button"
            onClick={handleClose}
            className="modal-close"
            aria-label="Закрыть"
          >
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="modal-body">
          {step === 'select' && (
            <>
              <div className="import-filters">
                <div className="import-filter-row">
                  <div className="import-filter">
                    <label>Поиск по имени</label>
                    <input
                      type="text"
                      placeholder="Введите имя или фамилию..."
                      value={nameFilter}
                      onChange={(e) => setNameFilter(e.target.value)}
                      className="form-input"
                    />
                  </div>
                  <div className="import-filter">
                    <label>Отдел</label>
                    <select
                      value={departmentFilter}
                      onChange={(e) => setDepartmentFilter(e.target.value)}
                      className="form-select"
                      disabled={departmentsLoading}
                    >
                      {departmentOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="import-filter-row">
                  <div className="import-filter">
                    <label>Роль для назначения</label>
                    <select
                      value={selectedRole}
                      onChange={(e) => setSelectedRole(e.target.value)}
                      className="form-select"
                    >
                      {ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {error && (
                <div className="error-banner">
                  <Icon name="alert-circle" size={16} />
                  <span>{error}</span>
                </div>
              )}

              <div className="import-list">
                <div className="import-list-header">
                  <div className="import-select-all">
                    <input
                      type="checkbox"
                      checked={filteredCandidates.filter(c => c.email).length > 0 &&
                        selectedUsers.size === filteredCandidates.filter(c => c.email).length}
                      onChange={handleSelectAll}
                      disabled={candidatesLoading}
                    />
                    <label>
                      Выбрать всех ({filteredCandidates.filter(c => c.email).length})
                    </label>
                  </div>
                  <div className="import-selected-count">
                    Выбрано: {selectedUsers.size}
                  </div>
                </div>

                {candidatesLoading ? (
                  <div className="import-loading">Загрузка...</div>
                ) : (
                  <div className="import-candidates">
                    {filteredCandidates.map((candidate) => {
                      const canSelect = !!candidate.email;
                      const isSelected = selectedUsers.has(candidate.b24_id);

                      return (
                        <div
                          key={candidate.b24_id}
                          className={`import-candidate ${!canSelect ? 'disabled' : ''}`}
                        >
                          <div className="import-candidate-checkbox">
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleUserToggle(candidate.b24_id)}
                              disabled={!canSelect}
                            />
                          </div>
                          <div className="import-candidate-info">
                            <div className="import-candidate-name">
                              {candidate.name} {candidate.last_name}
                            </div>
                            <div className="import-candidate-details">
                              {candidate.position && (
                                <span className="import-candidate-position">
                                  {candidate.position}
                                </span>
                              )}
                              <span className="import-candidate-department">
                                {candidate.department_name}
                              </span>
                              {candidate.email ? (
                                <span className="import-candidate-email">
                                  {candidate.email}
                                </span>
                              ) : (
                                <span className="import-candidate-no-email">
                                  нет email
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </>
          )}

          {step === 'result' && importResult && (
            <div className="import-result">
              <div className="import-result-summary">
                <Icon name="check-circle" size={20} />
                <h3>Импорт завершён</h3>
              </div>

              <div className="import-result-stats">
                {importResult.created.length > 0 && (
                  <div className="import-stat">
                    <strong>Создано пользователей:</strong> {importResult.created.length}
                    <div className="import-stat-list">
                      {importResult.created.map((user) => (
                        <div key={user.email}>{user.full_name} ({user.email})</div>
                      ))}
                    </div>
                  </div>
                )}

                {importResult.emailed.length > 0 && (
                  <div className="import-stat">
                    <strong>Отправлены приглашения:</strong> {importResult.emailed.length}
                    <div className="import-stat-list">
                      {importResult.emailed.map((email) => (
                        <div key={email}>{email}</div>
                      ))}
                    </div>
                  </div>
                )}

                {importResult.shown.length > 0 && (
                  <div className="import-stat">
                    <strong>Не удалось отправить письма (временные пароли):</strong>
                    <div className="import-stat-passwords">
                      {importResult.shown.map((user) => (
                        <div key={user.email} className="temp-password-item">
                          <strong>{user.full_name}</strong> ({user.email})
                          <div className="temp-password">
                            Пароль: <code>{user.temp_password}</code>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {importResult.skipped.length > 0 && (
                  <div className="import-stat">
                    <strong>Пропущено:</strong> {importResult.skipped.length}
                    <div className="import-stat-list">
                      {importResult.skipped.map((skipped, idx) => (
                        <div key={idx}>{skipped.name} — {skipped.reason}</div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {step === 'select' ? (
            <>
              <button
                type="button"
                onClick={handleClose}
                className="btn btn-secondary"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={handleImport}
                className="btn btn-primary"
                disabled={selectedUsers.size === 0 || importMutation.isPending}
              >
                {importMutation.isPending ? 'Импортируем...' : `Импортировать ${selectedUsers.size}`}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={handleClose}
              className="btn btn-primary"
            >
              Закрыть
            </button>
          )}
        </div>
      </div>
    </div>
  );
}