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
  channels: SourceChannel[]
  topics: Record<string, { count: number; events: CanonicalEvent[] }>
}

type SourceChannel = {
  channel_id: string
  name: string
  protocol: string
  format: string
  file_name: string
  record_count: number
  raw_payload: string
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

type AuditRecord = {
  id: string
  timestamp: string
  action: string
  component: string
  output_reference: string | null
}

type DagDef = {
  name: string
  tasks: { name: string; depends_on: string[] }[]
}

type DagRun = {
  run: { id: string; dag_name: string; status: string; started_at: string; completed_at: string | null }
  tasks: {
    id: string
    task_name: string
    status: string
    depends_on: string[]
    started_at: string | null
    completed_at: string | null
    error_message: string | null
  }[]
}

type Settlement = {
  id: string
  ticket_number: string
  counterparty: string
  status: string
  our_amount: number
  their_amount: number | null
}

type SettlementSaga = {
  id: string
  action: string
  from_status: string
  to_status: string
  timestamp: string
}

type PassengerWalkthrough = {
  passenger_name: string
  tickets: string[]
  sales_channels: string[]
  itinerary: {
    ticket_number: string
    pnr: string | null
    coupon_number: number | null
    flight_date: string | null
    flight_number: string | null
    origin: string | null
    destination: string | null
    marketing_carrier: string | null
    operating_carrier: string | null
    gross_amount: number | null
    currency: string | null
    sales_channel: string
    match_status: string
    recon_status: string
    recon_break_type: string | null
  }[]
  steps: {
    ingestion: {
      issued_coupons: number
      source_events: Record<string, number>
    }
    lifecycle: {
      ticket_states: {
        ticket_number: string
        status: string
        event_count: number
        last_event_type: string | null
      }[]
    }
    matching: {
      matched: number
      unmatched_issued: number
      unmatched_flown: number
      suspense: number
    }
    reconciliation: {
      matched: number
      breaks: number
      break_types: Record<string, number>
    }
    settlement: {
      total: number
      statuses: Record<string, number>
    }
    audit: {
      records: number
    }
  }
  narrative: string
}

type TabKey =
  | 'overview'
  | 'architecture'
  | 'passenger'
  | 'ticket'
  | 'matching'
  | 'recon'
  | 'audit'
  | 'orchestrator'
  | 'settlements'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'architecture', label: 'Architecture' },
  { key: 'passenger', label: 'Passenger Flows' },
  { key: 'ticket', label: 'Ticket Explorer' },
  { key: 'matching', label: 'Coupon Matching' },
  { key: 'recon', label: 'Reconciliation' },
  { key: 'audit', label: 'Audit & Lineage' },
  { key: 'orchestrator', label: 'Orchestrator' },
  { key: 'settlements', label: 'Settlements' },
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

