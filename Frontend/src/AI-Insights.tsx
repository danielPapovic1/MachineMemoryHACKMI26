import { useCallback, useEffect, useMemo, useState } from 'react'

const API_BASE_URL = 'http://localhost:8000'
const EMPTY_VALUE = 'No values yet'
const NOT_REPORTED = 'Not reported'

type AIType = 'machine_snapshot' | 'deep_review'
type Tone = 'green' | 'amber' | 'red' | 'neutral'

type AIInsightsSummary = {
  totalResponses?: number | null
  machineSnapshotResponses?: number | null
  deepReviewResponses?: number | null
  machinesWithMachineSnapshots?: number | null
  machinesWithDeepReviews?: number | null
  latestResponseTime?: string | null
}

type AIInsightMachineCard = {
  machineId?: string | null
  machineName?: string | null
  zone?: string | null
  latestResponseTime?: string | null
  latestSummary?: string | null
  responseCount?: number | null
  latestStatus?: string | null
  latestConfidence?: string | number | null
  source?: string | null
}

type AIInsightGroup = {
  aiType?: AIType | string
  label?: string | null
  responseCount?: number | null
  machineCount?: number | null
  machines?: AIInsightMachineCard[]
}

type AIInsightsPageResponse = {
  summary?: AIInsightsSummary | null
  groups?: Partial<Record<AIType, AIInsightGroup>> | null
  machine_snapshot?: AIInsightMachineCard[]
  deep_review?: AIInsightMachineCard[]
}

type MachineSnapshotFields = {
  urgency?: string | null
  keyAnomaly?: string | null
  suggestedNextStep?: string | null
  predictedDowntimeIfIgnored?: string | null
  downtimeReasoning?: string | null
  evidence?: unknown
}

type DeepReviewFields = {
  rootCause?: unknown
  patternFindings?: unknown
  maintenanceRecommendation?: unknown
  historicalMatch?: unknown
  riskOutlook?: unknown
  downtimeExposure?: unknown
  finalRecommendation?: unknown
  confidence?: unknown
}

type AIInsightResponseRecord = {
  responseId?: string | null
  machineId?: string | null
  machineName?: string | null
  machineType?: string | null
  zone?: string | null
  aiType?: AIType | string | null
  createdAt?: string | null
  status?: string | null
  summary?: string | null
  confidence?: string | number | null
  source?: string | null
  modelOrAgent?: string | null
  responseText?: string | null
  snapshot?: MachineSnapshotFields | null
  deepReview?: DeepReviewFields | null
}

type AIInsightDetailResponse = {
  machineId?: string | null
  machineName?: string | null
  zone?: string | null
  aiType?: AIType | string | null
  responseCount?: number | null
  limit?: number | null
  offset?: number | null
  latest?: AIInsightResponseRecord | null
  responses?: AIInsightResponseRecord[]
}

type SectionConfig = {
  type: AIType
  number: string
  title: string
  subtitle: string
  listTitle: string
  historyTitle: string
  emptyTitle: string
  emptyDetail: string
  sourceLabel: string
}

const SECTION_CONFIGS: SectionConfig[] = [
  {
    type: 'machine_snapshot',
    number: '1.',
    title: 'Machine Snapshot (Watsonx)',
    subtitle: 'Fast AI summaries for quick situational awareness.',
    listTitle: 'Snapshot Responses',
    historyTitle: 'Snapshot History',
    emptyTitle: 'No Machine Snapshot responses yet',
    emptyDetail: 'Select a machine with saved snapshot responses to view its timeline.',
    sourceLabel: 'Model',
  },
  {
    type: 'deep_review',
    number: '2.',
    title: 'Deep Review (Orchestrate Agent)',
    subtitle: 'In-depth AI analysis with root cause, patterns, and recommendations.',
    listTitle: 'Deep Review Responses',
    historyTitle: 'Deep Review History',
    emptyTitle: 'No Deep Review responses yet',
    emptyDetail: 'Select a machine with saved deep review responses to view its timeline.',
    sourceLabel: 'Agent',
  },
]

