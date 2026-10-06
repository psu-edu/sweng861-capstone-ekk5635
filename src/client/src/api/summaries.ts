import { apiRequest } from '@/api/client'

// The backend's SummarySource: one filing a summary's figures were computed from.
export interface SummarySource {
  concept: string
  accn: string
  form: string
  filed: string
  url: string
}

// The backend's CoverageSummaryRead. indicators is exactly what the model was given.
export interface CoverageSummary {
  period_end: string
  indicators: Record<string, number | string | null>
  summary: string
  model: string
  sources: SummarySource[]
  generated_at: string
}

// The backend's CollectionReport: a count, not the rows themselves.
export interface CollectionReport {
  coverage_id: number
  collected: number
  concepts: string[]
}

function summaryPath(coverageId: string): string {
  return `/api/coverages/${encodeURIComponent(coverageId)}/summary`
}

// Reads the stored summary only; a 404 means none has been generated yet.
export function getSummary(coverageId: string): Promise<CoverageSummary> {
  return apiRequest<CoverageSummary>(summaryPath(coverageId))
}

// Calls the LLM on the server and replaces any earlier summary.
export function generateSummary(coverageId: string): Promise<CoverageSummary> {
  return apiRequest<CoverageSummary>(summaryPath(coverageId), { method: 'POST' })
}

// The summary is computed from these figures, so they must be collected first.
export function collectFinancials(coverageId: string): Promise<CollectionReport> {
  return apiRequest<CollectionReport>(
    `/api/coverages/${encodeURIComponent(coverageId)}/financials`,
    { method: 'POST' },
  )
}
