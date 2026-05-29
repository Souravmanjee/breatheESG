import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import api from '../utils/api'
import { ArrowLeft, AlertTriangle, Lock } from 'lucide-react'

const STATUS_BADGE = {
  pending: 'badge-pending', approved: 'badge-approved', locked: 'badge-locked',
  flagged: 'badge-flagged', rejected: 'badge-rejected',
}

const ACTIONS = [
  { id: 'approve', label: 'Approve', className: 'btn-primary', allowedFrom: ['pending', 'flagged'] },
  { id: 'flag', label: 'Flag', className: 'btn-warn', allowedFrom: ['pending'] },
  { id: 'unflag', label: 'Clear flag', className: 'btn-secondary', allowedFrom: ['flagged'] },
  { id: 'reject', label: 'Reject', className: 'btn-danger', allowedFrom: ['pending', 'flagged'] },
  { id: 'lock', label: 'Lock for Audit', className: 'btn-secondary', allowedFrom: ['approved'], adminOnly: true },
]

function DetailRow({ label, value }) {
  return (
    <div className="detail-row">
      <span className="dk">{label}</span>
      <span className="dv">{value || '—'}</span>
    </div>
  )
}

export default function RecordDetailPage() {
  const { id } = useParams()
  const { tenant } = useAuth()
  const navigate = useNavigate()
  const [record, setRecord] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notes, setNotes] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')

  // Edit form states
  const [isEditing, setIsEditing] = useState(false)
  const [editForm, setEditForm] = useState({
    raw_value: '',
    raw_unit: '',
    activity_date: '',
    location_code: '',
    location_name: '',
    country_code: '',
    reason_for_edit: ''
  })

  const fetchRecord = () => {
    if (!tenant) return
    setLoading(true)
    api.get(`/tenants/${tenant.slug}/records/${id}/`)
      .then(r => setRecord(r.data))
      .finally(() => setLoading(false))
  }

  useEffect(fetchRecord, [id, tenant])

  const enterEditMode = () => {
    if (!record) return
    setEditForm({
      raw_value: record.raw_value,
      raw_unit: record.raw_unit,
      activity_date: record.activity_date,
      location_code: record.location_code,
      location_name: record.location_name,
      country_code: record.country_code,
      reason_for_edit: ''
    })
    setIsEditing(true)
  }

  const handleEditSubmit = async (e) => {
    e.preventDefault()
    if (!editForm.reason_for_edit.trim()) {
      setError('Please provide a reason for the edit (required for audit log).')
      return
    }
    setActionLoading(true)
    setError('')
    setMsg('')
    try {
      await api.patch(`/tenants/${tenant.slug}/records/${id}/`, editForm)
      setMsg('Record fields updated successfully.')
      setIsEditing(false)
      fetchRecord()
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save changes.')
    } finally {
      setActionLoading(false)
    }
  }

  const takeAction = async (action) => {
    setActionLoading(true)
    setMsg('')
    setError('')
    try {
      await api.post(`/tenants/${tenant.slug}/records/${id}/review/`, { action, notes })
      setMsg(`Record ${action}d successfully.`)
      setNotes('')
      fetchRecord()
    } catch (e) {
      setError(e.response?.data?.error || 'Action failed.')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>Loading…</div>
  if (!record) return <div style={{ padding: 40 }}>Record not found.</div>

  const availableActions = ACTIONS.filter(a => a.allowedFrom.includes(record.status))

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <Link to="/records" className="btn btn-ghost" style={{ paddingLeft: 0 }}>
          <ArrowLeft size={14} /> Back to records
        </Link>
      </div>

      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {record.is_suspicious && <AlertTriangle size={20} color="#d97706" />}
            Emission Record
            {record.status === 'locked' && <Lock size={16} color="#4338ca" />}
          </h2>
          <p>{record.activity_description}</p>
        </div>
        <span className={`badge ${STATUS_BADGE[record.status]}`} style={{ fontSize: 13, padding: '4px 12px' }}>
          {record.status_display}
        </span>
      </div>

      {record.is_suspicious && (
        <div className="alert alert-warn" style={{ marginBottom: 20 }}>
          <AlertTriangle size={14} style={{ display: 'inline', marginRight: 6 }} />
          <strong>Flagged as suspicious during ingestion:</strong> {record.suspicion_reason}
        </div>
      )}

      {msg && <div className="alert alert-success">{msg}</div>}
      {error && <div className="alert alert-error">{error}</div>}

      <div className="detail-grid">
        <div>
          {isEditing ? (
            <form onSubmit={handleEditSubmit} className="card" style={{ marginBottom: 16, padding: '20px' }}>
              <h3 style={{ marginBottom: '16px', color: '#1e293b' }}>Edit Emission Record</h3>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Raw Value / Quantity (Required)</label>
                <input
                  type="number"
                  step="any"
                  className="form-input"
                  value={editForm.raw_value}
                  onChange={e => setEditForm({ ...editForm, raw_value: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Raw Unit (Required)</label>
                <input
                  type="text"
                  className="form-input"
                  value={editForm.raw_unit}
                  onChange={e => setEditForm({ ...editForm, raw_unit: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Activity Date (Required)</label>
                <input
                  type="date"
                  className="form-input"
                  value={editForm.activity_date}
                  onChange={e => setEditForm({ ...editForm, activity_date: e.target.value })}
                  required
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Location Code</label>
                <input
                  type="text"
                  className="form-input"
                  value={editForm.location_code || ''}
                  onChange={e => setEditForm({ ...editForm, location_code: e.target.value })}
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Location Name</label>
                <input
                  type="text"
                  className="form-input"
                  value={editForm.location_name || ''}
                  onChange={e => setEditForm({ ...editForm, location_name: e.target.value })}
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                />
              </div>

              <div className="form-group" style={{ marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Country Code (2 letters, e.g. IN, DE, GB, US)</label>
                <input
                  type="text"
                  maxLength="2"
                  className="form-input"
                  value={editForm.country_code || ''}
                  onChange={e => setEditForm({ ...editForm, country_code: e.target.value.toUpperCase() })}
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                />
              </div>

              {record.category === 'travel_flight' && editForm.source_metadata?.cabin_class && (
                <div className="form-group" style={{ marginBottom: '12px' }}>
                  <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Flight Cabin Class</label>
                  <select
                    className="form-input"
                    value={editForm.source_metadata?.cabin_class || 'economy'}
                    onChange={e => setEditForm({
                      ...editForm,
                      source_metadata: {
                        ...editForm.source_metadata,
                        cabin_class: e.target.value
                      }
                    })}
                    style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px' }}
                  >
                    <option value="economy">Economy</option>
                    <option value="premium economy">Premium Economy</option>
                    <option value="business">Business Class</option>
                    <option value="first">First Class</option>
                  </select>
                </div>
              )}

              <div className="form-group" style={{ marginTop: '20px', marginBottom: '12px' }}>
                <label className="form-label" style={{ fontWeight: 600, display: 'block', marginBottom: '6px' }}>Reason for Edit (Required for Audit Trail) <span style={{ color: '#ef4444' }}>*</span></label>
                <textarea
                  className="form-textarea"
                  value={editForm.reason_for_edit}
                  onChange={e => setEditForm({ ...editForm, reason_for_edit: e.target.value })}
                  placeholder="Explain why this change is being made (e.g. corrected quantity from invoice)..."
                  required
                  style={{ width: '100%', padding: '8px', border: '1px solid #cbd5e1', borderRadius: '4px', minHeight: '80px' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                <button type="submit" className="btn btn-primary" disabled={actionLoading} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                  {actionLoading ? 'Saving…' : 'Save Changes'}
                </button>
                <button type="button" className="btn btn-secondary" onClick={() => setIsEditing(false)} disabled={actionLoading} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                  Cancel
                </button>
              </div>
            </form>
          ) : (
            <div className="card" style={{ marginBottom: 16 }}>
              <div className="detail-section">
                <h4>Classification</h4>
                <DetailRow label="Scope" value={record.scope_display} />
                <DetailRow label="Category" value={record.category_display} />
                <DetailRow label="Source type" value={record.source_type?.toUpperCase()} />
                <DetailRow label="Activity date" value={record.activity_date} />
                <DetailRow label="Reporting period" value={`${record.reporting_period_start} → ${record.reporting_period_end}`} />
              </div>

              <div className="detail-section">
                <h4>Activity Data (Raw)</h4>
                <DetailRow label="Raw value" value={`${record.raw_value} ${record.raw_unit}`} />
                <DetailRow label="Normalized value" value={`${record.normalized_value} ${record.normalized_unit}`} />
                <DetailRow label="Unit conversion factor" value={record.unit_conversion_factor} />
              </div>

              <div className="detail-section">
                <h4>Emission Calculation</h4>
                <DetailRow label="Emission factor used" value={record.emission_factor_value_used ? `${record.emission_factor_value_used} kgCO₂e / ${record.normalized_unit}` : '—'} />
                <DetailRow label="CO₂e result" value={record.normalized_value_kg_co2e ? `${parseFloat(record.normalized_value_kg_co2e).toFixed(2)} kgCO₂e` : '—'} />
              </div>

              <div className="detail-section">
                <h4>Location</h4>
                <DetailRow label="Location code" value={record.location_code} />
                <DetailRow label="Location name" value={record.location_name} />
                <DetailRow label="Country" value={record.country_code} />
              </div>

              {/* Source-specific metadata */}
              <div className="detail-section">
                <h4>Source Metadata</h4>
                {Object.entries(record.source_metadata || {}).map(([k, v]) => (
                  <DetailRow key={k} label={k.replace(/_/g, ' ')} value={String(v)} />
                ))}
              </div>

              {/* Provenance */}
              <div className="detail-section">
                <h4>Provenance</h4>
                <DetailRow label="Ingestion run ID" value={record.ingestion_run_id} />
                <DetailRow label="Created at" value={record.created_at} />
              </div>
            </div>
          )}

          {/* Raw source row */}
          {record.source_row && (
            <div className="card" style={{ marginBottom: 16 }}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>
                Raw source data (row {record.source_row.row_index})
              </div>
              <pre className="raw-viewer">
                {JSON.stringify(record.source_row.raw_data, null, 2)}
              </pre>
            </div>
          )}

          {/* Edit history */}
          {record.edits?.length > 0 && (
            <div className="card">
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 12 }}>Audit trail</div>
              {record.edits.map((e, i) => (
                <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid #e2e8f0', fontSize: 12, color: '#475569' }}>
                  <span style={{ fontWeight: 600 }}>{e.edited_by}</span> changed <strong>{e.field_name}</strong>
                  {' '}from <code style={{ background: '#f1f5f9', padding: '1px 4px', borderRadius: 3 }}>{e.old_value}</code>
                  {' '}to <code style={{ background: '#f1f5f9', padding: '1px 4px', borderRadius: 3 }}>{e.new_value}</code>
                  <span style={{ color: '#94a3b8', marginLeft: 8 }}>{new Date(e.edited_at).toLocaleString()}</span>
                  {e.reason && <div style={{ color: '#94a3b8', marginTop: 2 }}>Reason: {e.reason}</div>}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right panel: actions */}
        <div>
          <div className="card" style={{ position: 'sticky', top: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 16 }}>Review Actions</div>

            {isEditing ? (
              <div style={{ color: '#d97706', fontSize: 13, padding: '12px', background: '#fffbeb', borderRadius: '6px', border: '1px solid #fef3c7' }}>
                Currently editing record fields. Please complete or cancel editing in the form on the left.
              </div>
            ) : record.status === 'locked' ? (
              <div style={{ color: '#4338ca', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Lock size={14} /> Locked for audit. No further changes allowed.
              </div>
            ) : (
              <>
                {record.status !== 'approved' && (
                  <button
                    className="btn btn-secondary"
                    onClick={enterEditMode}
                    disabled={actionLoading}
                    style={{ width: '100%', justifyContent: 'center', marginBottom: 16, border: '1px solid #cbd5e1', fontWeight: 600, display: 'inline-flex', alignItems: 'center' }}
                  >
                    Edit Record Fields
                  </button>
                )}
                <div className="form-group">
                  <label className="form-label">Notes (optional)</label>
                  <textarea
                    className="form-textarea"
                    value={notes}
                    onChange={e => setNotes(e.target.value)}
                    placeholder="Add a reason or comment…"
                    style={{ minHeight: 60 }}
                  />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {availableActions.map(action => (
                    <button
                      key={action.id}
                      className={`btn ${action.className}`}
                      onClick={() => takeAction(action.id)}
                      disabled={actionLoading}
                      style={{ justifyContent: 'center' }}
                    >
                      {actionLoading ? '…' : action.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {record.reviewed_by && (
              <div style={{ marginTop: 20, padding: '12px', background: '#f8fafc', borderRadius: 6, fontSize: 12, color: '#64748b' }}>
                Last reviewed by <strong>{record.reviewed_by}</strong> at{' '}
                {record.reviewed_at ? new Date(record.reviewed_at).toLocaleString() : '—'}
                {record.review_notes && <div style={{ marginTop: 4 }}>"{record.review_notes}"</div>}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