const INITIAL_SELECTED_IDS: Record<AIType, string | null> = {
  machine_snapshot: null,
  deep_review: null,
}

const INITIAL_DETAILS: Record<AIType, AIInsightDetailResponse | null> = {
  machine_snapshot: null,
  deep_review: null,
}

const INITIAL_LOADING: Record<AIType, boolean> = {
  machine_snapshot: false,
  deep_review: false,
}

const INITIAL_ERRORS: Record<AIType, string | null> = {
  machine_snapshot: null,
  deep_review: null,
}

function AIInsightsPage() {
  const [pageData, setPageData] = useState<AIInsightsPageResponse | null>(null)
  const [selectedIds, setSelectedIds] = useState<Record<AIType, string | null>>(INITIAL_SELECTED_IDS)
  const [details, setDetails] = useState<Record<AIType, AIInsightDetailResponse | null>>(INITIAL_DETAILS)
  const [detailLoading, setDetailLoading] = useState<Record<AIType, boolean>>(INITIAL_LOADING)
  const [detailErrors, setDetailErrors] = useState<Record<AIType, string | null>>(INITIAL_ERRORS)
  const [isPageLoading, setIsPageLoading] = useState(true)
  const [pageError, setPageError] = useState<string | null>(null)

  const loadPage = useCallback(async () => {
    setIsPageLoading(true)
    setPageError(null)

    try {
      const data = await fetchAIJson<AIInsightsPageResponse>('/api/ai-insights')
      setPageData(data)
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Unable to load saved AI insights'
      setPageError(message)
      setPageData(null)
      setSelectedIds(INITIAL_SELECTED_IDS)
      setDetails(INITIAL_DETAILS)
    } finally {
      setIsPageLoading(false)
    }
  }, [])

  const machinesByType = useMemo<Record<AIType, AIInsightMachineCard[]>>(() => ({
    machine_snapshot: sortMachines(
      pageData?.groups?.machine_snapshot?.machines ?? pageData?.machine_snapshot ?? [],
    ),
    deep_review: sortMachines(
      pageData?.groups?.deep_review?.machines ?? pageData?.deep_review ?? [],
    ),
  }), [pageData])

  const loadDetail = useCallback(async (aiType: AIType, machineId: string) => {
    setDetailLoading((current) => ({ ...current, [aiType]: true }))
    setDetailErrors((current) => ({ ...current, [aiType]: null }))

    try {
      const detail = await fetchAIJson<AIInsightDetailResponse>(
        `/api/ai-insights/${encodeURIComponent(machineId)}?ai_type=${aiType}`,
      )
      const responses = sortResponses(
        (detail.responses ?? []).filter((response) => normalizeAIType(response.aiType) === aiType),
      )

      setDetails((current) => ({
        ...current,
        [aiType]: {
          ...detail,
          aiType,
          responses,
          latest: responses[0] ?? null,
        },
      }))
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Unable to load machine AI history'
      setDetailErrors((current) => ({ ...current, [aiType]: message }))
      setDetails((current) => ({ ...current, [aiType]: null }))
    } finally {
      setDetailLoading((current) => ({ ...current, [aiType]: false }))
    }
  }, [])

  useEffect(() => {
    void loadPage()
  }, [loadPage])

  useEffect(() => {
    setSelectedIds((current) => {
      const next = { ...current }
      let changed = false

      SECTION_CONFIGS.forEach((config) => {
        const machines = machinesByType[config.type]
        const currentId = current[config.type]
        const currentStillExists = currentId
          ? machines.some((machine) => machineIdFor(machine) === currentId)
          : false
        const nextId = currentStillExists ? currentId : machineIdFor(machines[0])

        if (next[config.type] !== nextId) {
          next[config.type] = nextId
          changed = true
        }
      })

      return changed ? next : current
    })
  }, [machinesByType])

  useEffect(() => {
    const machineId = selectedIds.machine_snapshot
    if (!machineId) {
      setDetails((current) => ({ ...current, machine_snapshot: null }))
      return
    }

    void loadDetail('machine_snapshot', machineId)
  }, [loadDetail, selectedIds.machine_snapshot])

  useEffect(() => {
    const machineId = selectedIds.deep_review
    if (!machineId) {
      setDetails((current) => ({ ...current, deep_review: null }))
      return
    }

    void loadDetail('deep_review', machineId)
  }, [loadDetail, selectedIds.deep_review])

  const handleSelectMachine = useCallback((aiType: AIType, machineId: string) => {
    setSelectedIds((current) => ({ ...current, [aiType]: machineId }))
  }, [])

  return (
    <section className="ai-insights-page" aria-label="AI Insights">
      {pageError ? (
        <div className="ai-insights-alert">
          <div>
            <strong>Unable to load saved AI insights</strong>
            <p>{pageError}</p>
          </div>
          <button type="button" onClick={loadPage}>Retry</button>
        </div>
      ) : null}

      {SECTION_CONFIGS.map((config) => (
        <AIInsightsSection
          config={config}
          detail={details[config.type]}
          detailError={detailErrors[config.type]}
          isDetailLoading={detailLoading[config.type]}
          isPageLoading={isPageLoading}
          key={config.type}
          machines={machinesByType[config.type]}
          onRetryDetail={() => {
            const machineId = selectedIds[config.type]
            if (machineId) {
              void loadDetail(config.type, machineId)
            }
          }}
          onSelectMachine={(machineId) => handleSelectMachine(config.type, machineId)}
          selectedMachineId={selectedIds[config.type]}
        />
      ))}
    </section>
  )
}

