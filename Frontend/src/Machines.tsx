import { AnimatePresence, motion } from 'framer-motion'
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import assemblyLineImage from './assets/assembly-line.png'
import cncImage from './assets/2-cnc-1-2.png'
import compressorImage from './assets/compressor.png'
import paintBoothImage from './assets/paint-booth.png'
import pressImage from './assets/2-press-machines.png'
import weldingImage from './assets/welding.png'

const API_BASE_URL = 'http://localhost:8000'
const NOT_REPORTED = 'Not reported'

type MachineListItem = {
  id?: string
  machine_id?: string
  name?: string | null
  type?: string | null
  zone?: string | null
  location?: string | null
  status?: string | null
  criticality?: string | null
  downtimeCostPerMinute?: number | null
}

type MachineIdentity = {
  machineId: string
  machineName: string | null
  machineType: string | null
  zone: string | null
  line: string | null
  location: string | null
  manufacturer: string | null
  model: string | null
  installedDate: string | null
  criticality: string | null
  downtimeCostPerMinute: number | null
  source: string | null
}

type MachineStatusContext = {
  status: string | null
  attentionLevel: string | null
  attentionReasons: string[]
  latestUploadStatus: string | null
  latestSourceFile: string | null
  latestLogTime: string | null
  latestIssue: string | null
}

type MachineSensorContext = {
  temperature: number | string | null
  vibration: number | string | null
  pressure: number | string | null
  runtimeHours: number | null
  errorCount: number | null
  lastMaintenance: string | null
  nextMaintenance: string | null
  maintenanceStatus: string | null
  maintenanceOverdue: boolean | null
  energyUsage: number | null
  throughputPerHour: number | null
}

type MachineBusinessContext = {
  criticality: string | null
  downtimeCostPerMinute: number | null
  estimatedDowntimeMinutes: number | null
  estimatedCostExposure: number | null
}

type MachineDowntimeContext = {
  downtimeCostPerMinute: number | null
  totalLoggedDowntimeMinutes: number
  estimatedCostExposure: number | null
  recordsWithDowntime: number
}

type MachineMaintenanceSummary = {
  matchingHistoryRecords: number
  recentUploadedRecords: number
  warningOrCriticalLogCount: number
  openMaintenanceItems: number
  totalLoggedDowntimeMinutes: number
  totalLaborHours: number
  mostCommonLoggedIssue: string | null
  latestIssue: string | null
  latestLogTime: string | null
  latestSourceFile: string | null
  technicians: string[]
}

