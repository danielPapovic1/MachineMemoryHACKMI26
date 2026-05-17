import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import './App.css'
import AIInsightsPage from './AI-Insights'
import MachinesPage from './Machines'
import UploadLogsPage from './Upload-Logs'

const API_BASE_URL = 'http://localhost:8000'
const EMPTY_VALUE = 'No values yet'
const APP_VERSION = 'v2.4.1'

const FACTORY_MACHINE_NAMES: Record<string, string> = {
  'PRESS-1': 'Hydraulic Press 1',
  'PRESS-2': 'Hydraulic Press 2',
  'WELD-1': 'Robotic Welder 1',
  'COMP-1': 'Air Compressor 1',
  'CNC-1': 'CNC Mill 1',
  'CNC-2': 'CNC Mill 2',
  'CONV-1': 'Main Conveyor 1',
  'PAINT-1': 'Paint Booth 1',
}

const FACTORY_ZONE_GRID = [
  {
    title: 'Stamping',
    code: 'ZONE 01',
    icon: 'press',
    machineIcon: 'press',
    machineIds: ['PRESS-1', 'PRESS-2'],
  },
  {
    title: 'Welding',
    code: 'ZONE 02',
    icon: 'welding',
    machineIcon: 'welding',
    machineIds: ['WELD-1'],
  },
  {
    title: 'Utilities',
    code: 'ZONE 03',
    icon: 'compressor',
    machineIcon: 'compressor',
    machineIds: ['COMP-1'],
  },
  {
    title: 'Machining',
    code: 'ZONE 04',
    icon: 'cnc',
    machineIcon: 'cnc',
    machineIds: ['CNC-1', 'CNC-2'],
  },
  {
    title: 'Assembly',
    code: 'ZONE 05',
    icon: 'conveyor',
    machineIcon: 'conveyor',
    machineIds: ['CONV-1'],
  },
  {
    title: 'Finishing',
    code: 'ZONE 06',
    icon: 'paint',
    machineIcon: 'paint',
    machineIds: ['PAINT-1'],
  },
]

type MachineStatus = 'healthy' | 'warning' | 'critical' | 'unknown' | string

type Machine = {
  id: string
  machine_id?: string
  name?: string | null
  type?: string | null
  line?: string | null
  location?: string | null
  zone?: string | null
  status?: MachineStatus | null
  riskScore?: number | null
  downtimeCostPerMinute?: number | null
  lastMaintenance?: string | null
  nextMaintenance?: string | null
  maintenanceOverdue?: boolean | null
  maintenanceStatus?: string | null
  anomalyFlags?: string[] | null
  estimatedDowntimeMinutes?: number | null
  estimatedCostExposure?: number | null
  runtimeHours?: number | null
  errorCount?: number | null
  sensorSummary?: {
    temperature?: number | string | null
    vibration?: number | string | null
    pressure?: number | string | null
  } | null
  manufacturer?: string | null
  model?: string | null
  installYear?: number | null
  installedDate?: string | null
  operatorNotes?: string | null
  maintenanceCount?: number | null
  energyUsage?: number | null
  throughputPerHour?: number | null
  source?: string | null
}

type DashboardSummary = {
  totalMachines?: number | null
  healthyCount?: number | null
  warningCount?: number | null
  criticalCount?: number | null
  unknownCount?: number | null
  averageRiskScore?: number | null
  estimatedDowntimeRisk?: number | null
  estimatedCostRisk?: number | null
}

type FactoryLayoutItem = {
  machineId: string
  x?: number | null
  y?: number | null
  width?: number | null
  height?: number | null
  zone?: string | null
}

type FactoryZone = {
  name: string
  x?: number | null
  y?: number | null
  width?: number | null
  height?: number | null
}

type FactoryMapData = {
  layout: FactoryLayoutItem[]
  zones: FactoryZone[]
  bounds?: {
    width?: number | null
    height?: number | null
  } | null
}

type ColumnMapping = {
  uploadedColumn?: string
  uploaded_column?: string
  normalizedField?: string
  normalized_field?: string
  strategy?: string | null
  confidence?: number | null
}

type UploadWarning = string

type SkippedRow = {
  rowNumber?: number
  row_number?: number
  reason?: string | null
}

type UnmappedColumn = {
  uploadedColumn?: string
  uploaded_column?: string
  reason?: string | null
}

type UploadPreview = {
  detectedColumnMappings: ColumnMapping[]
  lastUpload?: {
    uploadedAt?: string | null
    fileName?: string | null
    normalizedCount?: number | null
  } | null
  warnings?: UploadWarning[]
  skippedRows?: SkippedRow[]
  unmappedColumns?: UnmappedColumn[]
}

type UploadResult = {
  source?: string | null
  upload_type?: string | null
  row_count?: number | null
  normalized_count?: number | null
  saved_count?: number | null
  total_history_count?: number | null
  detected_column_mappings?: ColumnMapping[]
  normalized_machines?: Machine[]
  normalized_records?: MaintenanceRecord[]
  dashboard_summary?: DashboardSummary
  uploadPreview?: UploadPreview
  unmapped_columns?: UnmappedColumn[]
  warnings?: UploadWarning[]
  skipped_rows?: SkippedRow[]
}

type MaintenanceRecord = {
  machine_id?: string | null
}

type RecentLog = {
  time?: string | null
  machineId?: string | null
  event?: string | null
  downtimeMinutes?: number | null
  technician?: string | null
  status?: string | null
}