function AIInsightsSection({
  config,
  detail,
  detailError,
  isDetailLoading,
  isPageLoading,
  machines,
  onRetryDetail,
  onSelectMachine,
  selectedMachineId,
}: {
  config: SectionConfig
  detail: AIInsightDetailResponse | null
  detailError: string | null
  isDetailLoading: boolean
  isPageLoading: boolean
  machines: AIInsightMachineCard[]
  onRetryDetail: () => void
  onSelectMachine: (machineId: string) => void
  selectedMachineId: string | null
}) {
  const selectedDetail = detail && normalizeMachineId(detail.machineId) === selectedMachineId ? detail : null

  return (
    <section className={`ai-insights-section ${config.type}`} aria-labelledby={`${config.type}-title`}>
      <header className="ai-section-heading">
        <div>
          <h2 id={`${config.type}-title`}>
            <span>{config.number}</span>
            {config.title}
          </h2>
          <p>{config.subtitle}</p>
        </div>
      </header>

      <div className="ai-section-workspace">
        <aside className="ai-response-list-panel">
          <div className="ai-panel-toolbar">
            <div>
              <strong>{config.listTitle}</strong>
              <span>{machines.length}</span>
            </div>
            <button type="button" disabled>Newest</button>
          </div>

          <div className="ai-machine-list">
            {isPageLoading ? (
              <AIState title="Loading saved responses" copy="Fetching saved machine AI history." compact />
            ) : machines.length ? (
              machines.map((machine) => {
                const machineId = machineIdFor(machine) ?? 'unknown'
                const selected = machineId === selectedMachineId

                return (
                  <button
                    className={`ai-machine-card ${selected ? 'is-selected' : ''}`}
                    key={`${config.type}-${machineId}`}
                    onClick={() => onSelectMachine(machineId)}
                    type="button"
                  >
                    <AITypeIcon type={config.type} />
                    <span className="ai-machine-copy">
                      <strong>{displayText(machine.machineId ?? machineId)}</strong>
                      <small>{displayText(machine.machineName)} - {displayText(machine.zone)}</small>
                      <small className="ai-machine-summary">{displayText(machine.latestSummary)}</small>
                      <span className="ai-machine-submeta">
                        <em>{formatResponseCount(machine.responseCount)}</em>
                        <em>{displayText(machine.latestStatus)}</em>
                        <em>{displayText(machine.latestConfidence ?? machine.source)}</em>
                      </span>
                    </span>
                    <span className="ai-machine-meta">
                      <time>{formatRelativeTime(machine.latestResponseTime)}</time>
                      <i className={`ai-status-dot ${toneForStatus(machine.latestStatus)}`}></i>
                    </span>
                  </button>
                )
              })
            ) : (
              <AIState title={config.emptyTitle} copy="Saved AI responses will appear here after analysis is generated elsewhere." compact />
            )}
          </div>
        </aside>

        <article className="ai-history-panel">
          {selectedMachineId ? (
            <SelectedHistoryPanel
              config={config}
              detail={selectedDetail}
              detailError={detailError}
              isDetailLoading={isDetailLoading}
              onRetryDetail={onRetryDetail}
              selectedMachineId={selectedMachineId}
            />
          ) : (
            <AIState title={config.emptyTitle} copy={config.emptyDetail} />
          )}
        </article>
      </div>
    </section>
  )
}

