import { AlertTriangle } from 'lucide-react';
import './SubscriptionExpiredScreen.css';

export default function SubscriptionExpiredScreen() {
  return (
    <div className="sub-expired">
      <div className="sub-expired__card">
        <div className="sub-expired__icon">
          <AlertTriangle size={48} />
        </div>
        <h1 className="sub-expired__title">
          Тариф вашей организации истёк
        </h1>
        <p className="sub-expired__subtitle">
          Обратитесь к администратору сервиса.
        </p>
      </div>
    </div>
  );
}