type Alert = {
  level?: string | null
  message?: string | null
  timestamp?: string | null
}

type SimilarPastFix = {
  date?: string | null
  issue?: string | null
  fix?: string | null
  downtimeMinutes?: number | null
  outcome?: string | null
}

type OperationalSummary = {
  matchingHistoryRecords?: number | null
  recentUploadedRecords?: number | null
  highCriticalLogs?: number | null
  openItems?: number | null
  totalLoggedDowntimeMinutes?: number | null
  mostCommonLoggedIssue?: string | null
  lastLoggedIssue?: string | null
  latestUploadSource?: string | null
  latestLogTime?: string | null
  matchedMachine?: boolean | null
}

type PatternMatch = {
  pattern?: string | null
  count?: number | null
}

type SimilarHistoricalEvent = {
  date?: string | null
  machineId?: string | null
  pattern?: string | null
  issue?: string | null
  note?: string | null
  resolution?: string | null
  downtimeMinutes?: number | null
  source?: string | null
}

type MachineAnalysis = {
  machineId?: string | null
  summary?: string | null
  predictedDowntimeIfIgnored?: string | null
  downtimeReasoning?: string | null
  evidence?: string[] | null
  recommendedNextStep?: string | null
  predictedIssue?: string | null
  rootCause?: string | null
  recommendedAction?: string | null
  urgency?: string | null
  estimatedDowntimeHours?: number | null
  estimatedSavings?: number | null
  confidence?: number | string | null
}

type MachineDetail = {
  machine: Machine
  attentionLevel?: string | null
  attentionReasons?: string[]
  operationalSummary?: OperationalSummary | null
  operationalSignals?: string[]
  patternMatches?: PatternMatch[]
  similarHistoricalEvents?: SimilarHistoricalEvent[]
  riskSignals?: string[]
  similarPastFixes?: SimilarPastFix[]
  recommendations?: string[]
  recentLogs?: RecentLog[]
  analysis?: MachineAnalysis | null
}

type DashboardData = {
  machines: Machine[]
  factoryMap: FactoryMapData
  summary: DashboardSummary | null
  recentLogs: RecentLog[]
  alerts: Alert[]
  uploadPreview: UploadPreview | null
}

type SummaryCard = {
  label: string
  value: number | string | null | undefined
  tone: 'steel' | 'danger' | 'amber' | 'green'
  icon: string
}

type ActivePage = 'dashboard' | 'uploadLogs' | 'machines' | 'aiInsights'

type HealthResponse = {
  status?: string | null
}

const navItems: { label: string; icon: string; page?: ActivePage }[] = [
  { label: 'Dashboard', icon: 'grid', page: 'dashboard' },
  { label: 'Upload Logs', icon: 'upload', page: 'uploadLogs' },
  { label: 'Machines', icon: 'machine', page: 'machines' },
  { label: 'AI Insights', icon: 'bars', page: 'aiInsights' },
]

const emptyFactoryMap: FactoryMapData = {
  layout: [],
  zones: [],
  bounds: null,
}

