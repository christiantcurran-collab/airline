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

type TabKey =
  | 'overview'
  | 'ticket'
  | 'matching'
  | 'recon'
  | 'audit'
  | 'orchestrator'
  | 'settlements'

const tabs: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
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

  const [ticketSearch, setTicketSearch] = useState('125000000001')
  const [ticketDetail, setTicketDetail] = useState<TicketDetail | null>(null)

  const [matchingSummary, setMatchingSummary] = useState<MatchingSummary | null>(null)
  const [suspenseItems, setSuspenseItems] = useState<Record<string, unknown>[]>([])

  const [reconSummary, setReconSummary] = useState<ReconSummary | null>(null)
  const [reconBreaks, setReconBreaks] = useState<ReconBreak[]>([])

  const [auditTicket, setAuditTicket] = useState('125000000001')
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

  async function loadOverview() {
    setLoading(true)
    setError(null)
    try {
      const payload = await fetchJson<DashboardPayload>('/api/dashboard')
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

  useEffect(() => {
    void loadOverview()
  }, [])

  useEffect(() => {
    if (activeTab === 'ticket') {
      void loadTicket(ticketSearch)
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
        <button className="refresh-btn" onClick={() => void loadOverview()} disabled={loading}>
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
