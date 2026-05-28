import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Icon } from '@/components/ui/Icon';

export default function NotFoundPage() {
  const navigate = useNavigate();

  const handleGoHome = () => {
    navigate('/home');
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      gap: 'var(--space-4)',
      textAlign: 'center',
      padding: 'var(--space-6)'
    }}>
      <Icon name="alert-circle" size={64} style={{ color: 'var(--fg-3)' }} />

      <div>
        <h1 style={{
          fontSize: '24px',
          fontWeight: '600',
          margin: '0 0 var(--space-2) 0',
          color: 'var(--fg-1)'
        }}>
          Страница не найдена
        </h1>

        <p style={{
          fontSize: '16px',
          color: 'var(--fg-2)',
          margin: 0
        }}>
          Возможно, она была удалена или вы ошиблись адресом
        </p>
      </div>

      <Button
        variant="primary"
        onClick={handleGoHome}
      >
        <Icon name="home" size={16} />
        На главную
      </Button>
    </div>
  );
}