import { useEffect, useMemo, useState } from 'react'
import './App.css'

type CanonicalEvent = {
  event_id: string
  occurred_at: string
  source_system: string
  event_type: string
  ticket_number: string
  coupon_number: number | null
  pnr: string | null
  flight_number: string | null
  origin: string | null
  destination: string | null
  currency: string | null
  gross_amount: string | null
  net_amount: string | null
}

type TopicData = {
  count: number
  events: CanonicalEvent[]
}

type DashboardPayload = {
  generated_at: string
  bus_backend: string
  total_channels: number
  total_topics: number
  total_events: number
  channels: SourceChannel[]
  topics: Record<string, TopicData>
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

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '')
const dashboardEndpoint = `${apiBaseUrl}/api/dashboard`

function App() {
  const [data, setData] = useState<DashboardPayload | null>(null)
  const [selectedTopic, setSelectedTopic] = useState<string>('')
  const [selectedChannelId, setSelectedChannelId] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const topicEntries = useMemo(() => {
    if (!data) {
      return []
    }
    return Object.entries(data.topics).sort((a, b) => b[1].count - a[1].count)
  }, [data])

  const selectedEvents = useMemo(() => {
    if (!data || !selectedTopic) {
      return []
    }
    return data.topics[selectedTopic]?.events ?? []
  }, [data, selectedTopic])

  const selectedChannel = useMemo(() => {
    if (!data || !selectedChannelId) {
      return null
    }
    return data.channels.find((channel) => channel.channel_id === selectedChannelId) ?? null
  }, [data, selectedChannelId])

  async function loadDashboard() {
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(dashboardEndpoint)
      if (!response.ok) {
        throw new Error(`Request failed with ${response.status}`)
      }
      const payload = (await response.json()) as DashboardPayload
      setData(payload)
      if (!selectedTopic) {
        const firstTopic = Object.keys(payload.topics)[0]
        setSelectedTopic(firstTopic ?? '')
      }
      if (!selectedChannelId) {
        setSelectedChannelId(payload.channels[0]?.channel_id ?? '')
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadDashboard()
  }, [])

  return (
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">FlightLedger Control</p>
        <h1>Airline Revenue Event Console</h1>
        <p className="hero-copy">
          Live view of normalized ticket, coupon, and settlement events from all source adapters.
        </p>
        <button className="refresh-btn" onClick={() => void loadDashboard()} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh Feed'}
        </button>
      </section>

      {error && (
        <section className="panel error-panel">
          <h2>Connection Error</h2>
          <p>Could not load dashboard data: {error}</p>
          <p>Expected API endpoint: {dashboardEndpoint}</p>
        </section>
      )}

      {data && !error && (
        <section className="dashboard-grid">
          <article className="panel stats-panel">
            <h2>Run Snapshot</h2>
            <div className="stat-list">
              <div>
                <span>Topics</span>
                <strong>{data.total_topics}</strong>
              </div>
              <div>
                <span>Events</span>
                <strong>{data.total_events}</strong>
              </div>
              <div>
                <span>Bus Backend</span>
                <strong>{data.bus_backend}</strong>
              </div>
              <div>
                <span>Channels</span>
                <strong>{data.total_channels}</strong>
              </div>
              <div>
                <span>Generated UTC</span>
                <strong>{new Date(data.generated_at).toLocaleString()}</strong>
              </div>
            </div>
          </article>

          <article className="panel channels-panel">
            <h2>Source Channels (Raw Native Format)</h2>
            <div className="channels-layout">
              <div className="channel-list">
                {data.channels.map((channel) => (
                  <button
                    key={channel.channel_id}
                    className={`channel-row ${channel.channel_id === selectedChannelId ? 'active' : ''}`}
                    onClick={() => setSelectedChannelId(channel.channel_id)}
                  >
                    <span>{channel.name}</span>
                    <small>
                      {channel.protocol} | {channel.format} | {channel.record_count} records
                    </small>
                  </button>
                ))}
              </div>
              <div className="channel-detail">
                {selectedChannel && (
                  <>
                    <p className="channel-meta">
                      {selectedChannel.name} | {selectedChannel.protocol} | {selectedChannel.format} | file{' '}
                      {selectedChannel.file_name}
                    </p>
                    <pre>{selectedChannel.raw_payload}</pre>
                  </>
                )}
              </div>
            </div>
          </article>

          <article className="panel topics-panel">
            <h2>Topic Throughput</h2>
            <div className="topics-list">
              {topicEntries.map(([topic, topicData]) => (
                <button
                  key={topic}
                  className={`topic-row ${topic === selectedTopic ? 'active' : ''}`}
                  onClick={() => setSelectedTopic(topic)}
                >
                  <span>{topic}</span>
                  <strong>{topicData.count}</strong>
                </button>
              ))}
            </div>
          </article>

          <article className="panel events-panel">
            <h2>{selectedTopic || 'Events'}</h2>
            <div className="events-list">
              {selectedEvents.map((event) => (
                <div className="event-card" key={event.event_id}>
                  <header>
                    <span className="event-type">{event.event_type}</span>
                    <time>{new Date(event.occurred_at).toLocaleString()}</time>
                  </header>
                  <p className="event-route">
                    {event.origin ?? '---'} to {event.destination ?? '---'} | flight {event.flight_number ?? 'n/a'}
                  </p>
                  <p className="event-meta">
                    Ticket {event.ticket_number} | Source {event.source_system}
                  </p>
                </div>
              ))}
              {selectedEvents.length === 0 && <p>No events in this topic.</p>}
            </div>
          </article>
        </section>
      )}
      <div className="background-orb one" />
      <div className="background-orb two" />
      <div className="background-grid" />
    </main>
  )
}

export default App
