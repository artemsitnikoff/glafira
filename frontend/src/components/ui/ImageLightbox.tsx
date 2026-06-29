import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from '@/components/ui/Icon';
import './ImageLightbox.css';

type Props = {
  src: string;
  alt?: string;
  onClose: () => void;
};

/**
 * Лайтбокс-оверлей: показывает изображение в полный размер поверх всего UI.
 * Закрытие: клик по затемнённому фону, Esc, крестик. Клик по самому
 * изображению НЕ закрывает (stopPropagation). Рендерится через портал в
 * document.body, чтобы оверлей не обрезался родительскими overflow/transform.
 */
export function ImageLightbox({ src, alt = '', onClose }: Props) {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return createPortal(
    <div className="img-lightbox-overlay" onClick={onClose}>
      <button
        type="button"
        className="img-lightbox-close"
        onClick={onClose}
        title="Закрыть"
        aria-label="Закрыть"
      >
        <Icon name="x" size={22} />
      </button>
      <img
        className="img-lightbox-img"
        src={src}
        alt={alt}
        onClick={(e) => e.stopPropagation()}
      />
    </div>,
    document.body
  );
}
