import { useState, useCallback } from 'react'

// ─── API ─────────────────────────────────────────────────────────────────────

async function fetchComponent(name) {
  const res  = await fetch(`/component?name=${encodeURIComponent(name)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Not found')
  return data
}
async function fetchAlternatives(name) {
  const res  = await fetch(`/alternatives?name=${encodeURIComponent(name)}`)
  const data = await res.json()
  if (!res.ok) return []
  return data.alternatives || []
}

// ─── ICONS ───────────────────────────────────────────────────────────────────

const Ico = ({ d, size = 16, fill = 'none', sw = 2 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill}
    stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round">
    {typeof d === 'string' ? <path d={d}/> : d}
  </svg>
)
const SearchIcon  = () => <Ico d={<><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></>}/>
const ChipIcon    = () => <Ico size={22} d={<><rect x="7" y="7" width="10" height="10" rx="1"/><path d="M9 7V4M12 7V4M15 7V4M9 17v3M12 17v3M15 17v3M7 9H4M7 12H4M7 15H4M17 9h3M17 12h3M17 15h3"/></>}/>
const LinkIcon    = () => <Ico size={13} d={<><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></>}/>
const BackIcon    = () => <Ico d="M19 12H5M12 19l-7-7 7-7"/>
const ScaleIcon   = () => <Ico d={<><line x1="12" y1="3" x2="12" y2="21"/><path d="M3 9l4-6 4 6"/><path d="M17 15l4 6H13z"/></>}/>
const StarIcon    = () => <Ico size={10} fill="currentColor" sw={0} d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
const ArrowRight  = () => <Ico size={13} d="M5 12h14M12 5l7 7-7 7"/>

// ─── SMART LABEL LOGIC ───────────────────────────────────────────────────────

function parseVal(str) {
  if (!str) return null
  const m = str.match(/([\d.]+)\s*(k|m|µ|u)?([avw])/i)
  if (!m) return null
  let v = parseFloat(m[1])
  const p = (m[2] || '').toLowerCase()
  if (p === 'k') v *= 1000
  if (p === 'm') v /= 1000
  if (p === 'µ' || p === 'u') v /= 1e6
  return v
}

function smartLabel(alt, mainSpecs) {
  const aV = parseVal(alt.voltage),  mV = parseVal(mainSpecs?.voltage)
  const aI = parseVal(alt.current),  mI = parseVal(mainSpecs?.current)
  if (aV && mV && aI && mI) {
    if (Math.abs(aV-mV)/mV < 0.15 && Math.abs(aI-mI)/mI < 0.15)
      return { text:'Closest Match', color:'var(--emerald)', bg:'var(--em-dim)', icon:'◎' }
  }
  if (aI && mI && aI > mI*1.15) return { text:'Higher Current', color:'var(--purple)', bg:'rgba(188,140,255,0.12)', icon:'⚡' }
  if (aV && mV && aV < mV*0.85)  return { text:'Lower Voltage',  color:'var(--blue)',   bg:'var(--blue-dim)',       icon:'▼' }
  if (aV && mV && aV > mV*1.15)  return { text:'Higher Voltage', color:'var(--amber)',  bg:'var(--amber-dim)',      icon:'▲' }
  if (aV && mV && Math.abs(aV-mV)/mV < 0.1) return { text:'Same Voltage', color:'var(--blue)', bg:'var(--blue-dim)', icon:'=' }
  return { text:'Alternative', color:'var(--text2)', bg:'rgba(139,148,158,0.12)', icon:'◇' }
}

// ─── SOURCE BADGE ─────────────────────────────────────────────────────────────

function SourceBadge({ source }) {
  const map = {
    cache:   { label:'⚡ cached',  color:'#F0A500', bg:'rgba(240,165,0,0.12)' },
    dataset: { label:'📦 dataset', color:'#3FB950', bg:'rgba(63,185,80,0.12)' },
    live:    { label:'🌐 live',    color:'#58A6FF', bg:'rgba(88,166,255,0.12)' },
    nexar:   { label:'🔌 nexar',   color:'#BC8CFF', bg:'rgba(188,140,255,0.12)' },
    mouser:  { label:'🛒 mouser',  color:'#F0A500', bg:'rgba(240,165,0,0.12)' },
    ai:      { label:'🤖 ai gen',  color:'#F85149', bg:'rgba(248,81,73,0.12)' },
  }
  const m = map[source] || map.live
  return (
    <span style={{ fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
      padding:'2px 8px', borderRadius:20, letterSpacing:'0.04em',
      color:m.color, background:m.bg, border:`1px solid ${m.color}40` }}>
      {m.label}
    </span>
  )
}

// ─── SPEC PILL ────────────────────────────────────────────────────────────────

function SpecPill({ label, value, color, bg }) {
  if (!value) return null
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6,
      background:bg, border:`1px solid ${color}30`,
      borderRadius:8, padding:'8px 12px' }}>
      <span style={{ fontSize:9, fontWeight:800, fontFamily:'var(--mono)',
        color:color, opacity:0.7, textTransform:'uppercase', letterSpacing:'0.08em' }}>
        {label}
      </span>
      <span style={{ fontSize:14, fontWeight:700, fontFamily:'var(--mono)', color:color }}>
        {value}
      </span>
    </div>
  )
}

// ─── COMPARISON CARD ─────────────────────────────────────────────────────────

function ComparisonCard({ alt, mainSpecs, rank, onNavigate }) {
  const lbl    = smartLabel(alt, mainSpecs)
  const isBest = rank === 0
  const [hov, setHov] = useState(false)

  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        position:'relative', borderRadius:12,
        border:`1.5px solid ${isBest ? 'var(--amber)' : hov ? 'var(--border2)' : 'var(--border)'}`,
        background: isBest ? 'rgba(240,165,0,0.05)' : hov ? 'var(--bg3)' : 'var(--bg2)',
        padding:'16px', display:'flex', flexDirection:'column', gap:10,
        cursor:'pointer',
        boxShadow: isBest ? '0 0 20px rgba(240,165,0,0.1)' : hov ? '0 4px 16px rgba(0,0,0,0.3)' : 'none',
        transition:'all 0.18s ease',
      }}
      onClick={() => onNavigate(alt.name)}
    >
      {isBest && (
        <div style={{ position:'absolute', top:-1, right:14,
          background:'var(--amber)', color:'#000',
          fontSize:9, fontWeight:800, letterSpacing:'0.06em',
          padding:'3px 10px', borderRadius:'0 0 8px 8px',
          display:'flex', alignItems:'center', gap:4 }}>
          <StarIcon /> BEST PICK
        </div>
      )}

      {/* Smart label */}
      <span style={{ alignSelf:'flex-start', fontSize:10, fontWeight:700,
        fontFamily:'var(--mono)', padding:'2px 8px', borderRadius:20,
        color:lbl.color, background:lbl.bg, letterSpacing:'0.04em' }}>
        {lbl.icon} {lbl.text}
      </span>

      {/* Name */}
      <div style={{ fontSize:16, fontWeight:700, fontFamily:'var(--mono)',
        color: isBest ? 'var(--amber)' : 'var(--text)' }}>
        {alt.name}
      </div>

      {/* Type */}
      {alt.type && (
        <div style={{ fontSize:11, color:'var(--text2)', lineHeight:1.3 }}>{alt.type}</div>
      )}

      {/* Specs */}
      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
        {alt.voltage && (
          <span style={{ fontSize:11, fontWeight:600, fontFamily:'var(--mono)',
            color:'var(--blue)', background:'var(--blue-dim)',
            padding:'2px 8px', borderRadius:6 }}>
            {alt.voltage}
          </span>
        )}
        {alt.current && (
          <span style={{ fontSize:11, fontWeight:600, fontFamily:'var(--mono)',
            color:'var(--emerald)', background:'var(--em-dim)',
            padding:'2px 8px', borderRadius:6 }}>
            {alt.current}
          </span>
        )}
      </div>

      {/* Reason */}
      <div style={{ fontSize:11, color:'var(--text2)', lineHeight:1.55, flexGrow:1 }}>
        {alt.reason}
      </div>

      {/* CTA */}
      <div style={{ display:'flex', alignItems:'center', gap:6,
        fontSize:11, fontWeight:600, color: isBest ? 'var(--amber)' : 'var(--text2)',
        marginTop:4, opacity: hov ? 1 : 0.6, transition:'opacity 0.15s' }}>
        View this component <ArrowRight />
      </div>
    </div>
  )
}

// ─── BREADCRUMB ───────────────────────────────────────────────────────────────

function Breadcrumb({ history, onBack }) {
  if (history.length === 0) return null
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8,
      padding:'10px 16px', background:'var(--bg2)',
      border:'1px solid var(--border)', borderRadius:10,
      marginBottom:4 }}>
      <button onClick={onBack} style={{
        display:'flex', alignItems:'center', gap:6,
        background:'var(--amber-dim)', border:'1px solid var(--amber)40',
        borderRadius:6, padding:'5px 12px',
        color:'var(--amber)', fontSize:12, fontWeight:600,
        cursor:'pointer', fontFamily:'var(--sans)',
      }}>
        <BackIcon /> Back
      </button>
      <div style={{ display:'flex', alignItems:'center', gap:4, overflow:'hidden' }}>
        {history.map((h, i) => (
          <span key={i} style={{ display:'flex', alignItems:'center', gap:4 }}>
            <span style={{ fontSize:11, fontFamily:'var(--mono)',
              color:'var(--text2)', whiteSpace:'nowrap', overflow:'hidden',
              textOverflow:'ellipsis', maxWidth:120 }}>
              {h.result.name}
            </span>
            <span style={{ color:'var(--border2)', fontSize:11 }}>›</span>
          </span>
        ))}
        <span style={{ fontSize:11, fontFamily:'var(--mono)', color:'var(--amber)' }}>
          current
        </span>
      </div>
    </div>
  )
}

// ─── COMPARISON SECTION ───────────────────────────────────────────────────────

function ComparisonSection({ mainResult, alts, loading, onNavigate }) {
  if (loading) return (
    <div style={D.section}>
      <div style={D.secHeader}>
        <span style={{ color:'var(--amber)', display:'flex' }}><ScaleIcon /></span>
        <div>
          <div style={D.secTitle}>Compare with Similar Components</div>
          <div style={D.secSub}>Analysing alternatives…</div>
        </div>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(200px,1fr))', gap:12 }}>
        {[0,1,2].map(i => (
          <div key={i} style={{ height:180, borderRadius:12, border:'1px solid var(--border)',
            background:`linear-gradient(90deg,var(--bg2) 25%,var(--bg3) 50%,var(--bg2) 75%)`,
            backgroundSize:'200% 100%', animation:'shimmer 1.5s infinite' }}/>
        ))}
      </div>
    </div>
  )

  if (!alts || alts.length === 0) return (
    <div style={D.section}>
      <div style={D.secHeader}>
        <span style={{ color:'var(--amber)', display:'flex' }}><ScaleIcon /></span>
        <div>
          <div style={D.secTitle}>Compare with Similar Components</div>
          <div style={D.secSub}>No alternatives found for this component type.</div>
        </div>
      </div>
    </div>
  )

  const mainSpecs = mainResult?.specs

  return (
    <div style={D.section} className="fade-up">
      {/* Header */}
      <div style={D.secHeader}>
        <span style={{ color:'var(--amber)', display:'flex' }}><ScaleIcon /></span>
        <div>
          <div style={D.secTitle}>Compare with Similar Components</div>
          <div style={D.secSub}>{alts.length} alternatives — click any card to navigate</div>
        </div>
      </div>

      {/* Comparison table */}
      <div style={{ background:'var(--bg)', border:'1px solid var(--border)',
        borderRadius:10, overflow:'hidden', marginBottom:16 }}>

        {/* Table header */}
        <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr 1fr 1.4fr',
          padding:'8px 16px', borderBottom:'1px solid var(--border)',
          background:'var(--bg2)' }}>
          {['Component','Voltage','Current','Highlight'].map(h => (
            <span key={h} style={{ fontSize:10, fontWeight:700, color:'var(--text3)',
              textTransform:'uppercase', letterSpacing:'0.07em', fontFamily:'var(--mono)' }}>
              {h}
            </span>
          ))}
        </div>

        {/* Main component row */}
        <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr 1fr 1.4fr',
          alignItems:'center', padding:'12px 16px',
          borderBottom:'1px solid var(--border)',
          background:'rgba(240,165,0,0.05)',
          borderLeft:'3px solid var(--amber)' }}>
          <div>
            <div style={{ fontSize:13, fontWeight:700, fontFamily:'var(--mono)', color:'var(--amber)' }}>
              {mainResult?.name}
            </div>
            <div style={{ fontSize:10, color:'var(--text2)', marginTop:2 }}>
              {mainResult?.specs?.type || '—'}
            </div>
          </div>
          <span style={{ fontSize:12, fontWeight:600, fontFamily:'var(--mono)',
            color:'var(--blue)', background:'var(--blue-dim)',
            padding:'2px 8px', borderRadius:6, display:'inline-block', width:'fit-content' }}>
            {mainResult?.specs?.voltage || '—'}
          </span>
          <span style={{ fontSize:12, fontWeight:600, fontFamily:'var(--mono)',
            color:'var(--emerald)', background:'var(--em-dim)',
            padding:'2px 8px', borderRadius:6, display:'inline-block', width:'fit-content' }}>
            {mainResult?.specs?.current || '—'}
          </span>
          <span style={{ fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
            color:'var(--amber)', background:'var(--amber-dim)',
            padding:'2px 8px', borderRadius:20, display:'inline-block', width:'fit-content' }}>
            ● Selected
          </span>
        </div>

        {/* Alt rows */}
        {alts.map((alt, i) => {
          const lbl = smartLabel(alt, mainSpecs)
          return (
            <AltTableRow key={alt.name} alt={alt} lbl={lbl} isFirst={i===0}
              isLast={i===alts.length-1} onNavigate={onNavigate} />
          )
        })}
      </div>

      {/* Cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(210px,1fr))', gap:12 }}>
        {alts.slice(0,3).map((alt, i) => (
          <ComparisonCard key={alt.name} alt={alt} mainSpecs={mainSpecs}
            rank={i} onNavigate={onNavigate} />
        ))}
      </div>
    </div>
  )
}

function AltTableRow({ alt, lbl, isFirst, isLast, onNavigate }) {
  const [hov, setHov] = useState(false)
  return (
    <div
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      onClick={() => onNavigate(alt.name)}
      style={{
        display:'grid', gridTemplateColumns:'2fr 1fr 1fr 1.4fr',
        alignItems:'center', padding:'10px 16px',
        borderBottom: isLast ? 'none' : '1px solid var(--border)',
        background: hov ? 'var(--bg2)' : 'transparent',
        cursor:'pointer', transition:'background 0.15s',
        borderLeft: isFirst ? '3px solid var(--emerald)' : '3px solid transparent',
      }}>
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
        {isFirst && <span style={{ color:'var(--amber)', display:'flex' }}><StarIcon /></span>}
        <div>
          <div style={{ fontSize:13, fontWeight:700, fontFamily:'var(--mono)',
            color: hov ? 'var(--text)' : 'var(--text2)' }}>
            {alt.name}
          </div>
          <div style={{ fontSize:10, color:'var(--text3)', marginTop:1 }}>{alt.type||'—'}</div>
        </div>
      </div>
      <span style={{ fontSize:12, fontWeight:600, fontFamily:'var(--mono)',
        color:'var(--blue)', background:'var(--blue-dim)',
        padding:'2px 8px', borderRadius:6, display:'inline-block', width:'fit-content' }}>
        {alt.voltage||'—'}
      </span>
      <span style={{ fontSize:12, fontWeight:600, fontFamily:'var(--mono)',
        color:'var(--emerald)', background:'var(--em-dim)',
        padding:'2px 8px', borderRadius:6, display:'inline-block', width:'fit-content' }}>
        {alt.current||'—'}
      </span>
      <span style={{ fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
        color:lbl.color, background:lbl.bg,
        padding:'2px 8px', borderRadius:20, display:'inline-block', width:'fit-content' }}>
        {lbl.icon} {lbl.text}
      </span>
    </div>
  )
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────

const SUGGESTIONS = ['LM7805','NE555','BC547','IRF540N','LM741','1N4007']

export default function App() {
  const [query,     setQuery]     = useState('')
  const [result,    setResult]    = useState(null)
  const [alts,      setAlts]      = useState(null)
  const [status,    setStatus]    = useState('idle')
  const [altStatus, setAltStatus] = useState('idle')
  const [error,     setError]     = useState('')
  // Navigation history stack: [{result, alts, query}]
  const [history,   setHistory]   = useState([])

  const doSearch = useCallback(async (name) => {
    const nm = name.trim()
    if (!nm) return
    setQuery(nm)
    setStatus('loading')
    setResult(null)
    setAlts(null)
    setAltStatus('idle')
    setError('')
    try {
      const data = await fetchComponent(nm)
      setResult(data)
      setStatus('success')
      setAltStatus('loading')
      const altData = await fetchAlternatives(data.name)
      setAlts(altData)
      setAltStatus('done')
    } catch (err) {
      setError(err.message)
      setStatus('error')
    }
  }, [])

  // Navigate to an alternative — push current to history
  const navigateTo = useCallback((name) => {
    if (result) {
      setHistory(h => [...h, { result, alts, query }])
    }
    doSearch(name)
  }, [result, alts, query, doSearch])

  // Go back
  const goBack = useCallback(() => {
    const prev = history[history.length - 1]
    if (!prev) return
    setHistory(h => h.slice(0, -1))
    setQuery(prev.query)
    setResult(prev.result)
    setAlts(prev.alts)
    setStatus('success')
    setAltStatus(prev.alts ? 'done' : 'idle')
  }, [history])

  return (
    <div style={{ minHeight:'100vh', fontFamily:'var(--sans)' }}>

      {/* Header */}
      <header style={{ borderBottom:'1px solid var(--border)', background:'rgba(13,17,23,0.85)',
        backdropFilter:'blur(12px)', position:'sticky', top:0, zIndex:100 }}>
        <div style={{ maxWidth:900, margin:'0 auto', padding:'12px 20px',
          display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <span style={{ color:'var(--amber)', display:'flex' }}><ChipIcon /></span>
            <div>
              <div style={{ fontWeight:700, fontSize:15, color:'var(--text)',
                letterSpacing:'-0.01em' }}>
                Smart Component System
              </div>
              <div style={{ fontSize:10, color:'var(--text2)', fontFamily:'var(--mono)', marginTop:1 }}>
                v4.0 · multi-source · AI-powered
              </div>
            </div>
          </div>
          <div style={{ display:'flex', gap:6 }}>
            {['Mouser','Nexar','OpenRouter'].map(s => (
              <span key={s} style={{ fontSize:9, fontWeight:700, fontFamily:'var(--mono)',
                color:'var(--emerald)', background:'var(--em-dim)',
                padding:'2px 7px', borderRadius:20, letterSpacing:'0.04em' }}>
                {s}
              </span>
            ))}
          </div>
        </div>
      </header>

      <main style={{ maxWidth:900, margin:'0 auto', padding:'24px 20px',
        display:'flex', flexDirection:'column', gap:14 }}>

        {/* Search */}
        <div style={D.section}>
          <div style={{ fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
            color:'var(--text3)', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:10 }}>
            Component Name
          </div>
          <div style={{ display:'flex', gap:10 }}>
            <input
              style={{ flex:1, height:44, background:'var(--bg)',
                border:'1.5px solid var(--border)', borderRadius:8,
                padding:'0 14px', fontSize:14, fontFamily:'var(--sans)',
                color:'var(--text)', outline:'none',
                transition:'border-color 0.15s' }}
              onFocus={e => e.target.style.borderColor = 'var(--amber)'}
              onBlur={e  => e.target.style.borderColor = 'var(--border)'}
              type="text"
              placeholder="e.g. LM7805, NE555, BC547…"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && doSearch(query)}
              disabled={status === 'loading'}
              autoFocus
            />
            <button
              onClick={() => doSearch(query)}
              disabled={status === 'loading'}
              style={{ height:44, padding:'0 20px',
                background: status === 'loading' ? 'rgba(240,165,0,0.3)' : 'var(--amber)',
                color:'#000', border:'none', borderRadius:8,
                fontSize:13, fontWeight:700, cursor: status==='loading'?'not-allowed':'pointer',
                display:'flex', alignItems:'center', gap:7, fontFamily:'var(--sans)',
                transition:'background 0.15s' }}>
              {status === 'loading'
                ? <span style={{ width:18, height:18, border:'2px solid rgba(0,0,0,0.3)',
                    borderTopColor:'#000', borderRadius:'50%',
                    display:'inline-block', animation:'spin 0.7s linear infinite' }}/>
                : <><SearchIcon /><span>Search</span></>}
            </button>
          </div>

          {/* Pills */}
          <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginTop:12 }}>
            {SUGGESTIONS.map(sg => (
              <button key={sg} onClick={() => doSearch(sg)}
                disabled={status==='loading'}
                style={{ background:'var(--bg)', border:'1px solid var(--border)',
                  borderRadius:20, padding:'4px 12px', fontSize:11,
                  fontWeight:600, fontFamily:'var(--mono)', color:'var(--text2)',
                  cursor:'pointer', transition:'all 0.15s' }}
                onMouseEnter={e => { e.target.style.borderColor='var(--amber)'; e.target.style.color='var(--amber)' }}
                onMouseLeave={e => { e.target.style.borderColor='var(--border)'; e.target.style.color='var(--text2)' }}>
                {sg}
              </button>
            ))}
          </div>
        </div>

        {/* Breadcrumb navigation */}
        <Breadcrumb history={history} onBack={goBack} />

        {/* Result */}
        {status === 'success' && result && (
          <div className="fade-up" style={D.section}>
            {/* Result header */}
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:14 }}>
              <span style={{ width:7, height:7, borderRadius:'50%',
                background:'var(--emerald)', boxShadow:'0 0 8px var(--emerald)',
                flexShrink:0, display:'inline-block' }}/>
              <span style={{ fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
                color:'var(--emerald)', textTransform:'uppercase', letterSpacing:'0.08em' }}>
                Selected Component
              </span>
              <div style={{ marginLeft:'auto' }}>
                <SourceBadge source={result.source} />
              </div>
            </div>

            {/* Component name */}
            <div style={{ fontSize:26, fontWeight:700, fontFamily:'var(--mono)',
              color:'var(--amber)', letterSpacing:'-0.01em', marginBottom:10 }}>
              {result.name}
            </div>

            {/* Description */}
            <p style={{ fontSize:13, lineHeight:1.75, color:'var(--text2)',
              maxWidth:660, marginBottom:16 }}>
              {result.description}
            </p>

            {/* Specs */}
            <div style={{ fontSize:10, fontWeight:700, fontFamily:'var(--mono)',
              color:'var(--text3)', textTransform:'uppercase', letterSpacing:'0.08em', marginBottom:8 }}>
              Specifications
            </div>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:16 }}>
              <SpecPill label="Type"    value={result.specs?.type}    color="var(--purple)" bg="rgba(188,140,255,0.1)"/>
              <SpecPill label="Voltage" value={result.specs?.voltage} color="var(--blue)"   bg="var(--blue-dim)"/>
              <SpecPill label="Current" value={result.specs?.current} color="var(--emerald)"bg="var(--em-dim)"/>
              {!Object.values(result.specs||{}).some(v=>v) && (
                <span style={{ fontSize:12, color:'var(--text3)', fontStyle:'italic' }}>
                  Detailed specifications unavailable.
                </span>
              )}
            </div>

            {/* Divider + footer */}
            <div style={{ borderTop:'1px solid var(--border)', paddingTop:12,
              display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              {result.datasheet_url && (
                <a href={result.datasheet_url} target="_blank" rel="noopener noreferrer"
                  style={{ display:'inline-flex', alignItems:'center', gap:6,
                    fontSize:12, fontWeight:600, color:'var(--amber)',
                    background:'var(--amber-dim)', padding:'7px 14px',
                    borderRadius:8, textDecoration:'none',
                    border:'1px solid var(--amber)40' }}>
                  <LinkIcon /> View Datasheet
                </a>
              )}
              <span style={{ fontSize:10, color:'var(--text3)', fontFamily:'var(--mono)' }}>
                source: {result.source}
              </span>
            </div>
          </div>
        )}

        {/* Comparison Section */}
        {status === 'success' && result && (
          <ComparisonSection
            mainResult={result}
            alts={alts}
            loading={altStatus === 'loading'}
            onNavigate={navigateTo}
          />
        )}

        {/* Error */}
        {status === 'error' && (
          <div style={{ ...D.section, borderColor:'var(--rose)', background:'rgba(248,81,73,0.05)' }}
            className="fade-up">
            <div style={{ fontSize:13, fontWeight:700, color:'var(--rose)', marginBottom:6 }}>
              Component Not Found
            </div>
            <p style={{ fontSize:13, color:'#c9827e', marginBottom:8 }}>{error}</p>
            <p style={{ fontSize:11, color:'var(--text3)', fontFamily:'var(--mono)' }}>
              Try: "LM7805", "NE555", "BC547", "IRF540N"
            </p>
          </div>
        )}

        {/* Empty state */}
        {status === 'idle' && (
          <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
            gap:14, padding:'60px 20px', opacity:0.4 }}>
            <span style={{ color:'var(--amber)' }}><ChipIcon /></span>
            <p style={{ fontSize:13, color:'var(--text2)', fontFamily:'var(--mono)' }}>
              search a component to begin
            </p>
          </div>
        )}

      </main>
    </div>
  )
}

// ─── SHARED SECTION STYLE ─────────────────────────────────────────────────────

const D = {
  section: {
    background:'var(--bg2)',
    border:'1px solid var(--border)',
    borderRadius:12,
    padding:'20px',
  },
  secHeader: {
    display:'flex', alignItems:'flex-start', gap:10, marginBottom:18,
  },
  secTitle: {
    fontSize:14, fontWeight:700, color:'var(--text)', letterSpacing:'-0.01em',
  },
  secSub: {
    fontSize:11, color:'var(--text2)', marginTop:2, fontFamily:'var(--mono)',
  },
}