function SelectedHistoryPanel({
  config,
  detail,
  detailError,
  isDetailLoading,
  onRetryDetail,
  selectedMachineId,
}: {
  config: SectionConfig
  detail: AIInsightDetailResponse | null
  detailError: string | null
  isDetailLoading: boolean
  onRetryDetail: () => void
  selectedMachineId: string
}) {
  if (detailError) {
    return (
      <div className="ai-detail-state">
        <strong>Unable to load saved responses for {selectedMachineId}</strong>
        <p>{detailError}</p>
        <button type="button" onClick={onRetryDetail}>Retry</button>
      </div>
    )
  }

  if (isDetailLoading && !detail) {
    return <AIState title={`Loading ${selectedMachineId}`} copy="Fetching saved AI responses from newest to oldest." />
  }

  if (!detail) {
    return <AIState title="No saved responses for this machine yet" copy={config.emptyDetail} />
  }

  const responses = sortResponses(
    (detail.responses ?? []).filter((response) => normalizeAIType(response.aiType) === config.type),
  )
  const latest = responses[0] ?? detail.latest ?? null
  const status = latest?.status ?? null

  if (!responses.length) {
    return <AIState title="No saved responses for this machine yet" copy={config.emptyDetail} />
  }

  return (
    <>
      <div className="ai-selected-header">
        <div className="ai-selected-identity">
          <AITypeIcon type={config.type} />
          <div>
            <h3>{displayText(detail.machineId ?? selectedMachineId)}</h3>
            <p>{displayText(detail.machineName)} - {displayText(detail.zone)}</p>
          </div>
        </div>

        <div className="ai-selected-meta">
          <MetaPill label={config.sourceLabel} value={latest?.modelOrAgent ?? latest?.source} />
          <MetaPill label="Confidence" value={latest?.confidence} tone={toneForConfidence(latest?.confidence)} />
          <MetaPill label="Status" value={status} tone={toneForStatus(status)} />
          <MetaPill label="Updated" value={formatRelativeTime(latest?.createdAt)} />
        </div>
      </div>

      <div className="ai-history-toolbar">
        <div>
          <strong>{config.historyTitle}</strong>
          <span>{responses.length}</span>
        </div>
        <button type="button" disabled>Newest</button>
      </div>

      <div className="ai-history-list">
        {responses.map((response, index) => {
          const responseKey = response.responseId ?? response.createdAt ?? `${config.type}-${selectedMachineId}-${index}`

          return config.type === 'machine_snapshot' ? (
            <SnapshotResponseCard key={responseKey} response={response} />
          ) : (
            <DeepReviewResponseCard key={responseKey} response={response} />
          )
        })}
      </div>
    </>
  )
}

