// === Convenience aliases (manual, do not regenerate) ===
import type { components } from './types';

export type Vacancy = components['schemas']['VacancyDetail'];
export type VacancySidebarItem = components['schemas']['VacancySidebarItem'];
export type Candidate = components['schemas']['CandidateDetail'];
export type CandidateGridItem = components['schemas']['CandidateGridItem'];
export type UserMe = components['schemas']['UserMe'];
export type ApplicationRow = components['schemas']['ApplicationRow'];
export type EvaluationOut = components['schemas']['EvaluationOut'];
export type VerificationOut = components['schemas']['VerificationOut'];
export type EmployeeListItem = components['schemas']['EmployeeListItem'];
export type AnalyticsResponse = components['schemas']['AnalyticsResponse'];
export type PulseSummary = components['schemas']['PulseSummary'];

// FastAPI generated KpiCard under namespaced keys because the same class name
// is defined in both app.schemas.home and app.schemas.analytics. Structures match;
// keeping two aliases so call sites are explicit about origin.
export type HomeKpi = components['schemas']['HomeKpi'];
export type HomeKpiCard = components['schemas']['app__schemas__home__KpiCard'];
export type AnalyticsKpiCard = components['schemas']['app__schemas__analytics__KpiCard'];

// Unified error envelope (TZ-0 §3.3)
export interface ApiError {
  error: {
    code: string;
    message: string;
    details: Array<{ field: string; message: string }> | null;
  };
}