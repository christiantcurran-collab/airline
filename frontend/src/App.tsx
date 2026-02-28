import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type CanonicalEvent = {
  event_id: string
  occurred_at: string
  source_system: string
  event_type: string
  ticket_number: string
  coupon_number: number | null
  passenger_name?: string | null
  origin: string | null
  destination: string | null
  flight_number: string | null
}

type DashboardPayload = {
  generated_at: string
  bus_backend: string
  storage_backend: string
  total_channels: number
  total_topics: number
  total_events: number
  channels: {
    channel_id: string
    name: string
    protocol: string
    format: string
    file_name: string
    record_count: number
    raw_payload: string
  }[]
  topics: Record<string, { count: number; events: CanonicalEvent[] }>
}

type MatchingSummary = {
  matched: number
  unmatched_issued: number
  unmatched_flown: number
  suspense: number
  total: number
}

type ReconSummary = {
  total_matched: number
  total_breaks: number
  breaks_by_type: Record<string, number>
  breaks_by_severity: Record<string, number>
}

type ReconBreak = {
  id: string
  ticket_number: string
  break_type: string | null
  severity: string
  difference: number | null
  resolution: string
}

type Settlement = {
  id: string
  ticket_number: string
  counterparty: string
  status: string
  our_amount: number
  their_amount: number | null
}

type AuditRecord = {
  id: string
  timestamp: string
  action: string
  component: string
  output_reference: string | null
}

type TicketDetail = {
  ticket_number: string
  state: {
    status: string
    current_amount: number | null
    coupon_statuses: Record<string, string>
    last_modified: string | null
    event_count: number
    currency: string | null
  }
  history: CanonicalEvent[]
}

type PassengerWalkthrough = {
  passenger_name: string
  tickets: string[]
  sales_channels: string[]
  purchase_summary: {
    ticket_number: string
    pnr: string | null
    sales_channel: string
    coupons: number
    total_paid: number | null
    currency: string | null
    journey: string
  }[]
  narrative: string
  result_meaning: string[]
}

type SimulationOperation = {
  id: string
  timestamp: string
  phase: string
  component: string
  title: string
  message: string
  snippet: Record<string, unknown>
}

type SimulationTicket = {
  ticket_number: string
  pnr: string
  passenger_name: string
  source_system: string
  source_vendor: string
  cabin_class: string
  currency: string
  internal_total_amount: number
  external_reported_amount: number
  discrepancy_amount: number
  legs: {
    coupon_number: number
    flight_number: string
    marketing_carrier: string
    operating_carrier: string
    origin: string
    destination: string
    flight_date: string
    internal_amount: number
  }[]
}

type SimulationState = {
  simulation_id: string
  simulated_time: string
  flight: {
    carrier: string
    flight_number: string
    origin: string
    destination: string
    departure_time: string
  } | null
  phase_index: number
  phase_name: string
  phase_status: Record<string, string>
  tickets: SimulationTicket[]
  operations: SimulationOperation[]
  metrics: {
    tickets_generated: number
    coupons_generated: number
    potential_breaks: number
    gross_revenue: number
    bookings_processed: number
    events_appended: number
  }
  database: {
    tables: Record<string, { rows: number; simulation_rows: number }>
    simulation_source_breakdown: Record<string, number>
    sample_events: { ticket_number: string; event_type: string; event_sequence: number }[]
  }
}

type MainTab = 'visualisation' | 'architecture' | 'operations'

const mainTabs: { key: MainTab; label: string }[] = [
  { key: 'visualisation', label: 'Visualisation' },
  { key: 'architecture', label: 'Architecture' },
  { key: 'operations', label: 'Operations' },
]

const pipelineNodes = [
  { key: 'monte_carlo', label: 'Monte Carlo' },
  { key: 'adapter', label: 'Adapter' },
  { key: 'bus', label: 'Bus' },
  { key: 'event_store', label: 'Event Store' },
  { key: 'cqrs_read_model', label: 'Read Model' },
]

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '')
const api = (path: string) => `${apiBaseUrl}${path}`

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(api(path), init)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

