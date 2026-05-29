import { useState, useRef } from 'react'
import { useAuth } from '../hooks/useAuth'
import api from '../utils/api'
import { Upload, FileText, Zap, Plane } from 'lucide-react'

const SOURCE_TYPES = [
  {
    id: 'sap',
    label: 'SAP Fuel & Procurement',
    icon: <FileText size={24} />,
    color: '#c2410c',
    bg: '#fff7ed',
    desc: 'ME2M flat file export (tab or semicolon separated). Handles German headers, plant codes, mixed units (L, M3, KG, GAL).',
    accept: '.txt,.csv,.tsv',
    sampleFile: 'ME2M_fuel_export.txt',
  },
  {
    id: 'utility',
    label: 'Utility Electricity',
    icon: <Zap size={24} />,
    color: '#065f46',
    bg: '#ecfdf5',
    desc: 'Portal CSV export (Green Button format or billing summary). Monthly or interval data. Multiple meters supported.',
    accept: '.csv',
    sampleFile: 'electricity_greenbutton.csv',
  },
  {
    id: 'travel',
    label: 'Corporate Travel',
    icon: <Plane size={24} />,
    color: '#0c4a6e',
    bg: '#f0f9ff',
    desc: 'Concur or Navan expense export CSV. Flights (IATA codes), hotels (nights), ground transport.',
    accept: '.csv',
    sampleFile: 'concur_travel_export.csv',
  },
]