function App() {
  const [dashboardData, setDashboardData] = useState<DashboardData>({
    machines: [],
    factoryMap: emptyFactoryMap,
    summary: null,
    recentLogs: [],
    alerts: [],
    uploadPreview: null,
  })
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(null)
  const [machineDetail, setMachineDetail] = useState<MachineDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [systemHealth, setSystemHealth] = useState<'ok' | 'down'>('down')
  const [activePage, setActivePage] = useState<ActivePage>('dashboard')

  const loadDashboard = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const [machines, factoryMap, summary, recentLogs, alerts, uploadPreview] = await Promise.all([
        fetchJson<{ machines: Machine[] }>('/api/machines'),
        fetchJson<FactoryMapData>('/api/factory-map'),
        fetchJson<DashboardSummary>('/api/dashboard-summary'),
        fetchJson<{ logs: RecentLog[] }>('/api/maintenance-logs/recent'),
        fetchJson<{ alerts: Alert[] }>('/api/alerts/recent'),
        fetchJson<UploadPreview>('/api/uploads/preview'),
      ])

      setDashboardData({
        machines: machines.machines ?? [],
        factoryMap: {
          layout: factoryMap.layout ?? [],
          zones: factoryMap.zones ?? [],
          bounds: factoryMap.bounds ?? null,
        },
        summary,
        recentLogs: recentLogs.logs ?? [],
        alerts: alerts.alerts ?? [],
        uploadPreview,
      })
      setSelectedMachineId((currentMachineId) => {
        const loadedMachines = machines.machines ?? []
        const currentMachineExists = loadedMachines.some((machine) => machine.id === currentMachineId)

        return currentMachineExists ? currentMachineId : null
      })
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Unable to reach backend'
      setError(message)
      setDashboardData({
        machines: [],
        factoryMap: emptyFactoryMap,
        summary: null,
        recentLogs: [],
        alerts: [],
        uploadPreview: null,
      })
      setSelectedMachineId(null)
      setMachineDetail(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  const loadMachineDetail = useCallback(async (machineId: string) => {
    setDetailLoading(true)
    setDetailError(null)

    try {
      const detail = await fetchJson<MachineDetail>(`/api/machines/${encodeURIComponent(machineId)}`)
      setMachineDetail(detail)
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : 'Unable to load machine detail'
      setDetailError(message)
      setMachineDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const analyzeMachine = useCallback(async () => {
    if (!selectedMachineId) {
      return
    }

    setIsAnalyzing(true)
    setDetailError(null)

    try {
      const analysis = await fetchJson<MachineAnalysis>(`/api/machines/${encodeURIComponent(selectedMachineId)}/analyze`, {
        method: 'POST',
      })
      setMachineDetail((currentDetail) => currentDetail ? { ...currentDetail, analysis } : currentDetail)
    } catch (analysisError) {
      const message = analysisError instanceof Error ? analysisError.message : 'Unable to run AI analysis'
      setDetailError(message)
    } finally {
      setIsAnalyzing(false)
    }
  }, [selectedMachineId])

  const handleCsvUpload = useCallback(async (file: File) => {
    setIsUploading(true)
    setUploadError(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const result = await fetchJson<UploadResult>('/api/uploads/csv', {
        method: 'POST',
        body: formData,
      })

      await loadDashboard()

      const firstUploadedMachine = result.normalized_machines?.[0]
      if (firstUploadedMachine?.id) {
        setSelectedMachineId(firstUploadedMachine.id)
        return
      }

      const firstUploadedRecord = result.normalized_records?.find((record) => record.machine_id)
      if (firstUploadedRecord?.machine_id) {
        setSelectedMachineId(firstUploadedRecord.machine_id)
      }
    } catch (uploadFailure) {
      const message = uploadFailure instanceof Error ? uploadFailure.message : 'Unable to upload CSV'
      setUploadError(message)
    } finally {
      setIsUploading(false)
    }
  }, [loadDashboard])

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      void loadDashboard()
    }, 0)

    return () => window.clearTimeout(loadTimer)
  }, [loadDashboard])

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const health = await fetchJson<HealthResponse>('/api/health')
        setSystemHealth(String(health.status ?? '').toLowerCase() === 'ok' ? 'ok' : 'down')
      } catch {
        setSystemHealth('down')
      }
    }

    void checkHealth()
    const interval = window.setInterval(() => {
      void checkHealth()
    }, 30000)

    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!selectedMachineId) {
      const clearTimer = window.setTimeout(() => {
        setMachineDetail(null)
      }, 0)

      return () => window.clearTimeout(clearTimer)
    }

    const loadTimer = window.setTimeout(() => {
      void loadMachineDetail(selectedMachineId)
    }, 0)

    return () => window.clearTimeout(loadTimer)
  }, [loadMachineDetail, selectedMachineId])

  const selectedMachine = useMemo(
    () => dashboardData.machines.find((machine) => machine.id === selectedMachineId) ?? null,
    [dashboardData.machines, selectedMachineId],
  )

  const summaryCards: SummaryCard[] = [
    {
      label: 'Total Machines',
      value: dashboardData.summary?.totalMachines,
      tone: 'steel',
      icon: 'robot',
    },
    {
      label: 'Healthy Machines',
      value: dashboardData.summary?.healthyCount,
      tone: 'green',
      icon: 'healthyStatus',
    },
    {
      label: 'Warning Machines',
      value: dashboardData.summary?.warningCount,
      tone: 'amber',
      icon: 'warningStatus',
    },
    {
      label: 'Critical Machines',
      value: dashboardData.summary?.criticalCount,
      tone: 'danger',
      icon: 'criticalStatus',
    },
  ]

  return (
    <div className="min-h-screen">
      <div className="dashboard-shell">
        <aside className="sidebar">
          <div className="brand-lockup">
            <img className="brand-logo" src="/icon.png" alt="" />
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Hackathon Build</p>
              <h1>Machine Memory</h1>
            </div>
          </div>

          <nav className="mt-8 space-y-2" aria-label="Primary navigation">
            {navItems.map((item) => (
              <button
                key={item.label}
                className={`nav-item ${item.page === activePage ? 'is-active' : ''}`}
                onClick={item.page ? () => setActivePage(item.page as ActivePage) : undefined}
                type="button"
              >
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>

          <div className="sidebar-status-footer">
            <div className={`system-status-card ${systemHealth === 'ok' ? 'is-operational' : 'is-down'}`}>
              <span className="system-status-heading">
                <i></i>
                System Status
              </span>
              <strong>
                <i></i>
                {systemHealth === 'ok' ? 'All Systems Operational' : 'Backend Unavailable'}
              </strong>
            </div>
            <span className="app-version">{APP_VERSION}</span>
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="topbar">
            <div className="search-box">
              <Icon name="search" />
              <input aria-label="Search" placeholder="Search machines, issues, logs..." type="search" />
            </div>
            <div className="flex items-center gap-3">
              <button className="icon-button" type="button" aria-label="Notifications">
                <Icon name="bell" />
              </button>
              <div className="user-chip">
                <div className="avatar">--</div>
                <span>Alex Engineer</span>
                <Icon name="chevron" />
              </div>
            </div>
          </header>

          {activePage === 'uploadLogs' ? (
            <UploadLogsPage />
          ) : activePage === 'machines' ? (
            <MachinesPage />
          ) : activePage === 'aiInsights' ? (
            <AIInsightsPage />
          ) : (
            <>
              {error ? (
                <section className="mb-4">
                  <ErrorBanner message={error} onRetry={loadDashboard} />
                </section>
              ) : null}

              <section className="grid gap-4 xl:grid-cols-4 md:grid-cols-2">
                {summaryCards.map((card) => (
                  <article className={`summary-card ${card.tone}`} key={card.label}>
                    <div className="summary-icon">
                      <Icon name={card.icon} />
                    </div>
                    <div>
                      <p>{card.label}</p>
                      <strong>{isLoading ? 'Loading...' : displayValue(card.value)}</strong>
                    </div>
                  </article>
                ))}
              </section>

              <section className="dashboard-workbench mt-4">
                <div className="dashboard-support-column">
                  <UploadPreviewPanel
                    isUploading={isUploading}
                    onUpload={handleCsvUpload}
                    uploadError={uploadError}
                  />

                  <RecentLogsPanel logs={dashboardData.recentLogs} compact />
                  <AlertsPanel alerts={dashboardData.alerts} compact />
                </div>

                <div className="dashboard-main-column">
                  <div className="factory-workspace">
                    <FactoryMapPanel
                      error={error}
                      factoryMap={dashboardData.factoryMap}
                      isLoading={isLoading}
                      machines={dashboardData.machines}
                      onRetry={loadDashboard}
                      onSelectMachine={setSelectedMachineId}
                      selectedMachineId={selectedMachineId}
                    />
                  </div>

                  <MachineDetailPanel
                    detail={machineDetail}
                    error={detailError}
                    isAnalyzing={isAnalyzing}
                    isLoading={detailLoading}
                    machine={selectedMachine}
                    onAnalyze={analyzeMachine}
                  />
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  )
}

function UploadPreviewPanel({
  isUploading,
  onUpload,
  uploadError,
}: {
  isUploading: boolean
  onUpload: (file: File) => Promise<void>
  uploadError: string | null
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const handleFileSelection = (fileList: FileList | null) => {
    const selectedFile = fileList?.[0]
    if (selectedFile) {
      void onUpload(selectedFile)
    }
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    handleFileSelection(event.dataTransfer.files)
  }

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    handleFileSelection(event.currentTarget.files)
    event.currentTarget.value = ''
  }

  return (
    <article className="panel upload-control-panel">
      <PanelHeader title="Ingest Logs" />

      <div
        className={`upload-dropzone ${isUploading ? 'is-uploading' : ''}`}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          accept=".csv,text/csv"
          aria-label="Ingest Logs"
          hidden
          onChange={handleInputChange}
          type="file"
        />
        <Icon name="upload" />
        <strong>{uploadError ? 'Upload failed. Try again.' : 'Ingest logs here'}</strong>
        <button disabled={isUploading} onClick={() => fileInputRef.current?.click()} type="button">
          {isUploading ? 'Uploading...' : 'Browse Files'}
        </button>
      </div>
    </article>
  )
}

function FactoryMapPanel({
  error,
  factoryMap,
  isLoading,
  machines,
  onRetry,
  onSelectMachine,
  selectedMachineId,
}: {
  error: string | null
  factoryMap: FactoryMapData
  isLoading: boolean
  machines: Machine[]
  onRetry: () => void
  onSelectMachine: (machineId: string) => void
  selectedMachineId: string | null
}) {
  const machineLookup = useMemo(() => {
    const lookup = new Map<string, Machine>()

    machines.forEach((machine) => {
      if (machine.id) {
        lookup.set(machine.id, machine)
      }

      if (machine.machine_id) {
        lookup.set(machine.machine_id, machine)
      }
    })

    return lookup
  }, [machines])

  return (
    <article className="panel section-three-panel min-h-[440px]">
      <PanelHeader title="Map Machines" />
      <div className="section-three-layout mt-5">
        <div className="section-three-map">
          <div className="factory-map">
            {isLoading ? (
              <div className="map-state">
                <span className="loading-ring" aria-hidden="true"></span>
                <strong>Loading factory map</strong>
                <p>Reading machine and layout data from the backend.</p>
              </div>
            ) : error ? (
              <div className="map-state error-state">
                <Icon name="warning" />
                <strong>Unable to load factory map data</strong>
                <p>Start FastAPI on localhost:8000, then retry. Details: {error}</p>
                <button onClick={onRetry} type="button">Retry</button>
              </div>
            ) : factoryMap.layout.length === 0 ? (
              <div className="map-state">
                <Icon name="pin" />
                <strong>No factory map data available</strong>
                <p>Connect machines from the backend to populate this view.</p>
              </div>
            ) : (
              <>
                <div className="factory-zone-grid">
                  {FACTORY_ZONE_GRID.map((zone) => (
                    <section className="factory-zone-panel" key={zone.title}>
                      <div className="factory-zone-header">
                        <span className="factory-zone-icon" aria-hidden="true">
                          <Icon name={zone.icon} />
                        </span>
                        <span>
                          <strong>{zone.title}</strong>
                          <small>{zone.code}</small>
                        </span>
                      </div>

                      <div className={`factory-machine-list ${zone.machineIds.length === 1 ? 'single-machine' : ''}`}>
                        {zone.machineIds.map((machineId) => {
                          const machine = machineLookup.get(machineId)
                          const machineStatus = statusClass(machine?.status)
                          const isSelected = selectedMachineId === machineId

                          return (
                            <button
                              className={`factory-machine-card ${machineStatus} ${isSelected ? 'is-selected' : ''}`}
                              key={machineId}
                              onClick={() => onSelectMachine(machineId)}
                              type="button"
                            >
                              <span className="factory-machine-icon" aria-hidden="true">
                                <Icon name={zone.machineIcon} />
                              </span>
                              <span className="factory-machine-copy">
                                <span className="factory-machine-id">{machineId}</span>
                                <span className="factory-machine-name">
                                  {displayValue(machine?.name ?? FACTORY_MACHINE_NAMES[machineId])}
                                </span>
                              </span>
                              <span className="factory-status-dot" aria-label={`${displayValue(machine?.status)} status`}></span>
                            </button>
                          )
                        })}
                      </div>
                    </section>
                  ))}
                </div>

                <div className="factory-map-legend">
                  <span><i className="legend-dot healthy"></i>Healthy</span>
                  <span><i className="legend-dot warning"></i>Warning</span>
                  <span><i className="legend-dot critical"></i>Critical</span>
                  <span><i className="legend-dot selected"></i>Selected</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}

function MachineDetailPanel({
  detail,
  error,
  isAnalyzing,
  isLoading,
  machine,
  onAnalyze,
}: {
  detail: MachineDetail | null
  error: string | null
  isAnalyzing: boolean
  isLoading: boolean
  machine: Machine | null
  onAnalyze: () => void
}) {
  const displayMachine = detail?.machine ?? machine
  const analysis = detail?.analysis ?? null
  const operationalSummary = detail?.operationalSummary ?? null
  const operationalSignals = detail?.operationalSignals ?? detail?.riskSignals ?? []
  const historicalEvents = detail?.similarHistoricalEvents ?? []
  const attentionLevel = detail?.attentionLevel ?? displayMachine?.status
  const analysisItems = [
    { label: 'Summary', value: analysis?.summary ?? analysis?.predictedIssue },
    { label: 'Urgency', value: analysis?.urgency },
    { label: 'Downtime if ignored', value: analysis?.predictedDowntimeIfIgnored },
    { label: 'Reasoning', value: analysis?.downtimeReasoning ?? analysis?.rootCause },
    { label: 'Next step', value: analysis?.recommendedNextStep ?? analysis?.recommendedAction },
    { label: 'Confidence', value: analysis?.confidence },
  ].filter((item) => hasReportedValue(item.value))

  return (
    <article className="panel detail-panel detail-panel-compact">
      <PanelHeader title="Score Risk" />

      {isLoading ? (
        <LoadingState message="Loading machine detail" />
      ) : error ? (
        <ErrorBlock message={error} />
      ) : !displayMachine ? (
        <div className="machine-select-prompt">
          <Icon name="machine" />
          <strong>Select a machine on the factory map to calculate risk.</strong>
        </div>
      ) : (
        <div className="selected-machine-summary">
          <section className="selected-machine-identity">
            <span>Machine Profile</span>
            <div className="selected-title-row">
              <h2>{displayValue(displayMachine.id)}</h2>
              <span className={`risk-pill ${statusClass(attentionLevel)}`}>{displayValue(attentionLevel)}</span>
            </div>
            <p>{displayValue(displayMachine.name)}</p>
            <div className="machine-tag-row">
              <span>{displayValue(displayMachine.type)}</span>
              <span>{displayValue(displayMachine.location ?? displayMachine.zone)}</span>
            </div>
            <button className="compact-action-button" disabled={isAnalyzing} onClick={onAnalyze} type="button">
              {isAnalyzing ? 'Analyzing...' : 'Analyze with AI'}
              <Icon name="arrow" />
            </button>
          </section>

          <section className="compact-metric-grid">
            <Metric
              label="Matching History"
              support="Maintenance records matched to this machine."
              value={displayValue(operationalSummary?.matchingHistoryRecords)}
            />
            <Metric
              label="Recent Records"
              support="Latest uploaded records tied to this asset."
              value={displayValue(operationalSummary?.recentUploadedRecords)}
            />
            <Metric
              label="High/Critical Logs"
              support="Severe logged events found in history."
              value={displayValue(operationalSummary?.highCriticalLogs)}
            />
            <Metric
              label="Logged Downtime"
              support="Total downtime reported in maintenance logs."
              value={displayMinutes(operationalSummary?.totalLoggedDowntimeMinutes)}
            />
          </section>

          <section className="compact-insight-grid">
            <div className="compact-insight-card">
              <h3>Signals</h3>
              <div className="detail-card-content">
                {operationalSignals.length ? (
                  <ul className="compact-signal-list">
                    {operationalSignals.map((signal) => (
                      <li key={signal}>{signal}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No matching patterns yet.</p>
                )}
              </div>
            </div>

            <div className="compact-insight-card">
              <h3>Similar Past Fix</h3>
              <div className="detail-card-content">
                {historicalEvents.length ? (
                  <div className="historical-event-list">
                    {historicalEvents.map((event, index) => (
                      <article className="historical-event-card" key={`${event.date}-${event.machineId}-${event.pattern}-${index}`}>
                        <div className="historical-event-header">
                          <strong>{displayValue(event.pattern ?? event.issue)}</strong>
                          <span>{displayMinutes(event.downtimeMinutes)}</span>
                        </div>
                        <p>{displayValue(event.issue ?? event.note)}</p>
                        <span className="event-resolution">{displayValue(event.resolution)}</span>
                        <div className="event-meta-row">
                          <time>{displayValue(event.date)}</time>
                          <span>{displayValue(event.source ?? event.machineId)}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <p>No matching events yet.</p>
                )}
              </div>
            </div>

            <div className="compact-insight-card ai-card">
              <h3>AI Analysis</h3>
              <div className="detail-card-content">
                {isAnalyzing ? (
                  <p>Reviewing selected machine history with AI...</p>
                ) : hasAnalysisValues(analysis) ? (
                  <div className="analysis-summary-list">
                    {analysisItems.map((item) => (
                      <div className="analysis-summary-row" key={item.label}>
                        <span>{item.label}</span>
                        <strong>{displayValue(item.value)}</strong>
                      </div>
                    ))}
                    {analysis?.evidence?.length ? (
                      <div className="analysis-evidence-list">
                        <span>Evidence</span>
                        <ul>
                          {analysis.evidence.map((item) => (
                            <li key={item}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p>No AI analysis has been run yet.</p>
                )}
              </div>
            </div>
          </section>
        </div>
      )}
    </article>
  )
}

function RecentLogsPanel({ compact = false, logs }: { compact?: boolean; logs: RecentLog[] }) {
  if (compact) {
    return (
      <section className="context-section compact-logs">
        <PanelHeader title="Maintenance Memory" />
        <div className="scroll-box mt-3 space-y-2">
          {logs.length > 0 ? (
            logs.map((log) => (
              <div className="compact-log-row" key={`${log.time}-${log.machineId}-${log.event}`}>
                <div>
                  <strong>{displayValue(log.machineId)}</strong>
                  <span>{displayValue(log.event)}</span>
                </div>
                <div>
                  <time>{displayValue(log.time)}</time>
                  <span className={`status-badge ${statusClass(log.status)}`}>{displayValue(log.status)}</span>
                </div>
              </div>
            ))
          ) : (
            <EmptyState title="No values yet" message="Maintenance records from the backend will appear here." compact />
          )}
        </div>
      </section>
    )
  }

  return (
    <article className="panel">
      <PanelHeader title="Maintenance Memory" />
      <div className="mt-4 overflow-hidden rounded-lg border border-slate-200">
        {logs.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Machine</th>
                <th>Event</th>
                <th>Downtime</th>
                <th>Technician</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={`${log.time}-${log.machineId}-${log.event}`}>
                  <td>{displayValue(log.time)}</td>
                  <td className="font-bold text-slate-800">{displayValue(log.machineId)}</td>
                  <td>{displayValue(log.event)}</td>
                  <td>{displayMinutes(log.downtimeMinutes)}</td>
                  <td>{displayValue(log.technician)}</td>
                  <td>
                    <span className={`status-badge ${statusClass(log.status)}`}>{displayValue(log.status)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="No values yet" message="Maintenance records from the backend will appear here." />
        )}
      </div>
      <button className="link-button mt-4" type="button">
        View all logs
        <Icon name="arrow" />
      </button>
    </article>
  )
}

function AlertsPanel({ compact = false, alerts }: { compact?: boolean; alerts: Alert[] }) {
  const content = alerts.length > 0 ? (
    alerts.map((alert) => (
      <div className={`alert-row ${compact ? 'compact' : ''} ${statusClass(alert.level)}`} key={`${alert.message}-${alert.timestamp}`}>
        <Icon name={statusClass(alert.level) === 'healthy' ? 'info' : 'warning'} />
        <span>{displayValue(alert.message)}</span>
        <time>{displayValue(alert.timestamp)}</time>
      </div>
    ))
  ) : (
    <EmptyState title="No values yet" message="Backend alerts will appear here." compact={compact} />
  )

  if (compact) {
    return (
      <section className="context-section compact-alerts">
        <PanelHeader title="Live Signals" />
        <div className="scroll-box mt-3 space-y-2">{content}</div>
      </section>
    )
  }

  return (
    <article className="panel">
      <PanelHeader title="Live Signals" />
      <div className="mt-4 space-y-3">{content}</div>
      <button className="link-button mt-4" type="button">
        View all alerts
        <Icon name="arrow" />
      </button>
    </article>
  )
}

function PanelHeader({ eyebrow, title }: { eyebrow?: string; title: string }) {
  return (
    <div className="panel-header">
      {eyebrow ? <span>{eyebrow}.</span> : null}
      <h2>{title}</h2>
    </div>
  )
}

function Metric({ label, support, value }: { label: string; support?: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {support ? <p>{support}</p> : null}
    </div>
  )
}

function EmptyState({ compact = false, message, title }: { compact?: boolean; message: string; title: string }) {
  return (
    <div className={`empty-state ${compact ? 'compact' : ''}`}>
      <strong>{title}</strong>
      <p>{message}</p>
    </div>
  )
}

function LoadingState({ message }: { message: string }) {
  return (
    <div className="loading-card">
      <span className="loading-ring" aria-hidden="true"></span>
      <strong>{message}</strong>
    </div>
  )
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="error-banner">
      <Icon name="warning" />
      <div>
        <strong>Backend data could not be loaded</strong>
        <p>{message}</p>
      </div>
      <button onClick={onRetry} type="button">Retry</button>
    </div>
  )
}

function ErrorBlock({ message }: { message: string }) {
  return (
    <div className="empty-state error-copy">
      <strong>Unable to load values</strong>
      <p>{message}</p>
    </div>
  )
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)

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

function displayValue(value: unknown): string {
  if (!hasReportedValue(value)) {
    return EMPTY_VALUE
  }

  return String(value)
}

function displayMinutes(value: unknown): string {
  if (!hasReportedValue(value)) {
    return EMPTY_VALUE
  }

  return `${String(value)} min`
}

function hasReportedValue(value: unknown): boolean {
  return value !== null && value !== undefined && value !== ''
}

function statusClass(status: unknown): string {
  const normalizedStatus = String(status ?? '').toLowerCase()

  if (normalizedStatus === 'critical' || normalizedStatus === 'high' || normalizedStatus === 'high risk') {
    return 'critical'
  }

  if (normalizedStatus === 'warning' || normalizedStatus === 'watch' || normalizedStatus === 'issue') {
    return 'warning'
  }

  if (normalizedStatus === 'healthy' || normalizedStatus === 'closed' || normalizedStatus === 'info' || normalizedStatus === 'observed') {
    return 'healthy'
  }

  return 'unknown'
}

function hasAnalysisValues(analysis: MachineAnalysis | null): boolean {
  if (!analysis) {
    return false
  }

  return Boolean(
    hasReportedValue(analysis.summary) ||
    hasReportedValue(analysis.predictedDowntimeIfIgnored) ||
    hasReportedValue(analysis.downtimeReasoning) ||
    Boolean(analysis.evidence?.length) ||
    hasReportedValue(analysis.recommendedNextStep) ||
    hasReportedValue(analysis.predictedIssue) ||
    hasReportedValue(analysis.rootCause) ||
    hasReportedValue(analysis.recommendedAction) ||
    hasReportedValue(analysis.urgency) ||
    hasReportedValue(analysis.estimatedDowntimeHours) ||
    hasReportedValue(analysis.estimatedSavings) ||
    hasReportedValue(analysis.confidence),
  )
}

function Icon({ name }: { name: string }) {
  const common = {
    className: 'app-icon',
    fill: 'none',
    stroke: 'currentColor',
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    strokeWidth: 1.8,
    viewBox: '0 0 24 24',
  }

  if (name === 'grid') {
    return (
      <svg {...common}><path d="M4 4h7v7H4z" /><path d="M13 4h7v7h-7z" /><path d="M4 13h7v7H4z" /><path d="M13 13h7v7h-7z" /></svg>
    )
  }

  if (name === 'upload') {
    return (
      <svg {...common}><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M5 18h14" /><path d="M5 18v2h14v-2" /></svg>
    )
  }

  if (name === 'pin') {
    return (
      <svg {...common}><path d="M12 21s6-5.2 6-11a6 6 0 0 0-12 0c0 5.8 6 11 6 11Z" /><circle cx="12" cy="10" r="2" /></svg>
    )
  }

  if (name === 'press') {
    return (
      <svg {...common}>
        <rect x="4" y="3.5" width="16" height="3.5" rx="1" />
        <rect x="3" y="19" width="18" height="2" rx=".5" />
        <path d="M6 7v12" />
        <path d="M18 7v12" />
        <path d="M10 7v4" />
        <rect x="9" y="11" width="6" height="3" rx=".6" />
        <path d="M12 14v2" />
        <rect x="7.5" y="16" width="9" height="2.3" rx=".6" />
        <path d="M5 19h14" />
        <path d="M6.3 5.2h.01" />
        <path d="M17.7 5.2h.01" />
      </svg>
    )
  }

  if (name === 'welding') {
    return (
      <svg {...common}>
        <rect x="4" y="19" width="8" height="2" rx=".5" />
        <path d="M7 19v-5.5" />
        <circle cx="7" cy="13" r="2" />
        <path d="M8.4 11.6 13 6.8" />
        <circle cx="14.2" cy="5.8" r="2" />
        <path d="m15.6 7.1 3.1 3.2" />
        <circle cx="19" cy="11" r="1.5" />
        <path d="m19.5 12.4.9 3.5" />
        <path d="M20.4 15.9h1.4" />
        <path d="M18.2 11.9 17 15" />
        <path d="M16.4 17.5h.01" />
        <path d="M14.8 16.2l-.9-.9" />
        <path d="M17.7 16.1l1-.8" />
      </svg>
    )
  }

  if (name === 'compressor') {
    return (
      <svg {...common}>
        <path d="M5 10h13a3 3 0 0 1 3 3v2a3 3 0 0 1-3 3H5a3 3 0 0 1-3-3v-2a3 3 0 0 1 3-3Z" />
        <path d="M5 10c-1 1-1 7 0 8" />
        <path d="M18 10c1 1 1 7 0 8" />
        <rect x="9" y="6" width="5" height="4" rx=".7" />
        <path d="M8 8h7" />
        <circle cx="18" cy="6.5" r="2" />
        <path d="M18 6.5 19.1 5.4" />
        <path d="M6 18v2" />
        <path d="M17 18v2" />
        <path d="M21 14h1.5v2" />
      </svg>
    )
  }

  if (name === 'cnc') {
    return (
      <svg {...common}>
        <path d="M4 20h16" />
        <path d="M5 19V8.5A2.5 2.5 0 0 1 7.5 6H17a2 2 0 0 1 2 2v11" />
        <path d="M7 14h10" />
        <rect x="9" y="4" width="6" height="5" rx=".7" />
        <path d="M12 9v4" />
        <path d="m11 13 1 2 1-2" />
        <rect x="7.5" y="16" width="9" height="2" rx=".5" />
        <path d="M9 16l1-1h4l1 1" />
        <path d="M17 9h1" />
        <path d="M17 11h1" />
      </svg>
    )
  }

  if (name === 'conveyor') {
    return (
      <svg {...common}>
        <rect x="3" y="10" width="18" height="5" rx="2.5" />
        <circle cx="6" cy="12.5" r="1.4" />
        <circle cx="18" cy="12.5" r="1.4" />
        <path d="M7.5 10h9" />
        <path d="M7.5 15h9" />
        <path d="M9 12.5h.01" />
        <path d="M12 12.5h.01" />
        <path d="M15 12.5h.01" />
        <path d="M7 15v5" />
        <path d="M17 15v5" />
        <path d="M5.5 20h3" />
        <path d="M15.5 20h3" />
      </svg>
    )
  }

  if (name === 'paint') {
    return (
      <svg {...common}>
        <path d="M13 5.5h3.4c1.2 0 2.1.9 2.1 2.1v7.8c0 1.2-.9 2.1-2.1 2.1H13" />
        <path d="M14 5.5c-1.2 1.7-1.2 10.3 0 12" />
        <path d="M18.5 9.5h1.6l1.1 2-1.1 2h-1.6" />
        <path d="M12.8 8.2H9.5" />
        <path d="M12.8 14.8H9.5" />
        <path d="M9.5 8.2v6.6" />
        <path d="M9.5 10.2 3 7.5" />
        <path d="M9.5 11.8 2.2 11.8" />
        <path d="M9.5 13.4 3 16.1" />
        <path d="M5.6 8.7h.01" />
        <path d="M4.9 11.8h.01" />
        <path d="M5.8 14.9h.01" />
        <path d="M15.2 8h1" />
        <path d="M15.2 10.2h1" />
        <path d="M15.2 12.4h1" />
      </svg>
    )
  }

  if (name === 'robot') {
    return (
      <svg {...common}>
        <rect x="4" y="9" width="7" height="8" rx="1.2" />
        <rect x="13" y="7" width="7" height="10" rx="1.2" />
        <path d="M6 9V6.5h3V9" />
        <path d="M15 7V4.5h3V7" />
        <path d="M5.5 17v2.5" />
        <path d="M9.5 17v2.5" />
        <path d="M14.5 17v2.5" />
        <path d="M18.5 17v2.5" />
        <path d="M3 20h18" />
        <path d="M6.3 12h2.4" />
        <path d="M6.3 14h2.4" />
        <path d="M15.3 10h2.4" />
        <path d="M15.3 12h2.4" />
        <path d="M15.3 14h2.4" />
      </svg>
    )
  }

  if (name === 'machine') {
    return (
      <svg {...common}><path d="M5 18h14" /><path d="M8 18V9h8v9" /><path d="M9 9l3-5 3 5" /><path d="M7 13h10" /><circle cx="10" cy="12" r=".7" /><circle cx="14" cy="12" r=".7" /></svg>
    )
  }

  if (name === 'bars') {
    return (
      <svg {...common}><path d="M5 20V9" /><path d="M12 20V4" /><path d="M19 20v-7" /></svg>
    )
  }

  if (name === 'search') {
    return (
      <svg {...common}><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 3.5 3.5" /></svg>
    )
  }

  if (name === 'bell') {
    return (
      <svg {...common}><path d="M18 9a6 6 0 0 0-12 0c0 7-2 8-2 8h16s-2-1-2-8" /><path d="M10 21h4" /></svg>
    )
  }

  if (name === 'chevron') {
    return (
      <svg {...common}><path d="m7 9 5 5 5-5" /></svg>
    )
  }

  if (name === 'warning') {
    return (
      <svg {...common}><path d="M12 3 2.5 20h19L12 3Z" /><path d="M12 9v5" /><path d="M12 17h.01" /></svg>
    )
  }

  if (name === 'healthyStatus') {
    return (
      <svg {...common}>
        <path d="M12 21s7-3.8 7-10V5.8L12 3 5 5.8V11c0 6.2 7 10 7 10Z" />
        <path d="m8.5 12.2 2.1 2.1 4.9-5.1" />
      </svg>
    )
  }

  if (name === 'warningStatus') {
    return (
      <svg {...common}>
        <path d="M5 17a8 8 0 1 1 14 0" />
        <path d="M4 17h16" />
        <path d="m12 13 4-4" />
        <path d="M12 13h.01" />
        <path d="M7.5 13.5 6 12" />
        <path d="M16.5 13.5 18 12" />
        <path d="M12 5.5V8" />
      </svg>
    )
  }

  if (name === 'criticalStatus') {
    return (
      <svg {...common}>
        <path d="M12 3 2.8 20h18.4L12 3Z" />
        <path d="M12 8.5v5.2" />
        <path d="M12 17h.01" />
        <path d="M8.5 20h7" />
      </svg>
    )
  }

  if (name === 'clipboard') {
    return (
      <svg {...common}><path d="M9 4h6l1 2h3v15H5V6h3l1-2Z" /><path d="M9 10h6" /><path d="M9 14h6" /><path d="M9 18h4" /></svg>
    )
  }

  if (name === 'clock') {
    return (
      <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
    )
  }

  if (name === 'arrow') {
    return (
      <svg {...common}><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></svg>
    )
  }

  if (name === 'info') {
    return (
      <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 11v5" /><path d="M12 8h.01" /></svg>
    )
  }

  return (
    <svg {...common}><circle cx="12" cy="12" r="8" /></svg>
  )
}

export default App