function operationNarrative(operation: SimulationOperation): string {
  const snippet = operation.snippet
  const ticket = typeof snippet.ticket_number === 'string' ? snippet.ticket_number : null
  const coupon = typeof snippet.coupon_number === 'number' ? snippet.coupon_number : null
  const eventType = typeof snippet.event_type === 'string' ? snippet.event_type : null

  if (operation.component === 'monte_carlo') {
    const ticketCount = typeof snippet.ticket_count === 'number' ? snippet.ticket_count : 0
    const couponCount = typeof snippet.coupons === 'number' ? snippet.coupons : 0
    return `Simulation created ${ticketCount} tickets and ${couponCount} coupons with realistic variance.`
  }
  if (operation.component === 'adapter') {
    return ticket
      ? `Raw source payload for ${ticket}${coupon ? ` coupon ${coupon}` : ''} was normalized into canonical format.`
      : 'Raw source payload was normalized into canonical format.'
  }
  if (operation.component === 'bus') {
    return eventType
      ? `Canonical event ${eventType} was published on the message bus for downstream consumers.`
      : 'Canonical event was published on the message bus.'
  }
  if (operation.component === 'event_store') {
    return ticket
      ? `Event-sourcing append completed for ${ticket}; immutable history grew by one event.`
      : 'Event appended to immutable lifecycle history.'
  }
  if (operation.component === 'cqrs_read_model') {
    return ticket
      ? `CQRS projection refreshed for ${ticket}; read model is now query-optimized.`
      : 'CQRS read projection updated.'
  }
  return operation.message
}