type RepeatedPattern = {
  pattern: string
  count: number
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

type MachineRecentLog = {
  sourceRecordId: string | null
  timestampOpened: string | null
  timestampClosed: string | null
  machineId: string
  issue: string | null
  severity: string | null
  status: string | null
  operatorNote: string | null
  resolutionNote: string | null
  downtimeMinutes: number | null
  laborHours: number | null
  technician: string | null
  sourceFile: string | null
  sourceRowNumber: number | null
  uploadId: string | null
  matchedMachine: boolean | null
}

type AffectedUpload = {
  uploadId: string
  fileName: string
  uploadedAt: string
  uploadType: string
  status: string
  machineCount: number
  rowsStored: number
  insertedRows: number
  updatedRows: number
  errorRows: number
  affectedMachineIds: string[]
  warnings?: string[]
}

type MachineDataAvailability = {
  hasRegistryMatch: boolean
  hasMaintenanceHistory: boolean
  hasAffectedUploads: boolean
  hasSensorData: boolean
  missingCoreFields: string[]
}

type MachineProfileResponse = {
  machine: MachineIdentity
  statusContext: MachineStatusContext
  sensorContext: MachineSensorContext
  businessContext: MachineBusinessContext
  maintenanceSummary: MachineMaintenanceSummary
  downtimeContext: MachineDowntimeContext
  riskSignals: string[]
  repeatedPatterns: RepeatedPattern[]
  recentLogs: MachineRecentLog[]
  similarHistoricalEvents: SimilarHistoricalEvent[]
  affectedUploads: AffectedUpload[]
  rawExtractedFields: Record<string, unknown>
  dataAvailability: MachineDataAvailability
}

type DeepReviewRange = {
  low?: number | null
  high?: number | null
}

type DeepReviewFinding = {
  finding?: string
  evidence?: string[]
  severity?: string
  confidence?: string
}

type DeepReviewAction = {
  priority?: number
  action?: string
  why?: string
  supporting_evidence?: string[]
  recommended_timing?: string
  expected_downtime_reduction?: string
  confidence?: string
}

type DeepReviewStructured = {
  machine_id?: string
  machine_name?: string
  review_status?: string
  executive_summary?: string
  current_condition?: {
    assessment?: string
    evidence_strength?: string
    why?: string[]
  }
  key_findings?: DeepReviewFinding[]
  downtime_exposure?: {
    estimated_downtime_range_minutes?: DeepReviewRange
    basis?: string
    estimated_cost_range?: DeepReviewRange & { currency?: string | null }
    cost_basis?: string
    confidence?: string
  }
  preventive_action_plan?: DeepReviewAction[]
  root_cause_hypotheses?: Array<{
    hypothesis?: string
    supporting_evidence?: string[]
    contradicting_or_missing_evidence?: string[]
    confidence?: string
  }>
  monitoring_plan?: Array<{
    signal_to_watch?: string
    why_it_matters?: string
    trigger_for_escalation?: string
  }>
  missing_data?: string[]
  safe_to_run_summary?: string
  final_recommendation?: {
    decision?: string
    reason?: string
    next_best_step?: string
  }
}

type MachineDeepReviewResponse = {
  success?: boolean
  machineId?: string
  machineName?: string | null
  reviewStatus?: string
  agentResponse?: string
  message?: string
  review?: DeepReviewStructured | null
  error?: string | null
  metadata?: Record<string, unknown>
}

type MachineDeepReviewRequest = {
  machineId: string
  selectedMachineContext: Partial<MachineProfileResponse>
  dashboardContext: {
    knownMachineCount: number | null
    frontendSource: string
  }
}

type MachineVisual = {
  id: string
  fallbackName: string
  type: string
  hotspot: {
    x: number
    y: number
    width: number
    height: number
  }
  labelX: number
}

type ZoneVisual = {
  id: string
  title: string
  code: string
  image: string
  imageAlt: string
  machines: MachineVisual[]
}

const ZONES: ZoneVisual[] = [
  {
    id: 'stamping',
    title: 'Stamping',
    code: 'ZONE 01',
    image: pressImage,
    imageAlt: 'Two hydraulic presses',
    machines: [
      { id: 'PRESS-1', fallbackName: 'Hydraulic Press 1', type: 'Hydraulic Press', hotspot: { x: 5, y: 16, width: 42, height: 68 }, labelX: 26 },
      { id: 'PRESS-2', fallbackName: 'Hydraulic Press 2', type: 'Hydraulic Press', hotspot: { x: 53, y: 16, width: 42, height: 68 }, labelX: 74 },
    ],
  },
  {
    id: 'welding',
    title: 'Welding',
    code: 'ZONE 02',
    image: weldingImage,
    imageAlt: 'Robotic welding station',
    machines: [
      { id: 'WELD-1', fallbackName: 'Robotic Welder 1', type: 'Robotic Welder', hotspot: { x: 13, y: 9, width: 74, height: 77 }, labelX: 50 },
    ],
  },
  {
    id: 'utilities',
    title: 'Utilities',
    code: 'ZONE 03',
    image: compressorImage,
    imageAlt: 'Air compressor',
    machines: [
      { id: 'COMP-1', fallbackName: 'Air Compressor 1', type: 'Air Compressor', hotspot: { x: 12, y: 12, width: 76, height: 72 }, labelX: 50 },
    ],
  },
  {
    id: 'machining',
    title: 'Machining',
    code: 'ZONE 04',
    image: cncImage,
    imageAlt: 'Two CNC mills',
    machines: [
      { id: 'CNC-1', fallbackName: 'CNC Mill 1', type: 'CNC Mill', hotspot: { x: 5, y: 15, width: 42, height: 68 }, labelX: 26 },
      { id: 'CNC-2', fallbackName: 'CNC Mill 2', type: 'CNC Mill', hotspot: { x: 53, y: 15, width: 42, height: 68 }, labelX: 74 },
    ],
  },
  {
    id: 'assembly',
    title: 'Assembly',
    code: 'ZONE 05',
    image: assemblyLineImage,
    imageAlt: 'Conveyor assembly line',
    machines: [
      { id: 'CONV-1', fallbackName: 'Main Conveyor 1', type: 'Conveyor', hotspot: { x: 7, y: 27, width: 86, height: 48 }, labelX: 50 },
    ],
  },
  {
    id: 'finishing',
    title: 'Finishing',
    code: 'ZONE 06',
    image: paintBoothImage,
    imageAlt: 'Paint booth',
    machines: [
      { id: 'PAINT-1', fallbackName: 'Paint Booth 1', type: 'Paint Booth', hotspot: { x: 9, y: 12, width: 82, height: 73 }, labelX: 50 },
    ],
  },
]

function MachinesPage() {
  const [machines, setMachines] = useState<MachineListItem[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [selectedMachineId, setSelectedMachineId] = useState<string | null>(null)
  const [machineProfile, setMachineProfile] = useState<MachineProfileResponse | null>(null)
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [deepReview, setDeepReview] = useState<MachineDeepReviewResponse | null>(null)
  const [deepReviewLoading, setDeepReviewLoading] = useState(false)
  const [deepReviewError, setDeepReviewError] = useState<string | null>(null)

  useEffect(() => {
    let ignore = false

    const loadMachines = async () => {
      setListLoading(true)
      setListError(null)

      try {
        const response = await fetchMachines()
        if (!ignore) {
          setMachines(response.machines ?? [])
        }
      } catch (error) {
        if (!ignore) {
          setListError(error instanceof Error ? error.message : 'Unable to load machines')
          setMachines([])
        }
      } finally {
        if (!ignore) {
          setListLoading(false)
        }
      }
    }

    void loadMachines()

    return () => {
      ignore = true
    }
  }, [])

  useEffect(() => {
    if (!selectedMachineId) {
      const clearTimer = window.setTimeout(() => {
        setMachineProfile(null)
        setProfileError(null)
        setDeepReview(null)
        setDeepReviewError(null)
      }, 0)

      return () => window.clearTimeout(clearTimer)
    }

    let ignore = false

    const loadMachineProfile = async () => {
      setProfileLoading(true)
      setProfileError(null)
      setMachineProfile(null)
      setDeepReview(null)
      setDeepReviewError(null)

      try {
        const profile = await fetchMachineProfile(selectedMachineId)
        if (!ignore) {
          setMachineProfile(profile)
          if (!profile) {
            setProfileError('Machine not found.')
          }
        }
      } catch (error) {
        if (!ignore) {
          setProfileError(error instanceof Error ? error.message : 'Unable to load machine profile')
        }
      } finally {
        if (!ignore) {
          setProfileLoading(false)
        }
      }
    }

    void loadMachineProfile()

    return () => {
      ignore = true
    }
  }, [selectedMachineId])

  const machinesById = useMemo(() => {
    const lookup = new Map<string, MachineListItem>()

    for (const machine of machines) {
      const ids = [machine.id, machine.machine_id].filter(Boolean) as string[]
      ids.forEach((id) => lookup.set(id, machine))
    }

    return lookup
  }, [machines])

  const selectedZoneId = useMemo(() => {
    if (!selectedMachineId) {
      return null
    }

    return ZONES.find((zone) => zone.machines.some((machine) => machine.id === selectedMachineId))?.id ?? null
  }, [selectedMachineId])

  const selectedVisual = useMemo(() => {
    if (!selectedMachineId) {
      return null
    }

    return ZONES.flatMap((zone) => zone.machines).find((machine) => machine.id === selectedMachineId) ?? null
  }, [selectedMachineId])

  const handleMachineSelect = useCallback((machineId: string) => {
    setSelectedMachineId(machineId)
  }, [])

  const handleCloseProfile = useCallback(() => {
    setSelectedMachineId(null)
    setMachineProfile(null)
    setProfileError(null)
    setDeepReview(null)
    setDeepReviewError(null)
  }, [])

  const handleDeepReview = useCallback(async () => {
    if (!selectedMachineId) {
      return
    }

    setDeepReviewLoading(true)
    setDeepReviewError(null)
    setDeepReview(null)

    try {
      const response = await requestMachineDeepReview(
        selectedMachineId,
        buildMachineDeepReviewPayload(selectedMachineId, machineProfile, machines.length),
      )
      setDeepReview(response)
      if (!response) {
        setDeepReviewError('Machine not found.')
      } else if (response.success === false) {
        setDeepReviewError(response.error ?? 'Unable to run deep review')
      }
    } catch (error) {
      setDeepReviewError(error instanceof Error ? error.message : 'Unable to run deep review')
    } finally {
      setDeepReviewLoading(false)
    }
  }, [machineProfile, machines.length, selectedMachineId])

  return (
    <section className="machines-page">
      <div className="machines-hero">
        <div>
          <span>Machine Overview</span>
          <h2>Machines</h2>
          <p>Interactive image-based factory view with machine-level maintenance context.</p>
        </div>
        <div className="machines-hero-meter">
          <strong>{listLoading ? 'Loading...' : formatNumber(machines.length || 8)}</strong>
          <span>Registry machines</span>
        </div>
      </div>

      {listError ? (
        <div className="machines-page-alert">
          Backend machine list unavailable. Showing the fixed factory visual map.
        </div>
      ) : null}

      <div className="machines-zone-grid">
        {ZONES.map((zone, index) => {
          const hasSelection = selectedZoneId === zone.id
          const isDimmed = Boolean(selectedMachineId && !hasSelection)

          return (
            <motion.article
              animate={{ opacity: isDimmed ? 0.58 : 1, scale: hasSelection ? 1.015 : 1 }}
              className={`machines-zone-card ${hasSelection ? 'is-selected-zone' : ''}`}
              initial={{ opacity: 0, y: 18 }}
              key={zone.id}
              transition={{ duration: 0.28, delay: index * 0.035, ease: 'easeOut' }}
            >
              <div className="machines-zone-header">
                <div>
                  <span>{zone.code}</span>
                  <h3>{zone.title}</h3>
                </div>
                <small>{zone.machines.length} machine{zone.machines.length === 1 ? '' : 's'}</small>
              </div>

              <div className="machines-image-stage">
                <motion.img
                  alt={zone.imageAlt}
                  animate={{ scale: hasSelection ? 1.035 : 1 }}
                  className="machines-zone-image"
                  draggable={false}
                  src={zone.image}
                  transition={{ duration: 0.35, ease: 'easeOut' }}
                />
                <div className="machines-stage-vignette"></div>
                {zone.machines.map((machine) => {
                  const runtimeMachine = buildRuntimeMachine(machine, machinesById.get(machine.id))
                  const isSelected = selectedMachineId === machine.id

                  return (
                    <motion.button
                      animate={{ scale: isSelected ? 1.04 : 1 }}
                      aria-label={`Select ${machine.id}`}
                      className={`machines-hotspot ${isSelected ? 'is-selected' : ''}`}
                      key={machine.id}
                      onClick={() => handleMachineSelect(machine.id)}
                      style={{
                        height: `${machine.hotspot.height}%`,
                        left: `${machine.hotspot.x}%`,
                        top: `${machine.hotspot.y}%`,
                        width: `${machine.hotspot.width}%`,
                      }}
                      type="button"
                      whileHover={{ scale: 1.035 }}
                      whileTap={{ scale: 0.99 }}
                    >
                      <span className={`machines-hotspot-dot ${statusClass(runtimeMachine.status)}`}></span>
                    </motion.button>
                  )
                })}
              </div>

              <div className="machines-label-row">
                {zone.machines.map((machine) => {
                  const runtimeMachine = buildRuntimeMachine(machine, machinesById.get(machine.id))
                  const isSelected = selectedMachineId === machine.id

                  return (
                    <button
                      className={`machines-label-chip ${isSelected ? 'is-selected' : ''}`}
                      key={machine.id}
                      onClick={() => handleMachineSelect(machine.id)}
                      style={{ '--machine-label-x': `${machine.labelX}%` } as CSSProperties}
                      type="button"
                    >
                      <i className={statusClass(runtimeMachine.status)}></i>
                      <span>
                        <strong>{machine.id}</strong>
                        <small>{runtimeMachine.name}</small>
                      </span>
                    </button>
                  )
                })}
              </div>

              <AnimatePresence>
                {hasSelection && selectedVisual ? (
                  <MachineProfilePanel
                    deepReview={deepReview}
                    deepReviewError={deepReviewError}
                    deepReviewLoading={deepReviewLoading}
                    fallbackMachine={buildRuntimeMachine(selectedVisual, machinesById.get(selectedVisual.id))}
                    loading={profileLoading}
                    onClose={handleCloseProfile}
                    onDeepReview={handleDeepReview}
                    profile={machineProfile}
                    profileError={profileError}
                  />
                ) : null}
              </AnimatePresence>
            </motion.article>
          )
        })}
      </div>
    </section>
  )
}

function MachineProfilePanel({
  deepReview,
  deepReviewError,
  deepReviewLoading,
  fallbackMachine,
  loading,
  onClose,
  onDeepReview,
  profile,
  profileError,
}: {
  deepReview: MachineDeepReviewResponse | null
  deepReviewError: string | null
  deepReviewLoading: boolean
  fallbackMachine: RuntimeMachine
  loading: boolean
  onClose: () => void
  onDeepReview: () => void
  profile: MachineProfileResponse | null
  profileError: string | null
}) {
  const identity = profile?.machine
  const statusContext = profile?.statusContext
  const maintenanceSummary = profile?.maintenanceSummary
  const downtimeContext = profile?.downtimeContext
  const sensorContext = profile?.sensorContext
  const businessContext = profile?.businessContext
  const displayName = displayValue(identity?.machineName ?? fallbackMachine.name)
  const displayId = displayValue(identity?.machineId ?? fallbackMachine.id)
  const status = statusContext?.status ?? fallbackMachine.status

  return (
    <motion.aside
      animate={{ opacity: 1, y: 0 }}
      className="machines-profile-panel"
      exit={{ opacity: 0, y: 12 }}
      initial={{ opacity: 0, y: 16 }}
      transition={{ duration: 0.22, ease: 'easeOut' }}
    >
      <div className="machines-profile-header">
        <div>
          <span>Selected Machine</span>
          <h4>{displayName}</h4>
          <p>{displayId}</p>
        </div>
        <button aria-label="Close machine detail" onClick={onClose} type="button">X</button>
      </div>

      {loading ? (
        <div className="machines-profile-state">Loading machine profile...</div>
      ) : profileError ? (
        <div className="machines-profile-state">{profileError}</div>
      ) : (
        <>
          <div className="machines-profile-status">
            <span className={`machines-status-pill ${statusClass(status)}`}>{toTitleCase(displayValue(status))}</span>
            <p>{displayValue(statusContext?.latestIssue ?? maintenanceSummary?.latestIssue ?? 'No latest issue reported')}</p>
          </div>

          <div className="machines-profile-grid">
            <ProfileFact label="Zone" value={identity?.zone ?? fallbackMachine.zone} />
            <ProfileFact label="Type" value={identity?.machineType ?? fallbackMachine.type} />
            <ProfileFact label="Criticality" value={identity?.criticality ?? businessContext?.criticality ?? fallbackMachine.criticality} />
            <ProfileFact label="Cost / Min" value={formatCurrencyPerMinute(identity?.downtimeCostPerMinute ?? businessContext?.downtimeCostPerMinute)} />
            <ProfileFact label="Manufacturer" value={identity?.manufacturer} />
            <ProfileFact label="Model" value={identity?.model} />
          </div>

          <div className="machines-profile-metrics">
            <ProfileMetric label="History Records" value={formatNumber(maintenanceSummary?.matchingHistoryRecords)} />
            <ProfileMetric label="Recent Records" value={formatNumber(maintenanceSummary?.recentUploadedRecords)} />
            <ProfileMetric label="Warning/Critical" value={formatNumber(maintenanceSummary?.warningOrCriticalLogCount)} />
            <ProfileMetric label="Open Items" value={formatNumber(maintenanceSummary?.openMaintenanceItems)} />
            <ProfileMetric label="Logged Downtime" value={formatMinutes(downtimeContext?.totalLoggedDowntimeMinutes ?? maintenanceSummary?.totalLoggedDowntimeMinutes)} />
            <ProfileMetric label="Labor Hours" value={formatNumber(maintenanceSummary?.totalLaborHours)} />
          </div>

          <div className="machines-profile-columns">
            <ProfileList title="Attention Reasons" items={statusContext?.attentionReasons ?? []} empty="No attention reasons reported." />
            <ProfileList title="Risk Signals" items={profile?.riskSignals ?? []} empty="No risk signals reported." />
          </div>

          <div className="machines-profile-grid compact">
            <ProfileFact label="Temperature" value={sensorContext?.temperature} />
            <ProfileFact label="Vibration" value={sensorContext?.vibration} />
            <ProfileFact label="Pressure" value={sensorContext?.pressure} />
            <ProfileFact label="Runtime Hours" value={sensorContext?.runtimeHours} />
            <ProfileFact label="Last Maintenance" value={sensorContext?.lastMaintenance} />
            <ProfileFact label="Next Maintenance" value={sensorContext?.nextMaintenance} />
          </div>

          <ProfileRecentLogs logs={profile?.recentLogs ?? []} />
          <ProfileSimilarEvents events={profile?.similarHistoricalEvents ?? []} />
          <ProfileAffectedUploads uploads={profile?.affectedUploads ?? []} />

          <div className="machines-deep-review">
            <button disabled={deepReviewLoading} onClick={onDeepReview} type="button">
              {deepReviewLoading ? 'Starting Review...' : 'Deep Orchestrate Machine Review'}
            </button>
            {deepReviewError ? <p className="machines-review-error">{deepReviewError}</p> : null}
            {deepReview ? <DeepReviewResult response={deepReview} /> : null}
          </div>
        </>
      )}
    </motion.aside>
  )
}

type RuntimeMachine = {
  id: string
  name: string
  type: string
  zone: string
  status: string
  criticality: string | null | undefined
}

function buildRuntimeMachine(visual: MachineVisual, backendMachine?: MachineListItem): RuntimeMachine {
  return {
    id: visual.id,
    name: backendMachine?.name ?? visual.fallbackName,
    type: backendMachine?.type ?? visual.type,
    zone: backendMachine?.zone ?? backendMachine?.location ?? NOT_REPORTED,
    status: backendMachine?.status ?? 'unknown',
    criticality: backendMachine?.criticality,
  }
}

function ProfileFact({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="machines-profile-fact">
      <span>{label}</span>
      <strong>{displayValue(value)}</strong>
    </div>
  )
}

function ProfileMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="machines-profile-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ProfileList({ empty, items, title }: { empty: string; items: string[]; title: string }) {
  return (
    <section className="machines-profile-list">
      <h5>{title}</h5>
      {items.length ? (
        <ul>
          {items.slice(0, 5).map((item) => <li key={item}>{item}</li>)}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </section>
  )
}

function ProfileRecentLogs({ logs }: { logs: MachineRecentLog[] }) {
  return (
    <section className="machines-profile-list wide">
      <h5>Recent Logs</h5>
      {logs.length ? (
        <div className="machines-log-list">
          {logs.slice(0, 4).map((log, index) => (
            <article key={`${log.sourceRecordId ?? log.issue}-${index}`}>
              <strong>{displayValue(log.issue)}</strong>
              <span>{formatDate(log.timestampOpened)} - {displayValue(log.severity)} - {displayValue(log.status)}</span>
              <p>{displayValue(log.resolutionNote ?? log.operatorNote)}</p>
            </article>
          ))}
        </div>
      ) : (
        <p>No uploaded maintenance history for this machine yet.</p>
      )}
    </section>
  )
}

function ProfileSimilarEvents({ events }: { events: SimilarHistoricalEvent[] }) {
  return (
    <section className="machines-profile-list wide">
      <h5>Similar Historical Events</h5>
      {events.length ? (
        <div className="machines-log-list">
          {events.slice(0, 3).map((event, index) => (
            <article key={`${event.date ?? event.issue}-${index}`}>
              <strong>{displayValue(event.pattern ?? event.issue)}</strong>
              <span>{formatDate(event.date)} - {formatMinutes(event.downtimeMinutes)}</span>
              <p>{displayValue(event.resolution ?? event.note)}</p>
            </article>
          ))}
        </div>
      ) : (
        <p>No similar historical events reported.</p>
      )}
    </section>
  )
}

function ProfileAffectedUploads({ uploads }: { uploads: AffectedUpload[] }) {
  return (
    <section className="machines-profile-list wide">
      <h5>Affected Uploads</h5>
      {uploads.length ? (
        <div className="machines-upload-list">
          {uploads.slice(0, 4).map((upload) => (
            <span key={upload.uploadId}>
              <strong>{displayValue(upload.fileName)}</strong>
              <small>{formatDate(upload.uploadedAt)} - {formatNumber(upload.rowsStored)} rows</small>
            </span>
          ))}
        </div>
      ) : (
        <p>No affected uploads reported.</p>
      )}
    </section>
  )
}

function DeepReviewResult({ response }: { response: MachineDeepReviewResponse }) {
  const review = response.review
  const status = response.reviewStatus ?? review?.review_status ?? (response.success === false ? 'failed' : 'completed')
  const summary = review?.executive_summary ?? response.message ?? response.error
  const findings = review?.key_findings ?? []
  const actionPlan = review?.preventive_action_plan ?? []
  const downtimeExposure = review?.downtime_exposure
  const finalRecommendation = review?.final_recommendation

  return (
    <div className="machines-review-result">
      <div className="machines-review-heading">
        <span>Orchestrate Review</span>
        <strong>{toTitleCase(displayValue(status))}</strong>
      </div>

      {summary ? <p className="machines-review-summary">{displayValue(summary)}</p> : null}

      {review?.current_condition?.assessment ? (
        <section className="machines-review-section">
          <h5>Current Condition</h5>
          <p>{review.current_condition.assessment}</p>
          {review.current_condition.why?.length ? (
            <ul>
              {review.current_condition.why.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          ) : null}
        </section>
      ) : null}

      {downtimeExposure ? (
        <section className="machines-review-section">
          <h5>Downtime Exposure</h5>
          <div className="machines-review-facts">
            <span>
              <small>Downtime Range</small>
              <strong>{formatReviewMinuteRange(downtimeExposure.estimated_downtime_range_minutes)}</strong>
            </span>
            <span>
              <small>Cost Range</small>
              <strong>{formatReviewCostRange(downtimeExposure.estimated_cost_range)}</strong>
            </span>
            <span>
              <small>Confidence</small>
              <strong>{displayValue(downtimeExposure.confidence)}</strong>
            </span>
          </div>
          <p>{displayValue(downtimeExposure.basis ?? downtimeExposure.cost_basis)}</p>
        </section>
      ) : null}

      {findings.length ? (
        <section className="machines-review-section">
          <h5>Key Findings</h5>
          <div className="machines-review-stack">
            {findings.slice(0, 4).map((finding, index) => (
              <article key={`${finding.finding ?? 'finding'}-${index}`}>
                <strong>{displayValue(finding.finding)}</strong>
                <span>{toTitleCase(displayValue(finding.severity))} - {toTitleCase(displayValue(finding.confidence))} confidence</span>
                {finding.evidence?.length ? <p>{finding.evidence.slice(0, 3).join(' | ')}</p> : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {actionPlan.length ? (
        <section className="machines-review-section">
          <h5>Preventive Action Plan</h5>
          <div className="machines-review-stack">
            {actionPlan.slice(0, 5).map((action, index) => (
              <article key={`${action.priority ?? index}-${action.action ?? 'action'}`}>
                <strong>{displayValue(action.action)}</strong>
                <span>{toTitleCase(displayValue(action.recommended_timing))} - {toTitleCase(displayValue(action.confidence))} confidence</span>
                <p>{displayValue(action.why ?? action.expected_downtime_reduction)}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {finalRecommendation ? (
        <section className="machines-review-section">
          <h5>Final Recommendation</h5>
          <strong>{toTitleCase(displayValue(finalRecommendation.decision))}</strong>
          <p>{displayValue(finalRecommendation.reason)}</p>
          <p>{displayValue(finalRecommendation.next_best_step)}</p>
        </section>
      ) : null}

      {!review && response.agentResponse ? (
        <pre className="machines-review-plain">{response.agentResponse}</pre>
      ) : null}
    </div>
  )
}

async function fetchMachines(): Promise<{ machines: MachineListItem[] }> {
  return fetchJson<{ machines: MachineListItem[] }>('/api/machines')
}

async function fetchMachineProfile(machineId: string): Promise<MachineProfileResponse | null> {
  const response = await fetch(`${API_BASE_URL}/api/machines/${encodeURIComponent(machineId)}`)

  if (response.status === 404) {
    return null
  }

  if (!response.ok) {
    throw new Error('Unable to load machine profile')
  }

  return response.json() as Promise<MachineProfileResponse>
}

function buildMachineDeepReviewPayload(
  machineId: string,
  profile: MachineProfileResponse | null,
  knownMachineCount: number,
): MachineDeepReviewRequest {
  return {
    machineId,
    selectedMachineContext: profile
      ? {
          machine: profile.machine,
          statusContext: profile.statusContext,
          sensorContext: profile.sensorContext,
          businessContext: profile.businessContext,
          maintenanceSummary: profile.maintenanceSummary,
          downtimeContext: profile.downtimeContext,
          riskSignals: profile.riskSignals,
          repeatedPatterns: profile.repeatedPatterns,
          recentLogs: profile.recentLogs,
          similarHistoricalEvents: profile.similarHistoricalEvents,
          affectedUploads: profile.affectedUploads,
          rawExtractedFields: profile.rawExtractedFields,
          dataAvailability: profile.dataAvailability,
        }
      : {},
    dashboardContext: {
      knownMachineCount: knownMachineCount || null,
      frontendSource: 'Machines.tsx',
    },
  }
}

async function requestMachineDeepReview(
  machineId: string,
  payload: MachineDeepReviewRequest,
): Promise<MachineDeepReviewResponse | null> {
  const response = await fetch(`${API_BASE_URL}/api/machines/${encodeURIComponent(machineId)}/deep-review`, {
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json',
    },
    method: 'POST',
  })

  if (response.status === 404) {
    return null
  }

  if (!response.ok) {
    const errorPayload = await readErrorPayload(response)
    throw new Error(errorPayload ?? 'Unable to start machine deep review')
  }

  return response.json() as Promise<MachineDeepReviewResponse>
}

async function readErrorPayload(response: Response): Promise<string | null> {
  try {
    const payload = await response.json()
    if (payload?.detail) {
      return String(payload.detail)
    }
    if (payload?.error) {
      return String(payload.error)
    }
  } catch {
    return null
  }

  return null
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`)

  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`)
  }

  return response.json() as Promise<T>
}

function statusClass(status: unknown): string {
  const normalized = String(status ?? '').toLowerCase()

  if (normalized.includes('critical') || normalized.includes('high') || normalized.includes('failed')) {
    return 'critical'
  }

  if (normalized.includes('warning') || normalized.includes('maintenance') || normalized.includes('medium')) {
    return 'warning'
  }

  if (normalized.includes('healthy') || normalized.includes('closed') || normalized.includes('ok')) {
    return 'healthy'
  }

  return 'unknown'
}

function displayValue(value: unknown): string {
  return value === null || value === undefined || value === '' ? NOT_REPORTED : String(value)
}

function formatNumber(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return NOT_REPORTED
  }

  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) {
    return String(value)
  }

  return new Intl.NumberFormat('en-US').format(numberValue)
}

function formatMinutes(value: unknown): string {
  return value === null || value === undefined || value === '' ? NOT_REPORTED : `${formatNumber(value)} min`
}

function formatReviewMinuteRange(range?: DeepReviewRange): string {
  if (!range || (range.low === null && range.high === null) || (range.low === undefined && range.high === undefined)) {
    return NOT_REPORTED
  }

  if (range.low !== null && range.low !== undefined && range.high !== null && range.high !== undefined) {
    return `${formatNumber(range.low)}-${formatNumber(range.high)} min`
  }

  return formatMinutes(range.low ?? range.high)
}

function formatReviewCostRange(range?: DeepReviewRange & { currency?: string | null }): string {
  if (!range || (range.low === null && range.high === null) || (range.low === undefined && range.high === undefined)) {
    return NOT_REPORTED
  }

  const currency = range.currency || 'USD'
  if (range.low !== null && range.low !== undefined && range.high !== null && range.high !== undefined) {
    return `${formatCurrency(range.low, currency)}-${formatCurrency(range.high, currency)}`
  }

  return formatCurrency(range.low ?? range.high, currency)
}

function formatCurrency(value: unknown, currency = 'USD'): string {
  if (value === null || value === undefined || value === '') {
    return NOT_REPORTED
  }

  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) {
    return String(value)
  }

  try {
    return new Intl.NumberFormat('en-US', { currency, maximumFractionDigits: 0, style: 'currency' }).format(numberValue)
  } catch {
    return new Intl.NumberFormat('en-US', { currency: 'USD', maximumFractionDigits: 0, style: 'currency' }).format(numberValue)
  }
}

function formatCurrencyPerMinute(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return NOT_REPORTED
  }

  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) {
    return String(value)
  }

  return `${new Intl.NumberFormat('en-US', { currency: 'USD', style: 'currency' }).format(numberValue)} / min`
}

function formatDate(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return NOT_REPORTED
  }

  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' }).format(date)
}

function toTitleCase(value: string): string {
  return value
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1).toLowerCase()}`)
    .join(' ')
}

export default MachinesPage
