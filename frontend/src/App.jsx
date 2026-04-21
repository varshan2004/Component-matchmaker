import { useState, useRef } from 'react'

// ─── API ─────────────────────────────────────────────────────────────────────

async function fetchComponent(name) {
  const res  = await fetch(`/component?name=${encodeURIComponent(name)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Unexpected error')
  return data
}

async function fetchAlternatives(name) {
  const res  = await fetch(`/alternatives?name=${encodeURIComponent(name)}`)
  const data = await res.json()
  if (!res.ok) return []
  return data.alternatives || []
}

// ─── ICONS ───────────────────────────────────────────────────────────────────

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
)
const ChipIcon = () => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="7" y="7" width="10" height="10" rx="1"/>
    <path d="M9 7V4M12 7V4M15 7V4M9 17v3M12 17v3M15 17v3M7 9H4M7 12H4M7 15H4M17 9h3M17 12h3M17 15h3"/>
  </svg>
)
const LinkIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
  </svg>
)
const AltIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 014-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 01-4 4H3"/>
  </svg>
)

// ─── CONSTANTS ────────────────────────────────────────────────────────────────

const SUGGESTIONS = ['LM7805', 'NE555', 'BC547', 'IRF540N', 'LM741', '1N4007']

const SPEC_META = {
  type:    { label: 'Type',    color: '#534AB7', bg: '#EEEDFE' },
  voltage: { label: 'Voltage', color: '#185FA5', bg: '#E6F1FB' },
  current: { label: 'Current', color: '#0F6E56', bg: '#EAF3DE' },
}

// ─── SUB-COMPONENTS ───────────────────────────────────────────────────────────

function SpecsGrid({ specs }) {
  const hasAny = specs && Object.values(specs).some(v => v)
  if (!hasAny) return (
    <p style={s.noSpecs}>Detailed specifications unavailable. Showing best available data.</p>
  )
  return (
    <div style={s.specsGrid}>
      {Object.entries(SPEC_META).map(([key, meta]) => (
        <div key={key} style={{ ...s.specCard, background: meta.bg }}>
          <div style={{ ...s.specLabel, color: meta.color }}>{meta.label}</div>
          <div style={{ ...s.specValue, color: meta.color }}>
            {specs[key] || <span style={s.specNA}>—</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

function AlternativeCard({ alt }) {
  return (
    <div style={s.altCard}>
      <div style={s.altName}>{alt.name}</div>
      <div style={s.altBadges}>
        {alt.type    && <span style={{ ...s.altBadge, ...s.badgeType    }}>{alt.type}</span>}
        {alt.voltage && <span style={{ ...s.altBadge, ...s.badgeVoltage }}>{alt.voltage}</span>}
        {alt.current && <span style={{ ...s.altBadge, ...s.badgeCurrent }}>{alt.current}</span>}
      </div>
      <div style={s.altReason}>{alt.reason}</div>
    </div>
  )
}

function AlternativesSection({ name, alts, loading }) {
  if (loading) return (
    <section style={s.card}>
      <SectionLabel icon={<AltIcon />} text="Alternatives" />
      <div style={s.altLoading}>Finding alternatives…</div>
    </section>
  )
  if (!alts || alts.length === 0) return (
    <section style={s.card}>
      <SectionLabel icon={<AltIcon />} text="Alternatives" />
      <p style={s.noSpecs}>No alternatives found in dataset for this component type.</p>
    </section>
  )
  return (
    <section style={s.card}>
      <SectionLabel icon={<AltIcon />} text={`Alternatives for ${name}`} />
      <div style={s.altGrid}>
        {alts.map(a => <AlternativeCard key={a.name} alt={a} />)}
      </div>
    </section>
  )
}

function SectionLabel({ icon, text }) {
  return (
    <div style={s.sectionLabelRow}>
      <span style={s.sectionIcon}>{icon}</span>
      <span style={s.sectionLabelText}>{text}</span>
    </div>
  )
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

export default function App() {
  const [query,     setQuery]     = useState('')
  const [result,    setResult]    = useState(null)
  const [alts,      setAlts]      = useState(null)
  const [status,    setStatus]    = useState('idle')
  const [altStatus, setAltStatus] = useState('idle')   // idle | loading | done
  const [error,     setError]     = useState('')

  async function handleSearch(overrideName) {
    const name = (overrideName ?? query).trim()
    if (!name) return

    setStatus('loading')
    setResult(null)
    setAlts(null)
    setAltStatus('idle')
    setError('')

    try {
      // Fetch component
      const data = await fetchComponent(name)
      setResult(data)
      setStatus('success')

      // Fetch alternatives in parallel
      setAltStatus('loading')
      const altData = await fetchAlternatives(data.name)
      setAlts(altData)
      setAltStatus('done')

    } catch (err) {
      setError(err.message)
      setStatus('error')
    }
  }

  function handleSuggestion(s) {
    setQuery(s)
    handleSearch(s)
  }

  return (
    <div style={s.page}>

      {/* Header */}
      <header style={s.header}>
        <div style={s.headerInner}>
          <div style={s.logo}>
            <span style={s.logoIcon}><ChipIcon /></span>
            <div>
              <div style={s.logoTitle}>Smart Component System</div>
              <div style={s.logoSub}>Phase 3 · Specs + Alternatives</div>
            </div>
          </div>
          <span style={s.badge}>v3.0</span>
        </div>
      </header>

      <main style={s.main}>

        {/* Search */}
        <section style={s.card}>
          <label style={s.label}>Component Name</label>
          <div style={s.searchRow}>
            <input
              style={s.input}
              type="text"
              placeholder="e.g. LM7805, NE555, BC547, IRF540N…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              disabled={status === 'loading'}
              autoFocus
            />
            <button
              style={{ ...s.btn, ...(status === 'loading' ? s.btnDisabled : {}) }}
              onClick={() => handleSearch()}
              disabled={status === 'loading'}
            >
              {status === 'loading'
                ? <span style={s.spinner} />
                : <><SearchIcon /><span>Search</span></>}
            </button>
          </div>
          <div style={s.pills}>
            {SUGGESTIONS.map(sg => (
              <button key={sg} style={s.pill} onClick={() => handleSuggestion(sg)} disabled={status === 'loading'}>
                {sg}
              </button>
            ))}
          </div>
        </section>

        {/* Result */}
        {status === 'success' && result && (<>
          <section style={s.card}>
            <div style={s.resultHeader}>
              <div style={s.resultDot} />
              <span style={s.resultTag}>Result</span>
              {result.source === 'cache'   && <span style={{ ...s.sourceBadge, background: '#FAEEDA', color: '#BA7517' }}>⚡ cached</span>}
              {result.source === 'dataset' && <span style={{ ...s.sourceBadge, background: '#EAF3DE', color: '#0F6E56' }}>📦 dataset</span>}
              {result.source === 'live'    && <span style={{ ...s.sourceBadge, background: '#E6F1FB', color: '#185FA5' }}>🌐 live</span>}
            </div>

            <div style={s.componentName}>{result.name}</div>
            <p style={s.description}>{result.description}</p>

            <div style={s.divider} />

            <div style={s.sectionLabel2}>Specifications</div>
            <SpecsGrid specs={result.specs} />

            <div style={s.divider} />

            <div style={s.footer}>
              {result.datasheet_url && (
                <a href={result.datasheet_url} target="_blank" rel="noopener noreferrer" style={s.dsLink}>
                  <LinkIcon /><span>View Datasheet</span>
                </a>
              )}
              <span style={s.metaItem}>Source: Wikipedia + Dataset</span>
            </div>
          </section>

          {/* Alternatives */}
          <AlternativesSection
            name={result.name}
            alts={alts}
            loading={altStatus === 'loading'}
          />
        </>)}

        {/* Error */}
        {status === 'error' && (
          <section style={{ ...s.card, ...s.errorCard }}>
            <div style={s.errorTitle}>Not Found</div>
            <p style={s.errorMsg}>{error}</p>
            <p style={s.errorHint}>Try: "LM7805", "NE555", "BC547", "IRF540N"</p>
          </section>
        )}

        {/* Empty state */}
        {status === 'idle' && (
          <section style={s.emptyState}>
            <div style={{ opacity: 0.25 }}><ChipIcon /></div>
            <p style={{ fontSize: 14, color: '#9CA3AF' }}>Enter a component to get specs + alternatives</p>
          </section>
        )}

      </main>
    </div>
  )
}

// ─── STYLES ──────────────────────────────────────────────────────────────────

const s = {
  page:        { minHeight: '100vh', background: '#F5F7FA', fontFamily: "'IBM Plex Sans', system-ui, sans-serif" },
  header:      { background: '#185FA5', borderBottom: '1px solid #0C447C' },
  headerInner: { maxWidth: 720, margin: '0 auto', padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  logo:        { display: 'flex', alignItems: 'center', gap: 12 },
  logoIcon:    { color: 'rgba(255,255,255,0.85)', display: 'flex', alignItems: 'center' },
  logoTitle:   { color: '#fff', fontWeight: 700, fontSize: 16 },
  logoSub:     { color: 'rgba(255,255,255,0.6)', fontSize: 11, fontFamily: 'monospace', marginTop: 2 },
  badge:       { background: 'rgba(255,255,255,0.15)', color: '#fff', fontSize: 11, fontFamily: 'monospace', padding: '3px 10px', borderRadius: 20, border: '1px solid rgba(255,255,255,0.25)' },

  main:        { maxWidth: 720, margin: '0 auto', padding: '28px 20px', display: 'flex', flexDirection: 'column', gap: 16 },
  card:        { background: '#fff', border: '1px solid #E5E7EB', borderRadius: 12, padding: '20px' },

  label:       { display: 'block', fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 },
  searchRow:   { display: 'flex', gap: 10 },
  input:       { flex: 1, height: 44, border: '1.5px solid #D1D5DB', borderRadius: 8, padding: '0 14px', fontSize: 14, fontFamily: 'inherit', outline: 'none' },
  btn:         { height: 44, padding: '0 20px', background: '#185FA5', color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7 },
  btnDisabled: { background: '#93B8D8', cursor: 'not-allowed' },
  spinner:     { width: 18, height: 18, border: '2px solid rgba(255,255,255,0.35)', borderTopColor: '#fff', borderRadius: '50%', display: 'inline-block', animation: 'spin 0.7s linear infinite' },
  pills:       { display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 14 },
  pill:        { background: '#E6F1FB', color: '#185FA5', border: 'none', borderRadius: 20, padding: '5px 13px', fontSize: 12, fontWeight: 600, cursor: 'pointer' },

  resultHeader:  { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 },
  resultDot:     { width: 8, height: 8, borderRadius: '50%', background: '#0F6E56', flexShrink: 0 },
  resultTag:     { fontSize: 11, fontWeight: 700, color: '#0F6E56', textTransform: 'uppercase', letterSpacing: '0.07em' },
  sourceBadge:   { marginLeft: 'auto', fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600 },

  componentName: { fontSize: 22, fontWeight: 700, color: '#111827', marginBottom: 10, fontFamily: 'monospace' },
  description:   { fontSize: 14, lineHeight: 1.75, color: '#374151' },
  divider:       { borderTop: '1px solid #F3F4F6', margin: '16px 0' },
  sectionLabel2: { fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 },

  specsGrid:  { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 },
  specCard:   { borderRadius: 10, padding: '12px 14px' },
  specLabel:  { fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4, opacity: 0.75 },
  specValue:  { fontSize: 15, fontWeight: 700, fontFamily: 'monospace' },
  specNA:     { opacity: 0.3 },
  noSpecs:    { fontSize: 13, color: '#9CA3AF', fontStyle: 'italic', lineHeight: 1.6 },

  footer:     { display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 },
  dsLink:     { display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: '#185FA5', background: '#E6F1FB', padding: '7px 14px', borderRadius: 8, textDecoration: 'none', border: '1px solid #BDD8F0' },
  metaItem:   { fontSize: 11, color: '#9CA3AF', fontFamily: 'monospace' },

  // Alternatives
  sectionLabelRow:  { display: 'flex', alignItems: 'center', gap: 7, marginBottom: 14 },
  sectionIcon:      { color: '#6B7280', display: 'flex', alignItems: 'center' },
  sectionLabelText: { fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.07em' },

  altGrid:    { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 },
  altCard:    { border: '1px solid #E5E7EB', borderRadius: 10, padding: '13px 14px', background: '#FAFAFA' },
  altName:    { fontSize: 15, fontWeight: 700, fontFamily: 'monospace', color: '#111827', marginBottom: 8 },
  altBadges:  { display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 8 },
  altBadge:   { fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 20 },
  badgeType:    { background: '#EEEDFE', color: '#534AB7' },
  badgeVoltage: { background: '#E6F1FB', color: '#185FA5' },
  badgeCurrent: { background: '#EAF3DE', color: '#0F6E56' },
  altReason:  { fontSize: 12, color: '#6B7280', lineHeight: 1.5 },
  altLoading: { fontSize: 13, color: '#9CA3AF', fontStyle: 'italic' },

  errorCard:  { borderColor: '#FCA5A5', background: '#FFF5F5' },
  errorTitle: { fontSize: 14, fontWeight: 700, color: '#DC2626', marginBottom: 6 },
  errorMsg:   { fontSize: 13, color: '#7F1D1D', marginBottom: 8 },
  errorHint:  { fontSize: 12, color: '#B45309', fontFamily: 'monospace' },

  emptyState: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '48px 20px' },
}