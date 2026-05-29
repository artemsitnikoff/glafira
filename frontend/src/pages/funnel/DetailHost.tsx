import { CandidateDetail } from './candidate-detail/CandidateDetail';
import type { components } from '@/api/types';

type ApplicationRow = components['schemas']['ApplicationRow'];

type Props = {
  application: ApplicationRow | null;
  onClose: () => void;
  isResolving?: boolean;
};

export default function DetailHost({ application, onClose, isResolving }: Props) {
  return (
    <div className="cand-detail">
      <CandidateDetail
        application={application}
        onClose={onClose}
        isResolving={isResolving}
      />
    </div>
  );
}