function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [selectedChannelId, setSelectedChannelId] = useState<string>('')
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [passengerWalkthroughs, setPassengerWalkthroughs] = useState<PassengerWalkthrough[]>([])

  const [ticketSearch, setTicketSearch] = useState('125000100001')
  const [ticketDetail, setTicketDetail] = useState<TicketDetail | null>(null)

  const [matchingSummary, setMatchingSummary] = useState<MatchingSummary | null>(null)
  const [suspenseItems, setSuspenseItems] = useState<Record<string, unknown>[]>([])

  const [reconSummary, setReconSummary] = useState<ReconSummary | null>(null)
  const [reconBreaks, setReconBreaks] = useState<ReconBreak[]>([])

  const [auditTicket, setAuditTicket] = useState('125000100001')
  const [auditHistory, setAuditHistory] = useState<AuditRecord[]>([])

  const [dags, setDags] = useState<DagDef[]>([])
  const [selectedRun, setSelectedRun] = useState<DagRun | null>(null)

  const [settlements, setSettlements] = useState<Settlement[]>([])
  const [selectedSettlementSaga, setSelectedSettlementSaga] = useState<SettlementSaga[]>([])

  const selectedChannel = useMemo(
    () => dashboard?.channels.find((channel) => channel.channel_id === selectedChannelId) ?? null,
    [dashboard, selectedChannelId]
  )

  const selectedTopicEvents = useMemo(
    () => (dashboard && selectedTopic ? dashboard.topics[selectedTopic]?.events ?? [] : []),
    [dashboard, selectedTopic]
  )

  const scenarioStats = useMemo(() => {
    if (!dashboard) {
      return { passengerCount: 0, ticketCount: 0, flightCount: 0, issuedCount: 0, flownCount: 0, settledCount: 0 }
    }
    const issuedEvents = dashboard.topics['ticket.issued']?.events ?? []
    const flownEvents = dashboard.topics['coupon.flown']?.events ?? []
    const settledEvents = dashboard.topics['settlement.due']?.events ?? []
    const tickets = new Set(issuedEvents.map((event) => event.ticket_number))
    const passengers = new Set(issuedEvents.map((event) => event.passenger_name ?? event.ticket_number))
    const flights = new Set(
      [...issuedEvents, ...flownEvents].map((event) => event.flight_number).filter((flight): flight is string => !!flight)
    )
    return {
      passengerCount: passengers.size,
      ticketCount: tickets.size,
      flightCount: flights.size,
      issuedCount: issuedEvents.length,
      flownCount: flownEvents.length,
      settledCount: settledEvents.length,
    }
  }, [dashboard])

  async function loadOverview(forceRefresh = false) {
    setLoading(true)
    setError(null)
    try {
      const payload = await fetchJson<DashboardPayload>(
        forceRefresh ? '/api/dashboard?refresh=true' : '/api/dashboard'
      )
      setDashboard(payload)
      if (!selectedChannelId) {
        setSelectedChannelId(payload.channels[0]?.channel_id ?? '')
      }
      if (!selectedTopic) {
        setSelectedTopic(Object.keys(payload.topics)[0] ?? '')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'unknown error')
    } finally {
      setLoading(false)
    }
  }

  async function loadTicket(ticketNumber: string) {
    setTicketDetail(await fetchJson<TicketDetail>(`/api/tickets/${ticketNumber}`))
  }

  async function loadMatching() {
    const [summary, suspense] = await Promise.all([
      fetchJson<MatchingSummary>('/api/matching/summary'),
      fetchJson<Record<string, unknown>[]>('/api/matching/suspense?min_age_days=1'),
    ])
    setMatchingSummary(summary)
    setSuspenseItems(suspense)
  }

  async function loadRecon() {
    const [summary, breaks] = await Promise.all([
      fetchJson<ReconSummary>('/api/recon/summary'),
      fetchJson<ReconBreak[]>('/api/recon/breaks?status=unresolved'),
    ])
    setReconSummary(summary)
    setReconBreaks(breaks)
  }

  async function resolveBreak(breakId: string) {
    await fetchJson<{ status: string }>(`/api/recon/breaks/${breakId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolution: 'manually_resolved', notes: 'Resolved from dashboard' }),
    })
    await loadRecon()
  }

  async function loadAudit(ticketNumber: string) {
    setAuditHistory(await fetchJson<AuditRecord[]>(`/api/audit/${ticketNumber}`))
  }

  async function loadDags() {
    setDags(await fetchJson<DagDef[]>('/api/orchestrator/dags'))
  }

  async function runDag(dagName: string) {
    const run = await fetchJson<{ run_id: string }>(`/api/orchestrator/run/${dagName}`, { method: 'POST' })
    setSelectedRun(await fetchJson<DagRun>(`/api/orchestrator/runs/${run.run_id}`))
  }

  async function loadSettlements() {
    setSettlements(await fetchJson<Settlement[]>('/api/settlements'))
  }

  async function loadSettlementSaga(settlementId: string) {
    setSelectedSettlementSaga(await fetchJson<SettlementSaga[]>(`/api/settlements/${settlementId}/saga`))
  }

  async function loadPassengerWalkthroughs() {
    setPassengerWalkthroughs(await fetchJson<PassengerWalkthrough[]>('/api/walkthroughs'))
  }

  useEffect(() => {
    void loadOverview()
  }, [])

  useEffect(() => {
    if (activeTab === 'ticket') {
      void loadTicket(ticketSearch)
    } else if (activeTab === 'overview') {
      if (!matchingSummary) {
        void loadMatching()
      }
      if (!reconSummary) {
        void loadRecon()
      }
      if (settlements.length === 0) {
        void loadSettlements()
      }
      if (passengerWalkthroughs.length === 0) {
        void loadPassengerWalkthroughs()
      }
    } else if (activeTab === 'passenger') {
      void loadPassengerWalkthroughs()
    } else if (activeTab === 'matching') {
      void loadMatching()
    } else if (activeTab === 'recon') {
      void loadRecon()
    } else if (activeTab === 'audit') {
      void loadAudit(auditTicket)
    } else if (activeTab === 'orchestrator') {
      void loadDags()
    } else if (activeTab === 'settlements') {
      void loadSettlements()
    }
  }, [activeTab])

  function onTicketSubmit(event: FormEvent) {
    event.preventDefault()
    void loadTicket(ticketSearch)
  }

  function onAuditSubmit(event: FormEvent) {
    event.preventDefault()
    void loadAudit(auditTicket)
  }

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">FlightLedger Phase 2</p>
        <h1>Revenue Accounting Platform</h1>
        <p className="hero-copy">Event sourcing, matching, reconciliation, lineage, orchestration, and settlements.</p>
        <button className="refresh-btn" onClick={() => void loadOverview(true)} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh Ingestion'}
        </button>
      </section>

      {error && <section className="panel error-panel">API error: {error}</section>}

      <section className="tabbar">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`tab ${activeTab === tab.key ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </section>

      {activeTab === 'overview' && dashboard && (
        <section className="dashboard-grid">
          <article className="panel stats-panel">
            <h2>Pipeline Snapshot</h2>
            <div className="stat-list">
              <div>
                <span>Topics</span>
                <strong>{dashboard.total_topics}</strong>
              </div>
              <div>
                <span>Events</span>
                <strong>{dashboard.total_events}</strong>
              </div>
              <div>
                <span>Bus</span>
                <strong>{dashboard.bus_backend}</strong>
              </div>
              <div>
                <span>Storage</span>
                <strong>{dashboard.storage_backend}</strong>
              </div>
              <div>
                <span>Channels</span>
                <strong>{dashboard.total_channels}</strong>
              </div>
            </div>
          </article>

          <article className="panel channels-panel">
            <h2>Source Channels</h2>
            <div className="channels-layout">
              <div className="channel-list">
                {dashboard.channels.map((channel) => (
                  <button
                    key={channel.channel_id}
                    className={`channel-row ${selectedChannelId === channel.channel_id ? 'active' : ''}`}
                    onClick={() => setSelectedChannelId(channel.channel_id)}
                  >
                    <span>{channel.name}</span>
                    <small>
                      {channel.protocol} | {channel.format} | {channel.record_count}
                    </small>
                  </button>
                ))}
              </div>
              <div className="channel-detail">
                <pre>{selectedChannel?.raw_payload}</pre>
              </div>
            </div>
          </article>

          <article className="panel intuition-panel">
            <h2>Process Intuition</h2>
            <div className="intuition-grid">
              <div className="intuition-card">
                <h3>1. Ingestion</h3>
                <p>
                  {dashboard.total_channels} channels produced {dashboard.total_events} canonical events for this run.
                </p>
              </div>
              <div className="intuition-card">
                <h3>2. Lifecycle Store</h3>
                <p>
                  {scenarioStats.passengerCount} passengers and {scenarioStats.ticketCount} tickets across {scenarioStats.flightCount} flights were replayed into current ticket states.
                </p>
              </div>
              <div className="intuition-card">
                <h3>3. Coupon Matching</h3>
                <p>
                  {matchingSummary
                    ? `${matchingSummary.matched} matched, ${matchingSummary.unmatched_issued} unmatched issued, ${matchingSummary.unmatched_flown} unmatched flown.`
                    : 'Open Coupon Matching for detailed status.'}
                </p>
              </div>
              <div className="intuition-card">
                <h3>4. Reconciliation</h3>
                <p>
                  {reconSummary
                    ? `${reconSummary.total_matched} matched and ${reconSummary.total_breaks} breaks classified for follow-up.`
                    : 'Open Reconciliation to classify breaks by type and severity.'}
                </p>
              </div>
              <div className="intuition-card">
                <h3>5. Settlement Saga</h3>
                <p>{settlements.length} settlement records progressed through calculate, validate, submit, confirm, and reconcile/compensate.</p>
              </div>
            </div>
          </article>

          <article className="panel topics-panel">
            <h2>Topic Throughput</h2>
            <div className="topics-list">
              {Object.entries(dashboard.topics).map(([topic, item]) => (
                <button key={topic} className={`topic-row ${selectedTopic === topic ? 'active' : ''}`} onClick={() => setSelectedTopic(topic)}>
                  <span>{topic}</span>
                  <strong>{item.count}</strong>
                </button>
              ))}
            </div>
          </article>

          <article className="panel events-panel">
            <h2>{selectedTopic}</h2>
            <div className="events-list">
              {selectedTopicEvents.slice(0, 40).map((event) => (
                <div key={event.event_id} className="event-card">
                  <header>
                    <span className="event-type">{event.event_type}</span>
                    <time>{new Date(event.occurred_at).toLocaleString()}</time>
                  </header>
                  <p>
                    {event.ticket_number} | coupon {event.coupon_number ?? '-'} | {event.origin ?? '---'} to{' '}
                    {event.destination ?? '---'}
                  </p>
                </div>
              ))}
            </div>
          </article>
        </section>
      )}

      {activeTab === 'architecture' && (
        <section className="panel tab-panel">
          <h2>Architecture Diagram</h2>
          <p className="tab-copy">
            Scenario date: 2026-02-27. {scenarioStats.passengerCount || 6} passengers and {scenarioStats.issuedCount || 10} issued coupons across {scenarioStats.flightCount || 3} flights flow through adapters, event bus, lifecycle store, matching, reconciliation, settlement, and audit.
          </p>
          <svg className="arch-diagram" viewBox="0 0 1160 520" role="img" aria-label="FlightLedger architecture flow">
            <rect x="30" y="40" width="220" height="90" rx="14" className="arch-node source" />
            <text x="50" y="76" className="arch-title">Source Channels</text>
            <text x="50" y="102" className="arch-text">PSS, DCS, GDS, OTA, Interline</text>

            <rect x="300" y="40" width="200" height="90" rx="14" className="arch-node adapter" />
            <text x="320" y="76" className="arch-title">Adapters</text>
            <text x="320" y="102" className="arch-text">Normalize to CanonicalEvent</text>

            <rect x="550" y="40" width="200" height="90" rx="14" className="arch-node bus" />
            <text x="570" y="76" className="arch-title">Message Bus</text>
            <text x="570" y="102" className="arch-text">{dashboard?.bus_backend ?? 'memory'} topics by ticket</text>

            <rect x="800" y="40" width="320" height="90" rx="14" className="arch-node store" />
            <text x="820" y="76" className="arch-title">Ticket Lifecycle Store (Event Sourcing)</text>
            <text x="820" y="102" className="arch-text">Append-only history + CQRS current-state view</text>

            <rect x="120" y="210" width="280" height="90" rx="14" className="arch-node matcher" />
            <text x="140" y="246" className="arch-title">Coupon Matching Engine</text>
            <text x="140" y="272" className="arch-text">Issued vs flown, suspense aging</text>

            <rect x="440" y="210" width="280" height="90" rx="14" className="arch-node recon" />
            <text x="460" y="246" className="arch-title">Reconciliation Engine</text>
            <text x="460" y="272" className="arch-text">3-way match + break classification</text>

            <rect x="760" y="210" width="280" height="90" rx="14" className="arch-node settle" />
            <text x="780" y="246" className="arch-title">Settlement Saga Engine</text>
            <text x="780" y="272" className="arch-text">Calculate -&gt; validate -&gt; submit -&gt; confirm</text>

            <rect x="120" y="370" width="300" height="90" rx="14" className="arch-node audit" />
            <text x="140" y="406" className="arch-title">Audit & Lineage</text>
            <text x="140" y="432" className="arch-text">Immutable trace per ticket/output</text>

            <rect x="460" y="370" width="300" height="90" rx="14" className="arch-node dag" />
            <text x="480" y="406" className="arch-title">DAG Orchestrator</text>
            <text x="480" y="432" className="arch-text">Month-end dependency execution</text>

            <rect x="800" y="370" width="280" height="90" rx="14" className="arch-node ui" />
            <text x="820" y="406" className="arch-title">API + Dashboard</text>
            <text x="820" y="432" className="arch-text">Operational views and drill-down</text>

            <line x1="250" y1="85" x2="300" y2="85" className="arch-link" />
            <line x1="500" y1="85" x2="550" y2="85" className="arch-link" />
            <line x1="750" y1="85" x2="800" y2="85" className="arch-link" />
            <line x1="960" y1="130" x2="260" y2="210" className="arch-link" />
            <line x1="960" y1="130" x2="580" y2="210" className="arch-link" />
            <line x1="960" y1="130" x2="900" y2="210" className="arch-link" />
            <line x1="260" y1="300" x2="260" y2="370" className="arch-link" />
            <line x1="580" y1="300" x2="610" y2="370" className="arch-link" />
            <line x1="900" y1="300" x2="940" y2="370" className="arch-link" />
          </svg>
        </section>
      )}

      {activeTab === 'passenger' && (
        <section className="panel tab-panel">
          <h2>Passenger Flows</h2>
          <p className="tab-copy">
            One-day walkthrough on 2026-02-27 for 6 passengers across LHR-SFO, LHR-JFK, and JFK-SFO.
          </p>
          <button className="refresh-btn small" onClick={() => void loadPassengerWalkthroughs()}>
            Refresh Passenger Flows
          </button>
          <div className="events-list passenger-list">
            {passengerWalkthroughs.map((flow) => (
              <article key={flow.passenger_name} className="event-card passenger-card">
                <header>
                  <strong>{flow.passenger_name}</strong>
                  <span>{flow.tickets.join(', ')}</span>
                </header>
                <p className="event-meta">
                  Channels: {flow.sales_channels.join(', ')} | {flow.narrative}
                </p>
                <div className="legs-grid">
                  {flow.itinerary.map((leg) => (
                    <div key={`${leg.ticket_number}-${leg.coupon_number}`} className="leg-card">
                      <strong>
                        {leg.origin} to {leg.destination}
                      </strong>
                      <p>
                        {leg.flight_number} | coupon {leg.coupon_number} | {leg.marketing_carrier}/{leg.operating_carrier}
                      </p>
                      <p>
                        {leg.currency} {leg.gross_amount?.toFixed(2)} | {leg.sales_channel}
                      </p>
                      <p>
                        matching: {leg.match_status} | recon: {leg.recon_status}
                        {leg.recon_break_type ? ` (${leg.recon_break_type})` : ''}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="step-grid">
                  <div className="step-card">
                    <h3>Ingestion</h3>
                    <p>{flow.steps.ingestion.issued_coupons} issued coupons ingested.</p>
                  </div>
                  <div className="step-card">
                    <h3>Matching</h3>
                    <p>
                      {flow.steps.matching.matched} matched, {flow.steps.matching.unmatched_issued} unmatched issued,{' '}
                      {flow.steps.matching.unmatched_flown} unmatched flown.
                    </p>
                  </div>
                  <div className="step-card">
                    <h3>Reconciliation</h3>
                    <p>
                      {flow.steps.reconciliation.matched} matched, {flow.steps.reconciliation.breaks} breaks.
                    </p>
                  </div>
                  <div className="step-card">
                    <h3>Settlement & Audit</h3>
                    <p>
                      {flow.steps.settlement.total} settlement items, {flow.steps.audit.records} audit records.
                    </p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'ticket' && (
        <section className="panel tab-panel">
          <h2>Ticket Explorer</h2>
          <form className="inline-form" onSubmit={onTicketSubmit}>
            <input value={ticketSearch} onChange={(event) => setTicketSearch(event.target.value)} />
            <button type="submit">Search</button>
          </form>
          {ticketDetail && (
            <>
              <pre>{JSON.stringify(ticketDetail.state, null, 2)}</pre>
              <div className="events-list">
                {ticketDetail.history.map((event) => (
                  <div key={event.event_id} className="event-card">
                    <strong>{event.event_type}</strong> at {new Date(event.occurred_at).toLocaleString()}
                  </div>
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {activeTab === 'matching' && (
        <section className="panel tab-panel">
          <h2>Coupon Matching</h2>
          <button className="refresh-btn small" onClick={() => void loadMatching()}>
            Refresh Matching
          </button>
          <pre>{JSON.stringify(matchingSummary, null, 2)}</pre>
          <h3>Suspense Items</h3>
          <pre>{JSON.stringify(suspenseItems.slice(0, 30), null, 2)}</pre>
        </section>
      )}

      {activeTab === 'recon' && (
        <section className="panel tab-panel">
          <h2>Reconciliation</h2>
          <button className="refresh-btn small" onClick={() => void loadRecon()}>
            Refresh Reconciliation
          </button>
          <pre>{JSON.stringify(reconSummary, null, 2)}</pre>
          <div className="events-list">
            {reconBreaks.slice(0, 30).map((item) => (
              <div key={item.id} className="event-card">
                <strong>{item.ticket_number}</strong> | {item.break_type ?? 'none'} | {item.severity}
                <button className="resolve-btn" onClick={() => void resolveBreak(item.id)}>
                  Resolve
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {activeTab === 'audit' && (
        <section className="panel tab-panel">
          <h2>Audit & Lineage</h2>
          <form className="inline-form" onSubmit={onAuditSubmit}>
            <input value={auditTicket} onChange={(event) => setAuditTicket(event.target.value)} />
            <button type="submit">Load Lineage</button>
          </form>
          <pre>{JSON.stringify(auditHistory.slice(0, 80), null, 2)}</pre>
        </section>
      )}

      {activeTab === 'orchestrator' && (
        <section className="panel tab-panel">
          <h2>Orchestrator</h2>
          <div className="events-list">
            {dags.map((dag) => (
              <div key={dag.name} className="event-card">
                <strong>{dag.name}</strong>
                <p>{dag.tasks.map((task) => task.name).join(' -> ')}</p>
                <button onClick={() => void runDag(dag.name)}>Run DAG</button>
              </div>
            ))}
          </div>
          <h3>Last Run</h3>
          <pre>{JSON.stringify(selectedRun, null, 2)}</pre>
        </section>
      )}

      {activeTab === 'settlements' && (
        <section className="panel tab-panel">
          <h2>Settlements</h2>
          <div className="events-list">
            {settlements.slice(0, 40).map((item) => (
              <div key={item.id} className="event-card">
                <strong>{item.ticket_number}</strong> | {item.counterparty} | {item.status}
                <button onClick={() => void loadSettlementSaga(item.id)}>Saga</button>
              </div>
            ))}
          </div>
          <h3>Saga Log</h3>
          <pre>{JSON.stringify(selectedSettlementSaga, null, 2)}</pre>
        </section>
      )}
    </main>
  )
}

export default App
