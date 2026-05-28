type Props = {
  onSave?: () => void;
  onDiscard?: () => void;
};

export function DirtyBanner({ onSave, onDiscard }: Props) {
  return (
    <div className="dirty-banner">
      <div className="dirty-banner-content">
        <span className="dirty-banner-text">Не забудьте сохранить изменения</span>
        <div className="dirty-banner-actions">
          <button
            className="btn btn-secondary btn-sm"
            onClick={onDiscard}
            disabled={!onDiscard}
          >
            Отменить
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={onSave}
            disabled={!onSave}
          >
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}