export default function UploadPage() {
  const { tenant } = useAuth()
  const [selectedSource, setSelectedSource] = useState('sap')
  const [file, setFile] = useState(null)
  const [notes, setNotes] = useState('')
  const [countryCode, setCountryCode] = useState('IN')
  const [drag, setDrag] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const fileRef = useRef()

  const source = SOURCE_TYPES.find(s => s.id === selectedSource)

  const handleDrop = (e) => {
    e.preventDefault()
    setDrag(false)
    const f = e.dataTransfer.files[0]
    if (f) setFile(f)
  }

  const handleUpload = async () => {
    if (!file) { setError('Please select a file first.'); return }
    setError('')
    setResult(null)
    setUploading(true)

    const fd = new FormData()
    fd.append('file', file)
    fd.append('source_type', selectedSource)
    fd.append('notes', notes)
    if (selectedSource === 'utility') fd.append('country_code', countryCode)

    try {
      const r = await api.post(`/tenants/${tenant.slug}/upload/`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setResult(r.data)
      setFile(null)
    } catch (err) {
      setError(err.response?.data?.error || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <h2>Upload Data</h2>
        <p>Ingest data from SAP, utility portals, or travel platforms. Each file is parsed, normalized, and queued for review.</p>
      </div>

      {/* Source type selector */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 24 }}>
        {SOURCE_TYPES.map(s => (
          <div
            key={s.id}
            onClick={() => { setSelectedSource(s.id); setResult(null); setError('') }}
            style={{
              padding: '16px 18px', borderRadius: 8, cursor: 'pointer',
              border: `2px solid ${selectedSource === s.id ? s.color : '#e2e8f0'}`,
              background: selectedSource === s.id ? s.bg : '#fff',
              transition: 'all .15s',
            }}
          >
            <div style={{ color: s.color, marginBottom: 8 }}>{s.icon}</div>
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{s.label}</div>
            <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.5 }}>{s.desc}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 20 }}>
        <div>
          {/* Upload zone */}
          <div
            className={`upload-zone${drag ? ' drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={handleDrop}
            onClick={() => fileRef.current.click()}
          >
            <div className="icon"><Upload size={36} /></div>
            {file ? (
              <>
                <h3 style={{ color: '#16a34a' }}>{file.name}</h3>
                <p>{(file.size / 1024).toFixed(1)} KB · Click to change</p>
              </>
            ) : (
              <>
                <h3>Drop your {source.label} file here</h3>
                <p>or click to browse · Accepts {source.accept}</p>
              </>
            )}
            <input
              ref={fileRef}
              type="file"
              accept={source.accept}
              style={{ display: 'none' }}
              onChange={e => setFile(e.target.files[0])}
            />
          </div>

          {/* Extra fields */}
          {selectedSource === 'utility' && (
            <div className="form-group" style={{ marginTop: 16 }}>
              <label className="form-label">Country (for emission factor)</label>
              <select className="form-select" value={countryCode} onChange={e => setCountryCode(e.target.value)}>
                <option value="IN">India (0.713 kgCO₂e/kWh — CEA 2022)</option>
                <option value="GB">United Kingdom (0.207 kgCO₂e/kWh — DEFRA 2023)</option>
                <option value="DE">Germany (0.364 kgCO₂e/kWh — UBA 2023)</option>
                <option value="US">United States (0.386 kgCO₂e/kWh — EPA eGrid 2022)</option>
                <option value="AU">Australia (0.510 kgCO₂e/kWh — DCCEEW 2023)</option>
                <option value="DEFAULT">Unknown / Global average (0.450 kgCO₂e/kWh)</option>
              </select>
            </div>
          )}

          <div className="form-group" style={{ marginTop: 16 }}>
            <label className="form-label">Notes (optional)</label>
            <textarea
              className="form-textarea"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="e.g. Q1 2024 fuel data, Plant DE01 — exported from ME2M on 2024-04-02"
            />
          </div>

          {error && <div className="alert alert-error">{error}</div>}
          {result && (
            <div className="alert alert-success">
              <strong>Ingestion complete.</strong> {result.message}
              <div style={{ marginTop: 8, fontSize: 12 }}>
                Total rows: {result.total_rows} · Parsed: {result.parsed_rows} · Skipped: {result.failed_rows}
              </div>
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={uploading || !file}
            style={{ marginTop: 4 }}
          >
            {uploading ? 'Uploading…' : `Upload ${source.label} file`}
          </button>
        </div>

        {/* Side panel: format guide */}
        <div>
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 14, color: source.color }}>
              Expected format: {source.label}
            </div>
            {selectedSource === 'sap' && (
              <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.7 }}>
                <p><strong>Format:</strong> SAP ME2M flat file (tab or semicolon separated)</p>
                <p style={{ marginTop: 8 }}><strong>Required columns (English or German):</strong></p>
                <ul style={{ marginLeft: 14, marginTop: 4 }}>
                  <li>Werk / Plant</li>
                  <li>Bestelldatum / Posting Date</li>
                  <li>Menge / Quantity</li>
                  <li>Meins / UoM</li>
                  <li>Kurztext / Short Text (material description)</li>
                </ul>
                <p style={{ marginTop: 8 }}><strong>Units handled:</strong> L, LT, KG, M3, GAL, G, T</p>
                <p style={{ marginTop: 8 }}><strong>Date formats:</strong> YYYYMMDD, DD.MM.YYYY, YYYY-MM-DD</p>
                <p style={{ marginTop: 8 }}><strong>Non-fuel rows</strong> (no fuel keyword in description) will be skipped.</p>
              </div>
            )}
            {selectedSource === 'utility' && (
              <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.7 }}>
                <p><strong>Format:</strong> Green Button CSV or portal billing summary</p>
                <p style={{ marginTop: 8 }}><strong>Billing summary columns:</strong></p>
                <ul style={{ marginLeft: 14, marginTop: 4 }}>
                  <li>Billing Period / Period Start / End</li>
                  <li>Meter ID / Service Point ID</li>
                  <li>Usage (kWh) or Consumption (kWh)</li>
                  <li>Site / Location (optional)</li>
                </ul>
                <p style={{ marginTop: 8 }}><strong>Interval data:</strong> TYPE, DATE, USAGE, UNITS columns (Green Button standard) — aggregated to monthly.</p>
                <p style={{ marginTop: 8 }}><strong>Units:</strong> kWh, Wh, MWh</p>
              </div>
            )}
            {selectedSource === 'travel' && (
              <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.7 }}>
                <p><strong>Format:</strong> Concur or Navan expense export CSV</p>
                <p style={{ marginTop: 8 }}><strong>Required columns:</strong></p>
                <ul style={{ marginLeft: 14, marginTop: 4 }}>
                  <li>Expense Type / Booking Type</li>
                  <li>Transaction Date / Departure Date</li>
                  <li>Origin + Destination (IATA codes for flights)</li>
                  <li>Nights (for hotels)</li>
                  <li>Cabin Class / Class of Service</li>
                </ul>
                <p style={{ marginTop: 8 }}><strong>Flight distance:</strong> computed from IATA codes via great-circle if not provided.</p>
                <p style={{ marginTop: 8 }}><strong>Emission factors:</strong> DEFRA 2023 by cabin class.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
