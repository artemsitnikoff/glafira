import { CandidateDetail } from './candidate-detail/CandidateDetail';
import type { components } from '@/api/types';

type ApplicationRow = components['schemas']['ApplicationRow'] & {
  salary_from?: number | null;
  salary_to?: number | null;
};

type Props = {
  application: ApplicationRow | null;
  onClose: () => void;
  isResolving?: boolean;
  vacancyId?: string;
};

export default function DetailHost({ application, onClose, isResolving, vacancyId }: Props) {
  return (
    <div className="cand-detail">
      <CandidateDetail
        application={application}
        onClose={onClose}
        isResolving={isResolving}
        vacancyId={vacancyId}
      />
    </div>
  );
}