function SnapshotResponseCard({ response }: { response: AIInsightResponseRecord }) {
  const snapshot = response.snapshot ?? {}

  return (
    <article className="ai-response-card">
      <ResponseTimeRail response={response} type="machine_snapshot" />
      <div className="ai-response-grid snapshot">
        <InsightField label="Latest Machine Snapshot" value={response.summary} />
        <InsightField label="Key Anomaly" value={snapshot.keyAnomaly} />
        <InsightField label="Confidence" value={response.confidence} tone={toneForConfidence(response.confidence)} />
        <InsightField label="Suggested Next Step" value={snapshot.suggestedNextStep} />
        <InsightField label="Predicted Downtime" value={snapshot.predictedDowntimeIfIgnored} />
        <InsightField label="Downtime Reasoning" value={snapshot.downtimeReasoning} />
        <InsightField label="Evidence" value={snapshot.evidence} wide />
        <InsightField label="Source" value={response.modelOrAgent ?? response.source} />
        <RawResponseDetails responseText={response.responseText} />
      </div>
    </article>
  )
}

function DeepReviewResponseCard({ response }: { response: AIInsightResponseRecord }) {
  const deepReview = deepReviewFieldsFor(response)
  const confidence = response.confidence ?? deepReview.confidence

  return (
    <article className="ai-response-card">
      <ResponseTimeRail response={response} type="deep_review" />
      <div className="ai-response-grid deep">
        <InsightField label="Summary" value={response.summary} wide />
        <InsightField label="Root Cause" value={deepReview.rootCause} />
        <InsightField label="Pattern Findings" value={deepReview.patternFindings} />
        <InsightField label="Maintenance Recommendation" value={deepReview.maintenanceRecommendation} />
        <InsightField label="Confidence" value={confidence} tone={toneForConfidence(confidence)} />
        <InsightField label="Historical Match" value={deepReview.historicalMatch} />
        <InsightField label="Risk Outlook" value={deepReview.riskOutlook} tone={toneForStatus(deepReview.riskOutlook ?? response.status)} />
        <InsightField label="Downtime Exposure" value={deepReview.downtimeExposure} />
        <InsightField label="Final Recommendation" value={deepReview.finalRecommendation} wide />
        <InsightField label="Source" value={response.modelOrAgent ?? response.source} />
        <RawResponseDetails responseText={response.responseText} />
      </div>
    </article>
  )
}

function ResponseTimeRail({ response, type }: { response: AIInsightResponseRecord; type: AIType }) {
  return (
    <div className="ai-response-time">
      <AITypeIcon type={type} />
      <strong>{formatRelativeTime(response.createdAt)}</strong>
      <time>{formatDateTime(response.createdAt)}</time>
    </div>
  )
}

function InsightField({
  label,
  tone,
  value,
  wide = false,
}: {
  label: string
  tone?: Tone
  value: unknown
  wide?: boolean
}) {
  const displayValue = valueToText(value)
  const isList = Array.isArray(value) && value.length > 0

  return (
    <div className={`ai-insight-field ${wide ? 'wide' : ''}`}>
      <span>{label}</span>
      {isList ? (
        <ul>
          {(value as unknown[]).map((item, index) => (
            <li key={`${label}-${index}`}>{valueToText(item)}</li>
          ))}
        </ul>
      ) : tone ? (
        <strong className={`ai-value-badge ${tone}`}>{displayValue}</strong>
      ) : (
        <p>{displayValue}</p>
      )}
    </div>
  )
}

function MetaPill({ label, tone, value }: { label: string; tone?: Tone; value: unknown }) {
  return (
    <span className={`ai-meta-pill ${tone ?? ''}`}>
      <small>{label}</small>
      <strong>{valueToText(value)}</strong>
    </span>
  )
}

function RawResponseDetails({ responseText }: { responseText?: string | null }) {
  if (!responseText) {
    return null
  }

  return (
    <details className="ai-raw-response">
      <summary>View raw response</summary>
      <pre>{responseText}</pre>
    </details>
  )
}

