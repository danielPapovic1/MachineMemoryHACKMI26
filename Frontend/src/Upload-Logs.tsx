import { Fragment, useCallback, useEffect, useMemo, useState, type ChangeEvent } from 'react'

const API_BASE_URL = 'http://localhost:8000'
const EMPTY_VALUE = 'No values yet'
const NOT_REPORTED = 'Not reported'
const UPLOAD_LIST_LIMIT = 25
const DETAIL_ROW_LIMIT = 100

type UploadStatus = 'processed' | 'needs_review' | 'failed' | string

type UploadSummary = {
  uploadId: string
  fileName: string
  uploadedAt: string
  uploadType: string
  status: UploadStatus
  machineCount: number
  rowsStored: number
  insertedRows: number
  updatedRows: number
  errorRows: number
  affectedMachineIds: string[]
  warnings?: string[]
}

type UploadLogsPageResponse = {
  summary: {
    totalUploads: number
    lastUpload: null | {
      uploadedAt: string
      fileName: string
    }
    rowsStored: number
    machinesUpdated: number
    insertedRows: number
    updatedRows: number
    errorRows: number
  }
  uploads: UploadSummary[]
  filters: {
    uploadTypes: string[]
    statuses: string[]
    machineIds: string[]
  }
  pagination: {
    limit: number
    offset: number
    total: number
  }
}

type UploadLogDetailResponse = {
  overview: {
    uploadId: string
    fileName: string
    uploadedAt: string
    uploadType: string
    status: string
    machineCount: number
    rowsStored: number
    warnings: string[]
  }
  affectedMachines: {
    machineId: string
    name: string | null
    zone: string | null
    matchedMachine: boolean
  }[]
  rowSummary: {
    totalRows: number
    inserted: number
    updated: number
    errors: number
    returned: number
    limit: number
    offset: number
  }
  rows: UploadDisplayRow[]
}

type UploadDisplayRow = {
  machineId: string | null
  machineName?: string | null
  field: string
  value: string | number | null
  timestamp: string | null
  status: string
  sourceFile: string
  sourceRowNumber?: number | null
  severity?: string | null
  downtimeMinutes?: number | null
  laborHours?: number | null
  operatorNote?: string | null
  resolutionNote?: string | null
}

type UploadFilters = {
  dateFrom: string
  dateTo: string
  uploadType: string
  status: string
  machineId: string
}

const DEFAULT_FILTERS: UploadFilters = {
  dateFrom: '',
  dateTo: '',
  uploadType: '',
  status: '',
  machineId: '',
}

