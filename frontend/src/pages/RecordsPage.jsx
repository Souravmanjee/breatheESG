import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import api from '../utils/api'
import { AlertTriangle, ExternalLink, CheckCircle, XCircle, Flag } from 'lucide-react'

const SCOPE_BADGE = { '1': 'badge-scope1', '2': 'badge-scope2', '3': 'badge-scope3' }
const SOURCE_BADGE = { sap: 'badge-sap', utility: 'badge-utility', travel: 'badge-travel' }
const STATUS_BADGE = {
  pending: 'badge-pending', approved: 'badge-approved', locked: 'badge-locked',
  flagged: 'badge-flagged', rejected: 'badge-rejected',
}

function fmtCO2(val) {
  if (!val) return '—'
  const n = parseFloat(val)
  if (n >= 1000) return (n / 1000).toFixed(2) + ' tCO₂e'
  return n.toFixed(1) + ' kgCO₂e'
}

export default function RecordsPage() {
  const { tenant } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()
  const [records, setRecords] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(new Set())
  const [bulkLoading, setBulkLoading] = useState(false)
  const [msg, setMsg] = useState('')

  const filters = {
    status: searchParams.get('status') || '',
    scope: searchParams.get('scope') || '',
    source_type: searchParams.get('source_type') || '',
    suspicious: searchParams.get('suspicious') || '',
    page: parseInt(searchParams.get('page') || '1'),
  }

  const setFilter = (key, val) => {
    const next = new URLSearchParams(searchParams)
    if (val) next.set(key, val); else next.delete(key)
    next.delete('page')
    setSearchParams(next)
  }

  const fetchRecords = () => {
    if (!tenant) return
    setLoading(true)
    const params = {}
    Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v })
    api.get(`/tenants/${tenant.slug}/records/`, { params })
      .then(r => { setRecords(r.data.results); setCount(r.data.count) })
      .finally(() => setLoading(false))
  }

  useEffect(fetchRecords, [tenant, searchParams])

  const toggleSelect = (id) => {
    setSelected(s => {
      const n = new Set(s)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  const toggleAll = () => {
    if (selected.size === records.length) setSelected(new Set())
    else setSelected(new Set(records.map(r => r.id)))
  }

  const bulkAction = async (action) => {
    if (selected.size === 0) return
    setBulkLoading(true)
    setMsg('')
    try {
      const r = await api.post(`/tenants/${tenant.slug}/bulk-review/`, {
        record_ids: [...selected],
        action,
      })
      setMsg(r.data.message)
      setSelected(new Set())
      fetchRecords()
    } catch (e) {
      setMsg('Action failed: ' + (e.response?.data?.error || e.message))
    } finally {
      setBulkLoading(false)
    }
  }

  const totalPages = Math.ceil(count / 50)

  return (
    <div>
      <div className="page-header">
        <h2>Review Records</h2>
        <p>
          {count} records {filters.status ? `with status "${filters.status}"` : 'total'}.
          Approve rows before they can be locked for audit.
        </p>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <select className="filter-select" value={filters.status} onChange={e => setFilter('status', e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="flagged">Flagged</option>
          <option value="approved">Approved</option>
          <option value="locked">Locked</option>
          <option value="rejected">Rejected</option>
        </select>
        <select className="filter-select" value={filters.scope} onChange={e => setFilter('scope', e.target.value)}>
          <option value="">All scopes</option>
          <option value="1">Scope 1 — Direct</option>
          <option value="2">Scope 2 — Electricity</option>
          <option value="3">Scope 3 — Indirect</option>
        </select>
        <select className="filter-select" value={filters.source_type} onChange={e => setFilter('source_type', e.target.value)}>
          <option value="">All sources</option>
          <option value="sap">SAP</option>
          <option value="utility">Utility</option>
          <option value="travel">Travel</option>
        </select>
        <select className="filter-select" value={filters.suspicious} onChange={e => setFilter('suspicious', e.target.value)}>
          <option value="">All records</option>
          <option value="true">Suspicious only</option>
        </select>
        <button className="btn btn-secondary btn-sm" onClick={() => setSearchParams({})}>Clear filters</button>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 6, marginBottom: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>{selected.size} selected</span>
          <button className="btn btn-primary btn-sm" onClick={() => bulkAction('approve')} disabled={bulkLoading}>
            <CheckCircle size={13} /> Approve all
          </button>
          <button className="btn btn-warn btn-sm" onClick={() => bulkAction('flag')} disabled={bulkLoading}>
            <Flag size={13} /> Flag all
          </button>
          <button className="btn btn-danger btn-sm" onClick={() => bulkAction('reject')} disabled={bulkLoading}>
            <XCircle size={13} /> Reject all
          </button>
        </div>
      )}

      {msg && <div className="alert alert-success">{msg}</div>}

      {/* Table */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading records…</div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{ width: 36 }}>
                    <input type="checkbox" className="checkbox"
                      checked={selected.size === records.length && records.length > 0}
                      onChange={toggleAll}
                    />
                  </th>
                  <th>Description</th>
                  <th>Scope</th>
                  <th>Source</th>
                  <th>Date</th>
                  <th>Activity</th>
                  <th>CO₂e</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {records.length === 0 && (
                  <tr><td colSpan={9} style={{ textAlign: 'center', color: '#94a3b8', padding: 32 }}>No records match these filters.</td></tr>
                )}
                {records.map(r => (
                  <tr key={r.id} style={{ background: r.is_suspicious ? '#fff7ed' : undefined }}>
                    <td>
                      <input type="checkbox" className="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => toggleSelect(r.id)}
                      />
                    </td>
                    <td>
                      <div style={{ fontWeight: 500, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {r.is_suspicious && <AlertTriangle size={12} style={{ color: '#d97706', marginRight: 4, display: 'inline' }} />}
                        {r.activity_description}
                      </div>
                      {r.location_name && <div style={{ fontSize: 11, color: '#94a3b8' }}>{r.location_name}</div>}
                    </td>
                    <td><span className={`badge ${SCOPE_BADGE[r.scope]}`}>Scope {r.scope}</span></td>
                    <td><span className={`badge ${SOURCE_BADGE[r.source_type]}`}>{r.source_type.toUpperCase()}</span></td>
                    <td style={{ whiteSpace: 'nowrap', color: '#64748b', fontSize: 12 }}>{r.activity_date}</td>
                    <td style={{ fontSize: 12, color: '#475569' }}>{r.raw_value} {r.raw_unit}</td>
                    <td style={{ fontWeight: 600 }}>{fmtCO2(r.normalized_value_kg_co2e)}</td>
                    <td><span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status}</span></td>
                    <td>
                      <Link to={`/records/${r.id}`} className="btn btn-ghost btn-sm">
                        <ExternalLink size={12} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="pagination">
          <button className="btn btn-secondary btn-sm" disabled={filters.page <= 1}
            onClick={() => setFilter('page', filters.page - 1)}>← Prev</button>
          <span>Page {filters.page} of {totalPages}</span>
          <button className="btn btn-secondary btn-sm" disabled={filters.page >= totalPages}
            onClick={() => setFilter('page', filters.page + 1)}>Next →</button>
        </div>
      )}
    </div>
  )
}