function AIState({ compact = false, copy, title }: { compact?: boolean; copy: string; title: string }) {
  return (
    <div className={`ai-empty-state ${compact ? 'compact' : ''}`}>
      <strong>{title}</strong>
      <p>{copy}</p>
    </div>
  )
}

function AITypeIcon({ type }: { type: AIType }) {
  return (
    <span className={`ai-type-icon ${type}`} aria-hidden="true">
      {type === 'machine_snapshot' ? (
        <svg viewBox="0 0 24 24" role="img">
          <path d="M7 19V8.5h10V19" />
          <path d="M5 19h14" />
          <path d="M8.5 8.5V5.5h7v3" />
          <path d="M9.5 13h5" />
          <path d="M9.5 16h5" />
          <path d="M6 5.5h12" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" role="img">
          <path d="M6 19V9.5l4-2.5 4 2.5V19" />
          <path d="M4 19h16" />
          <path d="M14 10.5l3-2 3 2V19" />
          <path d="M8.5 12h3" />
          <path d="M8.5 15h3" />
          <path d="M17 13h1.5" />
        </svg>
      )}
    </span>
  )
}

function deepReviewFieldsFor(response: AIInsightResponseRecord): DeepReviewFields {
  const existing = response.deepReview ?? {}
  const extracted = extractDeepReviewFields(response.responseText)

  return {
    rootCause: firstPresent(existing.rootCause, extracted.rootCause),
    patternFindings: firstPresent(existing.patternFindings, extracted.patternFindings),
    maintenanceRecommendation: firstPresent(existing.maintenanceRecommendation, extracted.maintenanceRecommendation),
    historicalMatch: firstPresent(existing.historicalMatch, extracted.historicalMatch),
    riskOutlook: firstPresent(existing.riskOutlook, extracted.riskOutlook),
    downtimeExposure: firstPresent(existing.downtimeExposure, extracted.downtimeExposure),
    finalRecommendation: firstPresent(existing.finalRecommendation, extracted.finalRecommendation),
    confidence: extracted.confidence,
  }
}

function extractDeepReviewFields(responseText?: string | null): DeepReviewFields {
  if (!responseText) {
    return {}
  }

  const currentCondition = extractLooseJsonValue(responseText, 'current_condition')
  const findings = extractLooseJsonValue(responseText, 'key_findings')
  const downtime = extractLooseJsonValue(responseText, 'downtime_exposure')
  const actionPlan = extractLooseJsonValue(responseText, 'preventive_action_plan')
  const hypotheses = extractLooseJsonValue(responseText, 'root_cause_hypotheses')
  const historicalMatch = extractLooseJsonValue(responseText, 'historical_match')
  const finalRecommendation = extractLooseJsonValue(responseText, 'final_recommendation')
  const reviewStatus = extractLooseJsonValue(responseText, 'review_status')

  return {
    rootCause: firstReadableValue(hypotheses, ['hypothesis', 'root_cause', 'rootCause', 'summary', 'finding', 'description']),
    patternFindings: findings,
    maintenanceRecommendation: firstPresent(
      firstReadableValue(actionPlan, ['action', 'recommendation', 'maintenance_recommendation', 'summary', 'description']),
      finalRecommendation,
    ),
    historicalMatch: firstPresent(
      historicalMatch,
      objectField(currentCondition, 'why'),
      firstReadableValue(findings, ['evidence', 'finding']),
    ),
    riskOutlook: firstPresent(
      objectField(downtime, 'risk_outlook'),
      objectField(downtime, 'downtime_risk'),
      objectField(currentCondition, 'assessment'),
      reviewStatus,
    ),
    downtimeExposure: downtime,
    finalRecommendation: firstPresent(finalRecommendation, firstReadableValue(actionPlan, ['action', 'recommendation'])),
    confidence: firstPresent(
      extractLooseJsonValue(responseText, 'confidence'),
      objectField(downtime, 'confidence'),
      objectField(currentCondition, 'evidence_strength'),
    ),
  }
}