function UploadLogsPage() {
  const [pageData, setPageData] = useState<UploadLogsPageResponse | null>(null)
  const [selectedUploadId, setSelectedUploadId] = useState<string | null>(null)
  const [selectedDetail, setSelectedDetail] = useState<UploadLogDetailResponse | null>(null)
  const [filters, setFilters] = useState<UploadFilters>(DEFAULT_FILTERS)
  const [listOffset, setListOffset] = useState(0)
  const [detailOffset, setDetailOffset] = useState(0)
  const [isListLoading, setIsListLoading] = useState(true)
  const [isDetailLoading, setIsDetailLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const loadUploads = useCallback(async () => {
    setIsListLoading(true)
    setListError(null)

    try {
      const data = await fetchUploadJson<UploadLogsPageResponse>(
        `/api/upload-logs${buildQuery({
          ...filters,
          limit: UPLOAD_LIST_LIMIT,
          offset: listOffset,
        })}`,
      )

      setPageData(data)
      const firstUploadId = data.uploads[0]?.uploadId ?? null
      setSelectedUploadId(firstUploadId)
      setDetailOffset(0)
      setSelectedDetail(null)
      if (!firstUploadId) {
        setSelectedDetail(null)
      }
    } catch (error) {
      setListError(error instanceof Error ? error.message : 'Unable to load upload logs')
      setPageData(null)
      setSelectedUploadId(null)
      setSelectedDetail(null)
    } finally {
      setIsListLoading(false)
    }
  }, [filters, listOffset])

  const loadSelectedUpload = useCallback(async () => {
    if (!selectedUploadId) {
      return
    }

    setIsDetailLoading(true)
    setDetailError(null)

    try {
      const detail = await fetchUploadJson<UploadLogDetailResponse>(
        `/api/upload-logs/${encodeURIComponent(selectedUploadId)}${buildQuery({
          limit: DETAIL_ROW_LIMIT,
          offset: detailOffset,
        })}`,
      )
      setSelectedDetail(detail)
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : 'Unable to load selected upload')
      setSelectedDetail(null)
    } finally {
      setIsDetailLoading(false)
    }
  }, [detailOffset, selectedUploadId])

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      loadUploads().catch(() => undefined)
    }, 0)

    return () => window.clearTimeout(loadTimer)
  }, [loadUploads])

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      loadSelectedUpload().catch(() => undefined)
    }, 0)

    return () => window.clearTimeout(loadTimer)
  }, [loadSelectedUpload])

  const selectedUpload = useMemo(
    () => pageData?.uploads.find((upload) => upload.uploadId === selectedUploadId) ?? null,
    [pageData?.uploads, selectedUploadId],
  )

  const totalUploads = pageData?.pagination.total ?? 0
  const uploadStart = totalUploads === 0 ? 0 : (pageData?.pagination.offset ?? 0) + 1
  const uploadEnd = Math.min((pageData?.pagination.offset ?? 0) + (pageData?.uploads.length ?? 0), totalUploads)
  const canPageUploadsBack = (pageData?.pagination.offset ?? 0) > 0
  const canPageUploadsForward = uploadEnd < totalUploads
  const rowSummary = selectedDetail?.rowSummary
  const canPageRowsBack = (rowSummary?.offset ?? 0) > 0
  const canPageRowsForward = rowSummary ? rowSummary.offset + rowSummary.returned < rowSummary.totalRows : false

  const handleFilterChange = (field: keyof UploadFilters) => (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFilters((current) => ({ ...current, [field]: event.target.value }))
    setListOffset(0)
  }

  const handleResetFilters = () => {
    setFilters(DEFAULT_FILTERS)
    setListOffset(0)
  }

  const handleSelectUpload = (uploadId: string) => {
    setSelectedUploadId(uploadId)
    setDetailOffset(0)
    setSelectedDetail(null)
  }

  return (
    <section className="upload-logs-page">
      <div className="upload-logs-hero">
        <span className="upload-page-icon" aria-hidden="true">
          <UploadPageIcon name="upload" />
        </span>
        <div>
          <h2>Upload Logs</h2>
          <p>View and explore uploaded factory data.</p>
        </div>
        <div className="upload-match-legend" aria-label="Machine match legend">
          <span><i className="matched"></i>Matched in this set</span>
          <span><i className="unmatched"></i>Not matched</span>
        </div>
      </div>

      <div className="upload-summary-grid">
        <UploadMetricCard
          icon="file"
          label="Total Uploads"
          value={formatNumber(pageData?.summary.totalUploads)}
          support="Uploaded files tracked"
          tone="rose"
        />
        <UploadMetricCard
          icon="calendar"
          label="Last Upload"
          value={formatRelativeTime(pageData?.summary.lastUpload?.uploadedAt)}
          support={formatDateTime(pageData?.summary.lastUpload?.uploadedAt)}
          tone="green"
        />
        <UploadMetricCard
          icon="database"
          label="Rows Stored"
          value={formatNumber(pageData?.summary.rowsStored)}
          support={`${formatNumber(pageData?.summary.insertedRows)} inserted`}
          tone="purple"
        />
      </div>

      <div className="upload-filter-bar">
        <label>
          <span>Date From</span>
          <input onChange={handleFilterChange('dateFrom')} type="date" value={filters.dateFrom} />
        </label>
        <label>
          <span>Date To</span>
          <input onChange={handleFilterChange('dateTo')} type="date" value={filters.dateTo} />
        </label>
        <label>
          <span>Upload Type</span>
          <select onChange={handleFilterChange('uploadType')} value={filters.uploadType}>
            <option value="">All Types</option>
            {(pageData?.filters.uploadTypes ?? []).map((uploadType) => (
              <option key={uploadType} value={uploadType}>{formatUploadType(uploadType)}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select onChange={handleFilterChange('status')} value={filters.status}>
            <option value="">All Statuses</option>
            {(pageData?.filters.statuses ?? []).map((status) => (
              <option key={status} value={status}>{statusMeta(status).label}</option>
            ))}
          </select>
        </label>
        <label>
          <span>Machine</span>
          <select onChange={handleFilterChange('machineId')} value={filters.machineId}>
            <option value="">All Machines</option>
            {(pageData?.filters.machineIds ?? []).map((machineId) => (
              <option key={machineId} value={machineId}>{machineId}</option>
            ))}
          </select>
        </label>
        <button className="upload-reset-button" onClick={handleResetFilters} type="button">
          <UploadPageIcon name="reset" />
          Reset
        </button>
      </div>

      <div className="upload-workspace">
        <section className="upload-list-panel">
          <div className="upload-panel-header">
            <h3>Recent Uploads</h3>
          </div>

          {isListLoading ? (
            <UploadState title="Loading uploads" message="Reading uploaded file history from the backend." />
          ) : listError ? (
            <UploadState title="Unable to load uploads" message={listError} />
          ) : !pageData || pageData.uploads.length === 0 ? (
            <UploadState title="No uploads yet" message="Uploaded CSV files will appear here after processing." />
          ) : (
            <>
              <div className="upload-card-list">
                {pageData.uploads.map((upload) => (
                  <article className={`upload-card ${selectedUploadId === upload.uploadId ? 'is-selected' : ''}`} key={upload.uploadId}>
                    <div className="upload-file-icon" aria-hidden="true">
                      <UploadPageIcon name="file" />
                    </div>
                    <div className="upload-card-main">
                      <strong title={upload.fileName}>{displayValue(upload.fileName)}</strong>
                      <time>{formatDateTime(upload.uploadedAt)}</time>
                      <span>{formatUploadType(upload.uploadType)}</span>
                    </div>
                    <div className="upload-card-meta">
                      <span>Machines <strong>{formatNumber(upload.machineCount)}</strong></span>
                      <span>Rows <strong>{formatNumber(upload.rowsStored)}</strong></span>
                    </div>
                    <button onClick={() => handleSelectUpload(upload.uploadId)} type="button">
                      Open Upload
                    </button>
                  </article>
                ))}
              </div>

              <div className="upload-pagination">
                <span>Showing {uploadStart} to {uploadEnd} of {totalUploads} uploads</span>
                <div>
                  <button disabled={!canPageUploadsBack} onClick={() => setListOffset(Math.max(listOffset - UPLOAD_LIST_LIMIT, 0))} type="button">
                    <UploadPageIcon name="chevronLeft" />
                  </button>
                  <button disabled={!canPageUploadsForward} onClick={() => setListOffset(listOffset + UPLOAD_LIST_LIMIT)} type="button">
                    <UploadPageIcon name="chevronRight" />
                  </button>
                </div>
              </div>
            </>
          )}
        </section>

        <section className="selected-upload-panel">
          <div className="upload-panel-header">
            <h3>Selected Upload</h3>
            {selectedUpload ? <button type="button">Export</button> : null}
          </div>

          {!selectedUploadId ? (
            <UploadState title="Select an upload" message="Select an upload to view stored rows." />
          ) : isDetailLoading ? (
            <UploadState title="Loading selected upload" message="Fetching stored rows and upload metadata." />
          ) : detailError ? (
            <UploadState title="Unable to load selected upload" message={detailError} />
          ) : selectedDetail ? (
            <SelectedUploadDetail
              canPageRowsBack={canPageRowsBack}
              canPageRowsForward={canPageRowsForward}
              detail={selectedDetail}
              onNextRows={() => setDetailOffset(detailOffset + DETAIL_ROW_LIMIT)}
              onPreviousRows={() => setDetailOffset(Math.max(detailOffset - DETAIL_ROW_LIMIT, 0))}
            />
          ) : (
            <UploadState title="No upload selected" message="Select an upload to view stored rows." />
          )}
        </section>
      </div>
    </section>
  )
}

function SelectedUploadDetail({
  canPageRowsBack,
  canPageRowsForward,
  detail,
  onNextRows,
  onPreviousRows,
}: {
  canPageRowsBack: boolean
  canPageRowsForward: boolean
  detail: UploadLogDetailResponse
  onNextRows: () => void
  onPreviousRows: () => void
}) {
  const [expandedRowKey, setExpandedRowKey] = useState<string | null>(null)
  const rowsStart = detail.rowSummary.totalRows === 0 ? 0 : detail.rowSummary.offset + 1
  const rowsEnd = Math.min(detail.rowSummary.offset + detail.rowSummary.returned, detail.rowSummary.totalRows)

  useEffect(() => {
    setExpandedRowKey(null)
  }, [detail.overview.uploadId, detail.rowSummary.offset])

  return (
    <>
      <div className="upload-overview-card">
        <h4>Overview</h4>
        <dl>
          <div>
            <dt>File Name</dt>
            <dd>{displayValue(detail.overview.fileName)}</dd>
          </div>
          <div>
            <dt>Upload Time</dt>
            <dd>{formatDateTime(detail.overview.uploadedAt)}</dd>
          </div>
          <div>
            <dt>Upload Type</dt>
            <dd>{formatUploadType(detail.overview.uploadType)}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd><StatusBadge status={detail.overview.status} /></dd>
          </div>
          <div>
            <dt>Machines</dt>
            <dd>{formatNumber(detail.overview.machineCount)}</dd>
          </div>
          <div>
            <dt>Rows Stored</dt>
            <dd>{formatNumber(detail.overview.rowsStored)}</dd>
          </div>
        </dl>
      </div>

      <div className="upload-detail-grid">
        <section className="upload-detail-card" style={{ gridColumn: '1 / -1' }}>
          <h4>Affected Machines ({formatNumber(detail.affectedMachines.length)})</h4>
          {detail.affectedMachines.length > 0 ? (
            <div className="affected-machine-grid">
              {detail.affectedMachines.map((machine) => (
                <span className={`affected-machine-chip ${machine.matchedMachine ? '' : 'is-unmatched'}`} key={machine.machineId}>
                  <i></i>
                  <strong>{displayValue(machine.machineId)}</strong>
                  <small style={{ maxWidth: 160 }}>{displayMetadata(machine.zone ?? machine.name)}</small>
                </span>
              ))}
            </div>
          ) : (
            <p className="upload-muted-copy">No affected machines reported.</p>
          )}
        </section>
      </div>

      <section className="upload-rows-card">
        <div className="upload-rows-header">
          <div>
            <h4>Upload Data Rows</h4>
            <span>Showing {rowsStart} to {rowsEnd} of {formatNumber(detail.rowSummary.totalRows)} rows</span>
          </div>
          <div className="upload-row-controls">
            <button disabled={!canPageRowsBack} onClick={onPreviousRows} type="button">
              <UploadPageIcon name="chevronLeft" />
            </button>
            <button disabled={!canPageRowsForward} onClick={onNextRows} type="button">
              <UploadPageIcon name="chevronRight" />
            </button>
          </div>
        </div>

        {detail.rows.length > 0 ? (
          <div className="upload-table-scroll">
            <table className="upload-data-table">
              <thead>
                <tr>
                  <th>Machine ID</th>
                  <th>Field</th>
                  <th>Value</th>
                  <th>Timestamp</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {detail.rows.map((row, index) => {
                  const rowKey = uploadRowKey(row, index)
                  const isExpanded = expandedRowKey === rowKey

                  return (
                    <Fragment key={rowKey}>
                      <tr className={isExpanded ? 'is-expanded' : ''}>
                        <td>{displayMetadata(row.machineId)}</td>
                        <td>{displayValue(row.field)}</td>
                        <td>{displayValue(row.value)}</td>
                        <td>{formatDateTime(row.timestamp)}</td>
                        <td>
                          <div className="upload-row-status-cell">
                            <StatusBadge status={row.status} compact />
                            <button
                              aria-expanded={isExpanded}
                              className="upload-row-details-button"
                              onClick={() => setExpandedRowKey(isExpanded ? null : rowKey)}
                              type="button"
                            >
                              Details
                            </button>
                          </div>
                        </td>
                      </tr>
                      {isExpanded ? (
                        <tr className="upload-row-detail">
                          <td colSpan={5}>
                            <div className="upload-row-detail-shell">
                              <div className="upload-row-detail-item">
                                <span>Downtime Minutes</span>
                                <strong>{formatReportedNumber(row.downtimeMinutes)}</strong>
                              </div>
                              <div className="upload-row-detail-item">
                                <span>Labor Hours</span>
                                <strong>{formatReportedNumber(row.laborHours)}</strong>
                              </div>
                              <div className="upload-row-detail-item">
                                <span>Severity</span>
                                <strong>{displayMetadata(row.severity)}</strong>
                              </div>
                              <div className="upload-row-detail-item">
                                <span>Source Row</span>
                                <strong>{displayMetadata(row.sourceRowNumber)}</strong>
                              </div>
                              <div className="upload-row-detail-item is-wide">
                                <span>Operator Note</span>
                                <p>{displayNote(row.operatorNote, 'No operator note')}</p>
                              </div>
                              <div className="upload-row-detail-item is-wide">
                                <span>Resolution Note</span>
                                <p>{displayNote(row.resolutionNote, 'No resolution note')}</p>
                              </div>
                            </div>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <UploadState title="No stored rows found" message="No stored rows found for this upload." compact />
        )}
      </section>
    </>
  )
}

function UploadMetricCard({
  icon,
  label,
  support,
  tone,
  value,
}: {
  icon: string
  label: string
  support: string
  tone: string
  value: string
}) {
  return (
    <article className={`upload-metric-card ${tone}`}>
      <span className="upload-metric-icon" aria-hidden="true">
        <UploadPageIcon name={icon} />
      </span>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{support}</span>
      </div>
    </article>
  )
}

function StatusBadge({ compact = false, status }: { compact?: boolean; status: string }) {
  const meta = statusMeta(status)

  return <span className={`upload-status-badge ${meta.tone} ${compact ? 'compact' : ''}`}>{meta.label}</span>
}

function UploadState({ compact = false, message, title }: { compact?: boolean; message: string; title: string }) {
  return (
    <div className={`upload-state ${compact ? 'compact' : ''}`}>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  )
}

function UploadPageIcon({ name }: { name: string }) {
  const common = {
    className: 'upload-page-svg',
    fill: 'none',
    stroke: 'currentColor',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    strokeWidth: 1.8,
    viewBox: '0 0 24 24',
  }

  if (name === 'upload') {
    return <svg {...common}><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 18h14" /><path d="M5 18v2h14v-2" /></svg>
  }

  if (name === 'file') {
    return <svg {...common}><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v5h5" /><path d="M9 13h6" /><path d="M9 17h4" /></svg>
  }

  if (name === 'calendar') {
    return <svg {...common}><path d="M7 3v4" /><path d="M17 3v4" /><path d="M4 8h16" /><path d="M5 5h14v16H5z" /><path d="M8 12h3" /><path d="M13 12h3" /><path d="M8 16h3" /></svg>
  }

  if (name === 'database') {
    return <svg {...common}><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v6c0 1.7 3.1 3 7 3s7-1.3 7-3V5" /><path d="M5 11v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></svg>
  }

  if (name === 'machine') {
    return <svg {...common}><path d="M5 18h14" /><path d="M7 14h10v4H7z" /><path d="M9 10h6v4H9z" /><path d="M12 5v5" /><path d="M9 5h6" /></svg>
  }

  if (name === 'reset') {
    return <svg {...common}><path d="M4 12a8 8 0 1 0 2.4-5.7" /><path d="M4 5v5h5" /></svg>
  }

  if (name === 'chevronLeft') {
    return <svg {...common}><path d="m15 18-6-6 6-6" /></svg>
  }

  if (name === 'chevronRight') {
    return <svg {...common}><path d="m9 18 6-6-6-6" /></svg>
  }

  return <svg {...common}><circle cx="12" cy="12" r="8" /></svg>
}

async function fetchUploadJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)

  if (!response.ok) {
    let message = `Backend returned ${response.status} for ${path}`

    try {
      const body = await response.json()
      if (body?.detail) {
        message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // Keep the status-based message when the backend does not return JSON.
    }

    throw new Error(message)
  }

  return response.json() as Promise<T>
}

function buildQuery(params: Record<string, string | number | undefined>): string {
  const query = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      query.set(key, String(value))
    }
  })

  const text = query.toString()
  return text ? `?${text}` : ''
}

function statusMeta(status: unknown): { label: string; tone: string } {
  const normalized = String(status ?? '').toLowerCase()

  if (normalized === 'processed' || normalized === 'ok' || normalized === 'stored') {
    return { label: normalized === 'stored' ? 'Stored' : 'Processed', tone: 'processed' }
  }

  if (normalized === 'needs_review' || normalized === 'needs review' || normalized === 'warning') {
    return { label: 'Needs Review', tone: 'needs-review' }
  }

  if (normalized === 'failed' || normalized === 'error') {
    return { label: 'Failed', tone: 'failed' }
  }

  return { label: hasValue(status) ? toTitleCase(String(status).replace(/[_-]+/g, ' ')) : 'Unknown', tone: 'unknown' }
}

function formatUploadType(value: unknown): string {
  if (!hasValue(value)) {
    return NOT_REPORTED
  }

  const normalized = String(value).replace(/[_-]+/g, ' ')
  if (normalized.toLowerCase() === 'maintenance') {
    return 'Maintenance Logs'
  }

  return toTitleCase(normalized)
}

function formatNumber(value: unknown): string {
  if (!hasValue(value)) {
    return EMPTY_VALUE
  }

  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) {
    return String(value)
  }

  return new Intl.NumberFormat('en-US').format(numericValue)
}

function formatDateTime(value: unknown): string {
  if (!hasValue(value)) {
    return EMPTY_VALUE
  }

  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatRelativeTime(value: unknown): string {
  if (!hasValue(value)) {
    return EMPTY_VALUE
  }

  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  const diffSeconds = Math.round((date.getTime() - Date.now()) / 1000)
  const absoluteSeconds = Math.abs(diffSeconds)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 31536000],
    ['month', 2592000],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  const formatter = new Intl.RelativeTimeFormat('en-US', { numeric: 'auto' })

  for (const [unit, secondsPerUnit] of units) {
    if (absoluteSeconds >= secondsPerUnit) {
      return formatter.format(Math.round(diffSeconds / secondsPerUnit), unit)
    }
  }

  return formatter.format(diffSeconds, 'second')
}

function displayValue(value: unknown): string {
  return hasValue(value) ? String(value) : EMPTY_VALUE
}

function displayMetadata(value: unknown): string {
  return hasValue(value) ? String(value) : NOT_REPORTED
}

function formatReportedNumber(value: unknown): string {
  return hasValue(value) ? formatNumber(value) : NOT_REPORTED
}

function displayNote(value: unknown, fallback: string): string {
  return hasValue(value) ? String(value) : fallback
}

function uploadRowKey(row: UploadDisplayRow, index: number): string {
  return [
    row.sourceFile,
    row.sourceRowNumber ?? index,
    row.machineId ?? 'unknown-machine',
    row.field,
    row.timestamp ?? 'no-timestamp',
  ].join('|')
}

function hasValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

function toTitleCase(value: string): string {
  return value
    .split(' ')
    .filter(Boolean)
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`)
    .join(' ')
}

export default UploadLogsPage
