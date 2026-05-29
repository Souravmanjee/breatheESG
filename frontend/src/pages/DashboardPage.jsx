import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import api from '../utils/api'
import { AlertTriangle, CheckCircle, Lock, Clock, XCircle, Flag } from 'lucide-react'

const fmt = (n) => n ? (n / 1000).toFixed(1) + ' tCO₂e' : '—'
const fmtKg = (n) => n ? Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 }) + ' kg' : '—'

export default function DashboardPage() {
  const { tenant } = useAuth()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [runs, setRuns] = useState([])

  useEffect(() => {
    if (!tenant) return
    Promise.all([
      api.get(`/tenants/${tenant.slug}/stats/`),
      api.get(`/tenants/${tenant.slug}/ingestion-runs/`),
    ]).then(([s, r]) => {
      setStats(s.data)
      setRuns(r.data.slice(0, 5))
    }).finally(() => setLoading(false))
  }, [tenant])

  if (loading) return <div className="loading-screen">Loading dashboard…</div>
  if (!stats) return null

  const totalApproved =
    (stats.scope_totals_kg_co2e.scope_1 || 0) +
    (stats.scope_totals_kg_co2e.scope_2 || 0) +
    (stats.scope_totals_kg_co2e.scope_3 || 0)

  const scopeMax = Math.max(
    stats.scope_totals_kg_co2e.scope_1,
    stats.scope_totals_kg_co2e.scope_2,
    stats.scope_totals_kg_co2e.scope_3,
    1
  )

  return (
    <div>
      <div className="page-header">
        <h2>{tenant?.name} — Emissions Dashboard</h2>
        <p>Q1 2024 · Scope 1, 2 & 3 · Approved + locked records only</p>
      </div>

      {/* Status cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="label">Total Records</div>
          <div className="value">{stats.total_records}</div>
          <div className="sub">across all sources</div>
        </div>
        <div className="stat-card" style={{ borderLeft: '3px solid #d97706' }}>
          <div className="label">Pending Review</div>
          <div className="value" style={{ color: '#d97706' }}>{stats.status_counts.pending}</div>
          <div className="sub">{stats.suspicious_pending} flagged suspicious</div>
        </div>
        <div className="stat-card" style={{ borderLeft: '3px solid #16a34a' }}>
          <div className="label">Approved</div>
          <div className="value" style={{ color: '#16a34a' }}>{stats.status_counts.approved}</div>
          <div className="sub">{stats.status_counts.locked} locked for audit</div>
        </div>
        <div className="stat-card" style={{ borderLeft: '3px solid #2563eb' }}>
          <div className="label">Total CO₂e (approved)</div>
          <div className="value" style={{ fontSize: 20 }}>{fmt(totalApproved)}</div>
          <div className="sub">all scopes combined</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>
        {/* Scope breakdown */}
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: 18, fontSize: 14 }}>Emissions by Scope</div>
          <div className="scope-bars">
            {[
              { label: 'Scope 1', key: 'scope_1', color: '#d97706', desc: 'Direct (fuel)' },
              { label: 'Scope 2', key: 'scope_2', color: '#2563eb', desc: 'Electricity' },
              { label: 'Scope 3', key: 'scope_3', color: '#9333ea', desc: 'Travel / indirect' },
            ].map(({ label, key, color, desc }) => {
              const val = stats.scope_totals_kg_co2e[key] || 0
              const pct = scopeMax > 0 ? (val / scopeMax) * 100 : 0
              return (
                <div key={key}>
                  <div className="scope-bar-row">
                    <div className="scope-bar-label">{label}</div>
                    <div className="scope-bar-track">
                      <div className="scope-bar-fill" style={{ width: `${pct}%`, background: color }} />
                    </div>
                    <div className="scope-bar-value">{fmt(val)}</div>
                  </div>
                  <div style={{ fontSize: 11, color: '#94a3b8', marginLeft: 82, marginTop: 2 }}>{desc}</div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Source breakdown */}
        <div className="card">
          <div style={{ fontWeight: 700, marginBottom: 18, fontSize: 14 }}>Emissions by Source</div>
          {[
            { label: 'SAP (Fuel)', key: 'sap', color: '#c2410c' },
            { label: 'Utility (Electricity)', key: 'utility', color: '#065f46' },
            { label: 'Travel', key: 'travel', color: '#0c4a6e' },
          ].map(({ label, key, color }) => {
            const val = stats.source_totals_kg_co2e[key] || 0
            return (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: 13, color: '#475569' }}>{label}</span>
                <span style={{ fontWeight: 700, color, fontSize: 14 }}>{fmt(val)}</span>
              </div>
            )
          })}
          <div style={{ marginTop: 12, padding: '10px 12px', background: '#f8fafc', borderRadius: 6, fontSize: 12, color: '#64748b' }}>
            Note: only approved + locked records contribute to these totals.
            {stats.status_counts.pending > 0 && ` ${stats.status_counts.pending} records still pending.`}
          </div>
        </div>
      </div>

      {/* Review queue */}
      {stats.suspicious_pending > 0 && (
        <div className="alert alert-warn" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <AlertTriangle size={16} />
          <strong>{stats.suspicious_pending} records flagged as suspicious</strong> — unusually high values detected during ingestion.
          <Link to="/records?suspicious=true" className="btn btn-sm" style={{ marginLeft: 'auto', background: '#d97706', color: '#fff' }}>
            Review now
          </Link>
        </div>
      )}

      {/* Recent ingestion runs */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>Recent Ingestion Runs</div>
          <Link to="/upload" className="btn btn-secondary btn-sm">+ Upload new file</Link>
        </div>
        {runs.length === 0 ? (
          <div style={{ color: '#94a3b8', textAlign: 'center', padding: 24 }}>No uploads yet.</div>
        ) : (
          <div className="run-list">
            {runs.map(run => (
              <div key={run.id} className="run-item">
                <div>
                  <div style={{ fontWeight: 600 }}>{run.original_filename}</div>
                  <div className="run-meta">
                    {run.source_type.toUpperCase()} · {run.uploaded_by} · {new Date(run.uploaded_at).toLocaleDateString()}
                    {run.notes && ` · ${run.notes}`}
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 12, color: '#64748b' }}>
                    {run.row_count_parsed} ok / {run.row_count_failed} failed
                  </span>
                  <span className={`badge badge-${run.status === 'normalized' ? 'approved' : run.status}`}>
                    {run.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