function extractLooseJsonValue(text: string, key: string): unknown {
  const keyIndex = text.indexOf(`"${key}"`)
  if (keyIndex < 0) {
    return undefined
  }

  const colonIndex = text.indexOf(':', keyIndex + key.length + 2)
  if (colonIndex < 0) {
    return undefined
  }

  const startIndex = firstNonWhitespaceIndex(text, colonIndex + 1)
  if (startIndex < 0) {
    return undefined
  }

  const endIndex = jsonValueEndIndex(text, startIndex)
  if (endIndex <= startIndex) {
    return undefined
  }

  const source = text.slice(startIndex, endIndex).trim().replace(/,\s*$/, '')
  try {
    return JSON.parse(source)
  } catch {
    return source.replace(/^"|"$/g, '').trim() || undefined
  }
}

function firstNonWhitespaceIndex(text: string, startIndex: number): number {
  for (let index = startIndex; index < text.length; index += 1) {
    if (!/\s/.test(text[index])) {
      return index
    }
  }
  return -1
}

function jsonValueEndIndex(text: string, startIndex: number): number {
  const opening = text[startIndex]

  if (opening === '"') {
    for (let index = startIndex + 1, escaped = false; index < text.length; index += 1) {
      const char = text[index]
      if (escaped) {
        escaped = false
      } else if (char === '\\') {
        escaped = true
      } else if (char === '"') {
        return index + 1
      }
    }
    return -1
  }

  if (opening === '{' || opening === '[') {
    const stack = [opening === '{' ? '}' : ']']
    let inString = false
    let escaped = false

    for (let index = startIndex + 1; index < text.length; index += 1) {
      const char = text[index]
      if (inString) {
        if (escaped) {
          escaped = false
        } else if (char === '\\') {
          escaped = true
        } else if (char === '"') {
          inString = false
        }
        continue
      }

      if (char === '"') {
        inString = true
      } else if (char === '{') {
        stack.push('}')
      } else if (char === '[') {
        stack.push(']')
      } else if (char === stack[stack.length - 1]) {
        stack.pop()
        if (!stack.length) {
          return index + 1
        }
      }
    }

    return -1
  }

  for (let index = startIndex; index < text.length; index += 1) {
    if (/[,\n}\]]/.test(text[index])) {
      return index
    }
  }

  return text.length
}

function firstReadableValue(value: unknown, keys: string[]): unknown {
  if (Array.isArray(value)) {
    for (const item of value) {
      const result = firstReadableValue(item, keys)
      if (!isEmptyInsightValue(result)) {
        return result
      }
    }
    return undefined
  }

  if (isPlainObject(value)) {
    for (const key of keys) {
      const result = value[key]
      if (!isEmptyInsightValue(result)) {
        return result
      }
    }
  }

  return undefined
}

function firstPresent(...values: unknown[]): unknown {
  return values.find((value) => !isEmptyInsightValue(value))
}

function objectField(value: unknown, key: string): unknown {
  return isPlainObject(value) ? value[key] : undefined
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isEmptyInsightValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '' || value === EMPTY_VALUE) {
    return true
  }
  if (Array.isArray(value)) {
    return value.length === 0
  }
  if (isPlainObject(value)) {
    return Object.keys(value).length === 0
  }
  return false
}

async function fetchAIJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const payload = await response.json() as { detail?: string }
      if (payload.detail) {
        message = payload.detail
      }
    } catch {
      // Keep the HTTP status fallback.
    }
    throw new Error(message)
  }

  return response.json() as Promise<T>
}

function sortMachines(machines: AIInsightMachineCard[]): AIInsightMachineCard[] {
  return [...machines].sort((left, right) => dateScore(right.latestResponseTime) - dateScore(left.latestResponseTime))
}

function sortResponses(responses: AIInsightResponseRecord[]): AIInsightResponseRecord[] {
  return [...responses].sort((left, right) => dateScore(right.createdAt) - dateScore(left.createdAt))
}

