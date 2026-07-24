// === Convenience aliases (manual, do not regenerate) ===
import type { components } from './types';

export type Vacancy = components['schemas']['VacancyDetail'];
export type VacancySidebarItem = components['schemas']['VacancySidebarItem'];
// openapi не регенерён — расширяем CandidateDetail локально (habr_contacts_opened v0.9.120)
export type Candidate = components['schemas']['CandidateDetail'] & { habr_contacts_opened?: boolean };
export type CandidateGridItem = components['schemas']['CandidateGridItem'];
export type CandidateDetail = components['schemas']['CandidateDetail'] & { habr_contacts_opened?: boolean };
export type ApplicationHistoryItem = components['schemas']['ApplicationHistoryItem'];
export type CandidateCardVacancy = components['schemas']['CandidateCardVacancy'];

// Manual types (not in openapi yet)
export interface AssignToVacancyRequest {
  vacancy_id: string;
  stage?: string;
}
export type UserMe = components['schemas']['UserMe'];
// openapi не регенерён — расширяем ApplicationRow локально (offer_sent_at: ISO-дата
// отправки оффера кандидату; читает бейдж «Отправлен ✓» в тулбаре карточки).
export type ApplicationRow = components['schemas']['ApplicationRow'] & { offer_sent_at?: string | null };
export type EvaluationOut = components['schemas']['EvaluationOut'];
export type VerificationOut = components['schemas']['VerificationOut'];
export type EmployeeListItem = components['schemas']['EmployeeListItem'];
export type AnalyticsResponse = components['schemas']['AnalyticsResponse'];
export type PulseSummary = components['schemas']['PulseSummary'];
export type AttentionItem = components['schemas']['AttentionItem'];
export type SourceItem = components['schemas']['SourceItem'];
export type AttentionHrItem = components['schemas']['AttentionHrItem'];

export type EventOut = components['schemas']['EventOut'];
export type MessageOut = components['schemas']['MessageOut'];
export type DocumentOut = components['schemas']['DocumentOut'];
export type CommentOut = components['schemas']['CommentOut'];

// Pulse module types
export type PulseKPI = components['schemas']['PulseKPI'];
export type EmployeeDetail = components['schemas']['EmployeeDetail'];
export type PlanItemOut = components['schemas']['PlanItemOut'];
export type SurveyOut = components['schemas']['SurveyOut'];
export type AlertOut = components['schemas']['AlertOut'];
export type NoteOut = components['schemas']['NoteOut'];

// Settings module types
export type ProfileOut = components['schemas']['ProfileOut'];
export type GlafiraSettingsOut = components['schemas']['GlafiraSettingsOut'];
export type RejectReasonOut = components['schemas']['RejectReasonOut'];
export type EmailTemplateOut = components['schemas']['EmailTemplateOut'];
export type SurveyTemplateOut = components['schemas']['SurveyTemplateOut'];
export type IntegrationOut = components['schemas']['IntegrationOut'];
export type BillingOut = components['schemas']['BillingOut'];

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// FastAPI generated KpiCard under namespaced keys because the same class name
// is defined in both app.schemas.home and app.schemas.analytics. Structures match;
// keeping two aliases so call sites are explicit about origin.
export type HomeKpi = components['schemas']['HomeKpi'];
export type HomeKpiCard = components['schemas']['app__schemas__home__KpiCard'];
export type AnalyticsKpiCard = components['schemas']['app__schemas__analytics__KpiCard'];
export type ChartData = components['schemas']['ChartData'];
export type TableData = components['schemas']['TableData'];
export type TableColumn = components['schemas']['TableColumn'];

// Analytics filters for frontend
export interface AnalyticsFilters {
  period: 'week' | 'month' | 'quarter' | 'year' | 'custom';
  date_from?: string;
  date_to?: string;
  vacancy_ids?: string[];
  recruiter_ids?: string[];
  compare?: boolean;
}

// Unified error envelope (TZ-0 §3.3)
export interface ApiError {
  error: {
    code: string;
    message: string;
    details: Array<{ field: string; message: string }> | null;
  };
}