function App() {
  const [activeTab, setActiveTab] = useState<MainTab>('visualisation')
  const [error, setError] = useState<string | null>(null)
  const [globalLoading, setGlobalLoading] = useState(false)

  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [simulationState, setSimulationState] = useState<SimulationState | null>(null)
  const [simulationLoading, setSimulationLoading] = useState(false)
  const [selectedOperationIndex, setSelectedOperationIndex] = useState(0)

  const [matchingSummary, setMatchingSummary] = useState<MatchingSummary | null>(null)
  const [reconSummary, setReconSummary] = useState<ReconSummary | null>(null)
  const [reconBreaks, setReconBreaks] = useState<ReconBreak[]>([])
  const [settlements, setSettlements] = useState<Settlement[]>([])
  const [passengerWalkthroughs, setPassengerWalkthroughs] = useState<PassengerWalkthrough[]>([])

  const [ticketSearch, setTicketSearch] = useState('125000100001')
  const [ticketDetail, setTicketDetail] = useState<TicketDetail | null>(null)
  const [auditTicket, setAuditTicket] = useState('125000100001')
  const [auditHistory, setAuditHistory] = useState<AuditRecord[]>([])

  const [operationsLoaded, setOperationsLoaded] = useState(false)

  const selectedOperation = useMemo(() => {
    if (!simulationState || simulationState.operations.length === 0) {
      return null
    }
    const maxIndex = simulationState.operations.length - 1
    const safeIndex = Math.max(0, Math.min(selectedOperationIndex, maxIndex))
    return simulationState.operations[safeIndex]
  }, [simulationState, selectedOperationIndex])

  const selectedOperationNarrative = useMemo(() => {
    if (!selectedOperation) {
      return 'Generate a flight to start the walkthrough.'
    }
    return operationNarrative(selectedOperation)
  }, [selectedOperation])

  const issuedEvents = dashboard?.topics['ticket.issued']?.events ?? []
  const scenarioStats = useMemo(() => {
    const tickets = new Set(issuedEvents.map((event) => event.ticket_number))
    const passengers = new Set(issuedEvents.map((event) => event.passenger_name ?? event.ticket_number))
    const flights = new Set(issuedEvents.map((event) => event.flight_number).filter((value): value is string => !!value))
    return {
      passengers: passengers.size,
      tickets: tickets.size,
      flights: flights.size,
      events: dashboard?.total_events ?? 0,
    }
  }, [dashboard, issuedEvents])

  const settlementStatusCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const item of settlements) {
      counts[item.status] = (counts[item.status] ?? 0) + 1
    }
    return counts
  }, [settlements])

  async function loadDashboard(refresh = false) {
    const payload = await fetchJson<DashboardPayload>(refresh ? '/api/dashboard?refresh=true' : '/api/dashboard')
    setDashboard(payload)
  }

  async function loadSimulationState() {
    const state = await fetchJson<SimulationState>('/api/simulation/state')
    setSimulationState(state)
    if (state.operations.length > 0) {
      setSelectedOperationIndex(state.operations.length - 1)
    } else {
      setSelectedOperationIndex(0)
    }
  }

  async function loadOperationsData() {
    const [matching, recon, breaks, settlementRows, passengerRows] = await Promise.all([
      fetchJson<MatchingSummary>('/api/matching/summary'),
      fetchJson<ReconSummary>('/api/recon/summary'),
      fetchJson<ReconBreak[]>('/api/recon/breaks?status=unresolved'),
      fetchJson<Settlement[]>('/api/settlements'),
      fetchJson<PassengerWalkthrough[]>('/api/walkthroughs'),
    ])
    setMatchingSummary(matching)
    setReconSummary(recon)
    setReconBreaks(breaks)
    setSettlements(settlementRows)
    setPassengerWalkthroughs(passengerRows)
  }

  async function refreshAll() {
    setGlobalLoading(true)
    setError(null)
    try {
      await Promise.all([loadDashboard(true), loadSimulationState()])
      if (operationsLoaded || activeTab === 'operations') {
        await loadOperationsData()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unknown error')
    } finally {
      setGlobalLoading(false)
    }
  }

  async function generateFlight() {
    setSimulationLoading(true)
    setError(null)
    try {
      const state = await fetchJson<SimulationState>('/api/simulation/generate-flight', { method: 'POST' })
      setSimulationState(state)
      setSelectedOperationIndex(Math.max(0, state.operations.length - 1))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unknown error')
    } finally {
      setSimulationLoading(false)
    }
  }

  async function processBookings() {
    setSimulationLoading(true)
    setError(null)
    try {
      const state = await fetchJson<SimulationState>('/api/simulation/process-bookings', { method: 'POST' })
      setSimulationState(state)
      setSelectedOperationIndex(Math.max(0, state.operations.length - 1))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unknown error')
    } finally {
      setSimulationLoading(false)
    }
  }

  async function resetSimulation() {
    setSimulationLoading(true)
    setError(null)
    try {
      const state = await fetchJson<SimulationState>('/api/simulation/reset', { method: 'POST' })
      setSimulationState(state)
      setSelectedOperationIndex(0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unknown error')
    } finally {
      setSimulationLoading(false)
    }
  }

  async function loadTicket(ticketNumber: string) {
    setTicketDetail(await fetchJson<TicketDetail>(`/api/tickets/${ticketNumber}`))
  }

  async function loadAudit(ticketNumber: string) {
    setAuditHistory(await fetchJson<AuditRecord[]>(`/api/audit/${ticketNumber}`))
  }

  useEffect(() => {
    setGlobalLoading(true)
    setError(null)
    void Promise.all([loadDashboard(false), loadSimulationState()])
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'unknown error')
      })
      .finally(() => setGlobalLoading(false))
  }, [])

  useEffect(() => {
    if (activeTab !== 'operations' || operationsLoaded) {
      return
    }
    setGlobalLoading(true)
    setError(null)
    void loadOperationsData()
      .then(() => setOperationsLoaded(true))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'unknown error')
      })
      .finally(() => setGlobalLoading(false))
  }, [activeTab, operationsLoaded])

  function onTicketSubmit(event: FormEvent) {
    event.preventDefault()
    void loadTicket(ticketSearch)
  }

  function onAuditSubmit(event: FormEvent) {
    event.preventDefault()
    void loadAudit(auditTicket)
  }

  function previousOperation() {
    setSelectedOperationIndex((current) => Math.max(0, current - 1))
  }

  function nextOperation() {
    const maxIndex = (simulationState?.operations.length ?? 1) - 1
    setSelectedOperationIndex((current) => Math.min(maxIndex, current + 1))
  }

  const operationCount = simulationState?.operations.length ?? 0

  return (
    <div className="app-shell">
      <header className="top-bar">
        <div className="brand-block">
          <h1>Flight Ledger</h1>
          <p>Airline Revenue Accounting Platform</p>
        </div>
        <button className="refresh-button" onClick={() => void refreshAll()} disabled={globalLoading || simulationLoading}>
          {globalLoading ? 'Refreshing...' : 'Refresh Data'}
        </button>
      </header>

      <nav className="main-nav">
        {mainTabs.map((tab) => (
          <button key={tab.key} className={`main-tab ${activeTab === tab.key ? 'active' : ''}`} onClick={() => setActiveTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </nav>

      {error && <section className="error-banner">API error: {error}</section>}

      {activeTab === 'visualisation' && (
        <section className="panel">
          <div className="panel-head">
            <h2>Monte Carlo Simulation Walkthrough</h2>
            <p>Click through every processing step to see exactly how a ticket is transformed and stored.</p>
          </div>

          <div className="control-row">
            <button onClick={() => void generateFlight()} disabled={simulationLoading || (simulationState?.phase_index ?? -1) >= 0}>
              Generate Flight
            </button>
            <button
              onClick={() => void processBookings()}
              disabled={simulationLoading || (simulationState?.phase_index ?? -1) < 0 || (simulationState?.phase_index ?? -1) >= 1}
            >
              Process Bookings
            </button>
            <button onClick={() => void resetSimulation()} disabled={simulationLoading}>
              Reset Simulation
            </button>
          </div>

          <div className="simulation-summary">
            <div>
              <span>Flight</span>
              <strong>
                {simulationState?.flight
                  ? `${simulationState.flight.flight_number} ${simulationState.flight.origin}->${simulationState.flight.destination}`
                  : 'Not generated yet'}
              </strong>
            </div>
            <div>
              <span>Phase</span>
              <strong>{simulationState?.phase_name ?? 'idle'}</strong>
            </div>
            <div>
              <span>Simulated Time</span>
              <strong>{simulationState?.simulated_time ? new Date(simulationState.simulated_time).toLocaleString() : '-'}</strong>
            </div>
            <div>
              <span>Revenue</span>
              <strong>GBP {(simulationState?.metrics.gross_revenue ?? 0).toFixed(2)}</strong>
            </div>
          </div>

          <div className="pipeline-strip">
            {pipelineNodes.map((node) => (
              <div
                key={node.key}
                className={`pipeline-node ${selectedOperation?.component === node.key ? 'active' : ''}`}
              >
                {node.label}
              </div>
            ))}
          </div>

          <div className="visual-grid">
            <article className="card">
              <h3>Generated Tickets</h3>
              <div className="ticket-list">
                {(simulationState?.tickets ?? []).map((ticket) => (
                  <div key={ticket.ticket_number} className="ticket-card">
                    <strong>{ticket.passenger_name}</strong>
                    <p>
                      {ticket.ticket_number} | {ticket.pnr}
                    </p>
                    <p>
                      {ticket.source_system} via {ticket.source_vendor}
                    </p>
                    <p>
                      {ticket.currency} {ticket.internal_total_amount.toFixed(2)} | legs {ticket.legs.length}
                    </p>
                    <p>
                      discrepancy {ticket.currency} {ticket.discrepancy_amount.toFixed(2)}
                    </p>
                  </div>
                ))}
              </div>
            </article>

            <article className="card">
              <h3>Step Timeline ({operationCount})</h3>
              <div className="timeline-list">
                {(simulationState?.operations ?? []).map((operation, index) => (
                  <button
                    key={operation.id}
                    className={`timeline-row ${index === selectedOperationIndex ? 'active' : ''}`}
                    onClick={() => setSelectedOperationIndex(index)}
                  >
                    <span>{index + 1}</span>
                    <div>
                      <strong>{operation.title}</strong>
                      <small>{operation.message}</small>
                    </div>
                  </button>
                ))}
              </div>
            </article>

            <article className="card">
              <h3>Selected Step Explanation</h3>
              {selectedOperation ? (
                <>
                  <p className="explain">{selectedOperationNarrative}</p>
                  <p className="step-meta">
                    {selectedOperation.title} | {new Date(selectedOperation.timestamp).toLocaleTimeString()}
                  </p>
                  <pre>{JSON.stringify(selectedOperation.snippet, null, 2)}</pre>
                  <div className="step-nav">
                    <button onClick={previousOperation} disabled={selectedOperationIndex <= 0}>
                      Previous
                    </button>
                    <button onClick={nextOperation} disabled={selectedOperationIndex >= operationCount - 1}>
                      Next
                    </button>
                  </div>
                </>
              ) : (
                <p className="explain">Run Generate Flight to begin.</p>
              )}
            </article>
          </div>

          <h3 className="subhead">Database Snapshot</h3>
          <pre>{JSON.stringify(simulationState?.database ?? {}, null, 2)}</pre>
        </section>
      )}

      {activeTab === 'architecture' && (
        <section className="panel">
          <div className="panel-head">
            <h2>Architecture</h2>
            <p>
              Canonical events flow from adapters into the message bus, then into event sourcing, CQRS projections, matching,
              reconciliation, settlement saga, and audit lineage.
            </p>
          </div>
          <div className="architecture-metrics">
            <div>
              <span>Passengers</span>
              <strong>{scenarioStats.passengers}</strong>
            </div>
            <div>
              <span>Tickets</span>
              <strong>{scenarioStats.tickets}</strong>
            </div>
            <div>
              <span>Flights</span>
              <strong>{scenarioStats.flights}</strong>
            </div>
            <div>
              <span>Total Events</span>
              <strong>{scenarioStats.events}</strong>
            </div>
          </div>

          <svg className="architecture-diagram" viewBox="0 0 1160 520" role="img" aria-label="FlightLedger architecture flow">
            <rect x="30" y="40" width="220" height="90" rx="12" className="node source" />
            <text x="48" y="76" className="node-title">Source Channels</text>
            <text x="48" y="101" className="node-text">PSS, DCS, GDS, OTA, Interline</text>

            <rect x="300" y="40" width="190" height="90" rx="12" className="node adapter" />
            <text x="318" y="76" className="node-title">Adapters</text>
            <text x="318" y="101" className="node-text">Normalize to canonical events</text>

            <rect x="540" y="40" width="190" height="90" rx="12" className="node bus" />
            <text x="558" y="76" className="node-title">Message Bus</text>
            <text x="558" y="101" className="node-text">{dashboard?.bus_backend ?? 'memory'} topics</text>

            <rect x="780" y="40" width="340" height="90" rx="12" className="node store" />
            <text x="798" y="76" className="node-title">Ticket Lifecycle Store</text>
            <text x="798" y="101" className="node-text">Event sourcing + CQRS projection</text>

            <rect x="110" y="210" width="290" height="90" rx="12" className="node matcher" />
            <text x="130" y="246" className="node-title">Coupon Matching</text>
            <text x="130" y="271" className="node-text">Issued vs flown by ticket/coupon</text>

            <rect x="440" y="210" width="290" height="90" rx="12" className="node recon" />
            <text x="460" y="246" className="node-title">Reconciliation</text>
            <text x="460" y="271" className="node-text">3-way compare + break classification</text>

            <rect x="770" y="210" width="290" height="90" rx="12" className="node settlement" />
            <text x="790" y="246" className="node-title">Settlement Saga</text>
            <text x="790" y="271" className="node-text">calculate -&gt; validate -&gt; submit -&gt; confirm</text>

            <rect x="120" y="370" width="300" height="90" rx="12" className="node audit" />
            <text x="140" y="406" className="node-title">Audit & Lineage</text>
            <text x="140" y="431" className="node-text">Immutable trace for every action</text>

            <rect x="460" y="370" width="300" height="90" rx="12" className="node orchestrator" />
            <text x="480" y="406" className="node-title">DAG Orchestrator</text>
            <text x="480" y="431" className="node-text">Month-end dependency workflow</text>

            <rect x="800" y="370" width="280" height="90" rx="12" className="node api" />
            <text x="820" y="406" className="node-title">API + UI</text>
            <text x="820" y="431" className="node-text">Operational and educational views</text>

            <line x1="250" y1="86" x2="300" y2="86" className="arch-link" />
            <line x1="490" y1="86" x2="540" y2="86" className="arch-link" />
            <line x1="730" y1="86" x2="780" y2="86" className="arch-link" />
            <line x1="948" y1="130" x2="255" y2="210" className="arch-link" />
            <line x1="948" y1="130" x2="585" y2="210" className="arch-link" />
            <line x1="948" y1="130" x2="915" y2="210" className="arch-link" />
            <line x1="260" y1="300" x2="260" y2="370" className="arch-link" />
            <line x1="585" y1="300" x2="610" y2="370" className="arch-link" />
            <line x1="915" y1="300" x2="940" y2="370" className="arch-link" />
          </svg>
        </section>
      )}

      {activeTab === 'operations' && (
        <section className="panel">
          <div className="panel-head">
            <h2>Operations</h2>
            <p>Passenger outcomes, matching, reconciliation, settlements, and direct ticket/audit lookups.</p>
          </div>

          <div className="ops-stats">
            <div>
              <span>Matched Coupons</span>
              <strong>{matchingSummary?.matched ?? 0}</strong>
            </div>
            <div>
              <span>Unresolved Breaks</span>
              <strong>{reconSummary?.total_breaks ?? 0}</strong>
            </div>
            <div>
              <span>Settlements</span>
              <strong>{settlements.length}</strong>
            </div>
            <div>
              <span>Passenger Flows</span>
              <strong>{passengerWalkthroughs.length}</strong>
            </div>
          </div>

          <div className="ops-grid">
            <article className="card">
              <h3>Passenger Outcomes</h3>
              <div className="passenger-list">
                {passengerWalkthroughs.map((flow) => (
                  <div key={flow.passenger_name} className="passenger-card">
                    <strong>{flow.passenger_name}</strong>
                    <p>{flow.narrative}</p>
                    {flow.purchase_summary.map((purchase) => (
                      <p key={purchase.ticket_number}>
                        {purchase.ticket_number} via {purchase.sales_channel}, {purchase.currency} {purchase.total_paid?.toFixed(2)}
                      </p>
                    ))}
                  </div>
                ))}
              </div>
            </article>

            <article className="card">
              <h3>Break Queue</h3>
              <div className="break-list">
                {reconBreaks.slice(0, 20).map((item) => (
                  <div key={item.id} className="break-row">
                    <strong>{item.ticket_number}</strong>
                    <p>
                      {item.break_type ?? 'unknown'} | {item.severity} | diff {item.difference ?? 0}
                    </p>
                  </div>
                ))}
              </div>
              <h4>Settlement Status</h4>
              <pre>{JSON.stringify(settlementStatusCounts, null, 2)}</pre>
            </article>

            <article className="card">
              <h3>Lookup Tools</h3>
              <form className="inline-form" onSubmit={onTicketSubmit}>
                <input value={ticketSearch} onChange={(event) => setTicketSearch(event.target.value)} />
                <button type="submit">Ticket</button>
              </form>
              <form className="inline-form" onSubmit={onAuditSubmit}>
                <input value={auditTicket} onChange={(event) => setAuditTicket(event.target.value)} />
                <button type="submit">Audit</button>
              </form>
              <h4>Ticket State</h4>
              <pre>{JSON.stringify(ticketDetail?.state ?? {}, null, 2)}</pre>
              <h4>Audit History</h4>
              <pre>{JSON.stringify(auditHistory.slice(0, 20), null, 2)}</pre>
            </article>
          </div>
        </section>
      )}
    </div>
  )
}

export default App