function machineIdFor(machine?: AIInsightMachineCard): string | null {
  return normalizeMachineId(machine?.machineId)
}

function normalizeMachineId(value: unknown): string | null {
  const text = String(value ?? '').trim()
  return text ? text : null
}

function normalizeAIType(value: unknown): AIType | null {
  const text = String(value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (text === 'machine_snapshot' || text === 'snapshot' || text === 'machine_snapshot_response') {
    return 'machine_snapshot'
  }
  if (text === 'deep_review' || text === 'machine_deep_review' || text === 'deep_orchestrate_machine_review') {
    return 'deep_review'
  }
  return null
}

function dateScore(value: unknown): number {
  if (!value) {
    return 0
  }

  const parsed = Date.parse(String(value))
  return Number.isNaN(parsed) ? 0 : parsed
}

function formatRelativeTime(value: unknown): string {
  const score = dateScore(value)
  if (!score) {
    return NOT_REPORTED
  }

  const diff = Date.now() - score
  if (diff < 0) {
    return formatDateTime(value)
  }

  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) {
    return 'Just now'
  }
  if (minutes < 60) {
    return `${minutes} min ago`
  }

  const hours = Math.floor(minutes / 60)
  if (hours < 24) {
    return `${hours} hr ago`
  }

  const days = Math.floor(hours / 24)
  if (days < 30) {
    return `${days} day${days === 1 ? '' : 's'} ago`
  }

  return formatDateTime(value)
}

function formatDateTime(value: unknown): string {
  const score = dateScore(value)
  if (!score) {
    return NOT_REPORTED
  }

  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(score))
}

function displayText(value: unknown): string {
  const text = valueToText(value)
  return text === EMPTY_VALUE ? NOT_REPORTED : text
}

function formatResponseCount(value: unknown): string {
  const count = typeof value === 'number' && Number.isFinite(value) ? value : 0
  return `${count} response${count === 1 ? '' : 's'}`
}

function valueToText(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return EMPTY_VALUE
  }

  if (typeof value === 'number') {
    return Number.isFinite(value) ? String(value) : EMPTY_VALUE
  }

  if (typeof value === 'string') {
    return value.trim() || EMPTY_VALUE
  }

  if (Array.isArray(value)) {
    const items = value.map((item) => valueToText(item)).filter((item) => item !== EMPTY_VALUE)
    return items.length ? items.join('; ') : EMPTY_VALUE
  }

  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => {
        const itemText = valueToText(item)
        return itemText === EMPTY_VALUE ? null : `${humanizeKey(key)}: ${itemText}`
      })
      .filter(Boolean)

    return entries.length ? entries.join(' | ') : EMPTY_VALUE
  }

  return String(value)
}

function humanizeKey(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function toneForConfidence(value: unknown): Tone {
  if (typeof value === 'number') {
    if (value >= 0.8) {
      return 'green'
    }
    if (value >= 0.6) {
      return 'amber'
    }
    return 'red'
  }

  const text = String(value ?? '').toLowerCase()
  if (text.includes('high') || text.includes('0.8') || text.includes('0.9')) {
    return 'green'
  }
  if (text.includes('medium') || text.includes('moderate') || text.includes('0.6') || text.includes('0.7')) {
    return 'amber'
  }
  if (text.includes('low') || text.includes('weak')) {
    return 'red'
  }
  return 'neutral'
}

function toneForStatus(value: unknown): Tone {
  const text = String(value ?? '').toLowerCase()
  if (text.includes('critical') || text.includes('high') || text.includes('risk') || text.includes('failed') || text.includes('error')) {
    return 'red'
  }
  if (text.includes('warning') || text.includes('medium') || text.includes('review') || text.includes('elevated')) {
    return 'amber'
  }
  if (text.includes('healthy') || text.includes('low') || text.includes('complete') || text.includes('analy') || text.includes('ok')) {
    return 'green'
  }
  return 'neutral'
}

export default AIInsightsPage
