import { useState, useCallback, useEffect } from 'react'

// ─── API ─────────────────────────────────────────────────────────────────────
async function fetchComponent(name) {
  const res = await fetch(`/component?name=${encodeURIComponent(name)}`)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Not found')
  return data
}
async function fetchAlternatives(name) {
  const res = await fetch(`/alternatives?name=${encodeURIComponent(name)}`)
  const data = await res.json()
  if (!res.ok) return []
  return data.alternatives || []
}
async function fetchPricing(name) {
  try {
    const res  = await fetch(`/pricing?name=${encodeURIComponent(name)}`)
    const data = await res.json()
    return data.pricing || {}
  } catch { return {} }
}

// ─── SPEC SCHEMA ─────────────────────────────────────────────────────────────
const SPEC_SCHEMA = {
  type:         { label:'Type',         group:'core',       icon:'⬡', color:'147,112,219' },
  voltage:      { label:'Voltage',      group:'electrical', icon:'⚡', color:'77,158,255'  },
  current:      { label:'Current',      group:'electrical', icon:'〜', color:'0,184,160'   },
  power:        { label:'Power Diss.',  group:'electrical', icon:'♨', color:'251,146,60'  },
  resistance:   { label:'Resistance',  group:'electrical', icon:'Ω',  color:'234,179,8'   },
  capacitance:  { label:'Capacitance', group:'electrical', icon:'⊣',  color:'52,211,153'  },
  inductance:   { label:'Inductance',  group:'electrical', icon:'⌁',  color:'96,165,250'  },
  frequency:    { label:'Frequency',   group:'electrical', icon:'≋',  color:'167,139,250' },
  gain:         { label:'Gain / hFE',  group:'electrical', icon:'▲',  color:'251,191,36'  },
  rds_on:       { label:'RDS(on)',      group:'mosfet',     icon:'⊿',  color:'74,222,128'  },
  vgs_th:       { label:'VGS(th)',      group:'mosfet',     icon:'⊳',  color:'110,231,183' },
  dropout:      { label:'Dropout V',   group:'regulator',  icon:'↓',  color:'248,113,113' },
  accuracy:     { label:'Accuracy',    group:'regulator',  icon:'◎',  color:'52,211,153'  },
  logic_family: { label:'Logic Family',group:'digital',    icon:'□',  color:'129,140,248' },
  temp_range:   { label:'Temp Range',  group:'thermal',    icon:'🌡', color:'251,146,60'  },
  package:      { label:'Package',     group:'physical',   icon:'◫',  color:'148,163,184' },
  mounting:     { label:'Mounting',    group:'physical',   icon:'⊕',  color:'148,163,184' },
}

const DISPLAY_ORDER = [
  'type','voltage','current','power','resistance','capacitance',
  'inductance','frequency','gain','rds_on','vgs_th','dropout',
  'accuracy','logic_family','temp_range','package','mounting'
]

// Groups for detailed view sections
const SPEC_GROUPS = {
  core:       { label:'General',    color:'147,112,219' },
  electrical: { label:'Electrical', color:'77,158,255'  },
  mosfet:     { label:'MOSFET',     color:'74,222,128'  },
  regulator:  { label:'Regulator',  color:'248,113,113' },
  digital:    { label:'Digital',    color:'129,140,248' },
  thermal:    { label:'Thermal',    color:'251,146,60'  },
  physical:   { label:'Physical',   color:'148,163,184' },
}

function getOrderedSpecs(specs) {
  if (!specs) return []
  return DISPLAY_ORDER
    .filter(key => specs[key] && SPEC_SCHEMA[key])
    .map(key => ({ key, value: specs[key], ...SPEC_SCHEMA[key] }))
}

function altToSpecs(alt) {
  const obj = {}
  for (const key of DISPLAY_ORDER) {
    const val = alt?.specs?.[key] ?? alt?.[key]
    if (val && typeof val === 'string') obj[key] = val
  }
  return obj
}

// ─── ICONS ───────────────────────────────────────────────────────────────────
const Svg = ({ ch, size=16, sw=2, fill='none' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill={fill}
    stroke="currentColor" strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round">
    {ch}
  </svg>
)
const IcoSearch  = () => <Svg ch={<><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></>}/>
const IcoChip    = () => <Svg size={20} ch={<><rect x="7" y="7" width="10" height="10" rx="1"/><path d="M9 7V4M12 7V4M15 7V4M9 17v3M12 17v3M15 17v3M7 9H4M7 12H4M7 15H4M17 9h3M17 12h3M17 15h3"/></>}/>
const IcoLink    = () => <Svg size={13} ch={<><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></>}/>
const IcoBack    = () => <Svg ch={<path d="M19 12H5M12 19l-7-7 7-7"/>}/>
const IcoScale   = () => <Svg ch={<path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/>}/>
const IcoStar    = () => <Svg size={11} fill="currentColor" sw={0} ch={<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>}/>
const IcoArrow   = () => <Svg size={13} ch={<><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></>}/>
const IcoTag     = () => <Svg size={13} ch={<><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></>}/>
const IcoTable   = () => <Svg ch={<><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/></>}/>
const IcoCards   = () => <Svg ch={<><rect x="2" y="3" width="9" height="13" rx="1"/><rect x="13" y="3" width="9" height="13" rx="1"/><line x1="2" y1="20" x2="22" y2="20"/></>}/>

// ─── SMART LABEL ─────────────────────────────────────────────────────────────
function parseVal(str) {
  if (!str) return null
  const m = str.match(/([\d.]+)\s*(k|m|µ|u)?([avwΩhzf])/i)
  if (!m) return null
  let v = parseFloat(m[1])
  const p = (m[2]||'').toLowerCase()
  if (p==='k') v*=1000; if (p==='m') v/=1000
  if (p==='µ'||p==='u') v/=1e6
  return v
}
function smartLabel(alt, mainSpecs) {
  const aV=parseVal(alt.voltage||alt.specs?.voltage), mV=parseVal(mainSpecs?.voltage)
  const aI=parseVal(alt.current||alt.specs?.current), mI=parseVal(mainSpecs?.current)
  const aP=parseVal(alt.power  ||alt.specs?.power),   mP=parseVal(mainSpecs?.power)
  if (aV&&mV&&aI&&mI&&Math.abs(aV-mV)/mV<.15&&Math.abs(aI-mI)/mI<.15)
    return {text:'Closest Match', color:'0,184,160',   bg:'rgba(0,184,160,0.1)',   icon:'◎'}
  if (aI&&mI&&aI>mI*1.15) return {text:'Higher Current',color:'167,139,250',bg:'rgba(167,139,250,0.1)',icon:'⚡'}
  if (aP&&mP&&aP>mP*1.15) return {text:'Higher Power',  color:'251,146,60', bg:'rgba(251,146,60,0.1)', icon:'♨'}
  if (aV&&mV&&aV<mV*.85)  return {text:'Lower Voltage', color:'77,158,255', bg:'rgba(77,158,255,0.1)', icon:'▼'}
  if (aV&&mV&&aV>mV*1.15) return {text:'Higher Voltage',color:'232,160,32', bg:'rgba(232,160,32,0.1)',icon:'▲'}
  if (aV&&mV&&Math.abs(aV-mV)/mV<.1) return {text:'Same Voltage',color:'77,158,255',bg:'rgba(77,158,255,0.1)',icon:'='}
  return {text:'Alternative',color:'122,143,168',bg:'rgba(122,143,168,0.1)',icon:'◇'}
}

// ─── PRICING COMPONENTS ───────────────────────────────────────────────────────
function PricingTable({ pricing }) {
  if (!pricing?.qty1) return null
  const rows = [
    {qty:'1 unit',   price:pricing.qty1},
    {qty:'10 units', price:pricing.qty10},
    {qty:'100 units',price:pricing.qty100},
  ].filter(r=>r.price)
  return (
    <div style={{ background:'var(--bg)',border:'1px solid var(--border)',borderRadius:10,overflow:'hidden' }}>
      <div style={{ padding:'7px 14px',borderBottom:'1px solid var(--border)',
        display:'flex',alignItems:'center',gap:6,background:'var(--bg2)' }}>
        <span style={{ color:'var(--amber)',display:'flex' }}><IcoTag/></span>
        <span style={{ fontSize:9,fontWeight:700,fontFamily:'var(--mono)',
          color:'var(--text2)',textTransform:'uppercase',letterSpacing:'.08em' }}>
          Distributor Pricing
        </span>
        {pricing.seller&&<span style={{ marginLeft:'auto',fontSize:10,color:'var(--text3)',fontFamily:'var(--mono)' }}>via {pricing.seller}</span>}
      </div>
      <div style={{ display:'flex' }}>
        {rows.map((r,i)=>(
          <div key={i} style={{ flex:1,padding:'12px 14px',textAlign:'center',
            borderRight:i<rows.length-1?'1px solid var(--border)':'none' }}>
            <div style={{ fontSize:9,fontWeight:600,fontFamily:'var(--mono)',
              color:'var(--text3)',textTransform:'uppercase',letterSpacing:'.06em',marginBottom:5 }}>{r.qty}</div>
            <div style={{ fontSize:19,fontWeight:800,fontFamily:'var(--mono)',
              color:'var(--amber)',letterSpacing:'-.01em' }}>{r.price}</div>
            <div style={{ fontSize:9,color:'var(--text3)',marginTop:2 }}>{pricing.currency||'USD'}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PricingMini({ pricing, loading }) {
  if (loading) return <span style={{ fontSize:11,color:'var(--text3)',fontStyle:'italic' }}>fetching…</span>
  if (!pricing?.qty1) return <span style={{ fontSize:11,color:'var(--text3)',fontStyle:'italic' }}>Price N/A</span>
  return (
    <div>
      <div style={{ fontSize:18,fontWeight:800,fontFamily:'var(--mono)',color:'var(--amber)',lineHeight:1 }}>
        {pricing.qty1}
      </div>
      <div style={{ fontSize:9,color:'var(--text3)',fontFamily:'var(--mono)',marginTop:2 }}>
        per unit · {pricing.qty100&&pricing.qty100!==pricing.qty1?`${pricing.qty100} @100+`:''}
      </div>
    </div>
  )
}

// ─── SPEC CHIP ────────────────────────────────────────────────────────────────
function SpecChip({ spec }) {
  const rgb = spec.color
  return (
    <div style={{ display:'flex',alignItems:'center',gap:6,
      background:`rgba(${rgb},0.08)`,border:`1px solid rgba(${rgb},0.2)`,
      borderRadius:8,padding:'7px 11px',minWidth:0 }}>
      <span style={{ fontSize:11,opacity:.6,flexShrink:0 }}>{spec.icon}</span>
      <div style={{ minWidth:0 }}>
        <div style={{ fontSize:9,fontWeight:700,fontFamily:'var(--mono)',
          color:`rgb(${rgb})`,opacity:.7,textTransform:'uppercase',letterSpacing:'.08em',marginBottom:2 }}>
          {spec.label}
        </div>
        <div style={{ fontSize:13,fontWeight:700,fontFamily:'var(--mono)',
          color:`rgb(${rgb})`,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>
          {spec.value}
        </div>
      </div>
    </div>
  )
}

function SpecGrid({ specs }) {
  const ordered = getOrderedSpecs(specs)
  if (!ordered.length) return (
    <p style={{ fontSize:12,color:'var(--text3)',fontStyle:'italic' }}>No detailed specifications available.</p>
  )
  return (
    <div>
      <div style={{ fontSize:9,fontWeight:700,fontFamily:'var(--mono)',
        color:'var(--text3)',textTransform:'uppercase',letterSpacing:'.1em',marginBottom:10 }}>
        Specifications
      </div>
      <div style={{ display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(150px,1fr))',gap:8 }}>
        {ordered.map(s=><SpecChip key={s.key} spec={s}/>)}
      </div>
    </div>
  )
}

// ─── OVERVIEW CARDS ───────────────────────────────────────────────────────────
function CompCard({ alt, mainSpecs, rank, onNavigate, pricing, pricingLoading }) {
  const lbl    = smartLabel(alt, mainSpecs)
  const isBest = rank === 0
  const [hov, setHov] = useState(false)
  const altSpecs = getOrderedSpecs(altToSpecs(alt))

  return (
    <div onMouseEnter={()=>setHov(true)} onMouseLeave={()=>setHov(false)}
      onClick={()=>onNavigate(alt.name)}
      style={{ position:'relative',borderRadius:12,minHeight:290,
        border:`1.5px solid ${isBest?'var(--amber)':hov?'var(--border2)':'var(--border)'}`,
        background:isBest?'linear-gradient(145deg,rgba(232,160,32,0.06),var(--bg3))':hov?'var(--bg3)':'var(--bg2)',
        padding:'16px',display:'flex',flexDirection:'column',gap:10,cursor:'pointer',
        transition:'all 0.2s ease',
        boxShadow:isBest?'0 0 30px rgba(232,160,32,0.08)':hov?'0 8px 24px rgba(0,0,0,0.4)':'none' }}>

      {isBest&&(
        <div style={{ position:'absolute',top:-1,right:12,
          background:'linear-gradient(90deg,var(--amber),var(--amber2))',
          color:'#000',fontSize:9,fontWeight:800,letterSpacing:'.08em',
          padding:'3px 12px',borderRadius:'0 0 8px 8px',
          display:'flex',alignItems:'center',gap:4 }}>
          <IcoStar/> TOP PICK
        </div>
      )}

      <span style={{ alignSelf:'flex-start',fontSize:9,fontWeight:700,fontFamily:'var(--mono)',
        padding:'2px 8px',borderRadius:20,color:`rgb(${lbl.color})`,background:lbl.bg,
        letterSpacing:'.05em',textTransform:'uppercase' }}>
        {lbl.icon} {lbl.text}
      </span>

      <div style={{ fontSize:17,fontWeight:700,fontFamily:'var(--mono)',
        color:isBest?'var(--amber)':'var(--text)',letterSpacing:'-.01em' }}>
        {alt.name}
      </div>

      <div style={{ display:'flex',flexWrap:'wrap',gap:5 }}>
        {altSpecs.slice(0,4).map(s=>(
          <div key={s.key} style={{ display:'flex',alignItems:'center',gap:4,
            padding:'4px 8px',background:`rgba(${s.color},0.08)`,
            border:`1px solid rgba(${s.color},0.18)`,borderRadius:6,maxWidth:'100%' }}>
            <span style={{ fontSize:9,flexShrink:0 }}>{s.icon}</span>
            <div style={{ minWidth:0 }}>
              <div style={{ fontSize:8,fontFamily:'var(--mono)',color:`rgb(${s.color})`,
                opacity:.65,textTransform:'uppercase',letterSpacing:'.07em',whiteSpace:'nowrap' }}>
                {s.label}
              </div>
              <div style={{ fontSize:11,fontWeight:700,fontFamily:'var(--mono)',
                color:`rgb(${s.color})`,whiteSpace:'nowrap',overflow:'hidden',
                textOverflow:'ellipsis',maxWidth:110 }}>
                {s.value}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ borderTop:'1px solid var(--border)',paddingTop:10,marginTop:'auto' }}>
        <PricingMini pricing={pricing} loading={pricingLoading}/>
      </div>

      <div style={{ fontSize:11,color:'var(--text2)',lineHeight:1.55,
        overflow:'hidden',display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical' }}>
        {alt.reason}
      </div>

      <div style={{ display:'flex',alignItems:'center',gap:5,borderTop:'1px solid var(--border)',
        paddingTop:10,fontSize:11,fontWeight:600,
        color:isBest?'var(--amber)':'var(--text2)',opacity:hov?1:.6,transition:'opacity 0.15s' }}>
        View component <IcoArrow/>
      </div>
    </div>
  )
}

// ─── DETAILED COMPARISON TABLE ────────────────────────────────────────────────
function DetailedComparison({ mainResult, alts, pricingMap, pricingLoading, onNavigate }) {
  // Build column list: main + alts (max 4 alts)
  const cols = [
    { ...mainResult, isMain: true, pricing: mainResult.pricing || {} },
    ...alts.slice(0, 4).map(a => ({
      ...a,
      specs: altToSpecs(a),
      isMain: false,
      pricing: pricingMap[a.name] || {}
    }))
  ]

  // Which spec rows to show: union of all non-empty specs across all cols
  const activeRows = DISPLAY_ORDER.filter(key =>
    cols.some(c => c.specs?.[key] || c[key])
  )

  const mainSpecs = mainResult.specs || {}

  function cellValue(col, key) {
    return col.specs?.[key] || col[key] || ''
  }

  function CellContent({ col, rowKey }) {
    const val = cellValue(col, rowKey)
    const mainVal = cellValue(cols[0], rowKey)
    const schema = SPEC_SCHEMA[rowKey]
    if (!val) return <span style={{ color:'var(--text3)',fontSize:12 }}>—</span>

    const isSame = !col.isMain && val === mainVal
    const rgb = schema?.color || '148,163,184'

    return (
      <div style={{ display:'flex',flexDirection:'column',gap:2 }}>
        <span style={{ fontSize:12,fontWeight:700,fontFamily:'var(--mono)',
          color: col.isMain ? `rgb(${rgb})` : isSame ? 'var(--text3)' : `rgb(${rgb})`,
          background: col.isMain ? `rgba(${rgb},0.1)` : isSame ? 'transparent' : `rgba(${rgb},0.06)`,
          padding: col.isMain ? '2px 6px' : isSame ? '0' : '2px 6px',
          borderRadius:5, display:'inline-block' }}>
          {val}
        </span>
        {!col.isMain && isSame && (
          <span style={{ fontSize:8,color:'var(--text3)',fontFamily:'var(--mono)' }}>= same</span>
        )}
      </div>
    )
  }

  const colWidth = `${Math.max(140, Math.floor(600 / cols.length))}px`

  return (
    <div style={{ overflowX:'auto',borderRadius:10,border:'1px solid var(--border)' }}>
      <table style={{ borderCollapse:'collapse',width:'100%',minWidth:600 }}>
        <thead>
          <tr>
            {/* Row label header */}
            <th style={{ ...TH_STYLE, width:130, position:'sticky',left:0,
              background:'var(--bg)',zIndex:2, textAlign:'left' }}>
              Parameter
            </th>
            {cols.map((col, i) => (
              <th key={i} style={{ ...TH_STYLE, width:colWidth, minWidth:120,
                background: col.isMain ? 'rgba(232,160,32,0.08)' : 'var(--bg)',
                borderLeft:`2px solid ${col.isMain?'var(--amber)':'var(--border)'}` }}>
                <div style={{ display:'flex',flexDirection:'column',gap:3,alignItems:'center' }}>
                  {col.isMain && (
                    <span style={{ fontSize:8,color:'var(--amber)',fontWeight:800,
                      letterSpacing:'.06em',textTransform:'uppercase' }}>● SELECTED</span>
                  )}
                  {!col.isMain && i===1 && (
                    <span style={{ fontSize:8,color:'var(--amber)',fontWeight:800,
                      letterSpacing:'.06em',textTransform:'uppercase',
                      display:'flex',alignItems:'center',gap:3 }}>
                      <IcoStar/> TOP PICK
                    </span>
                  )}
                  <button onClick={()=>!col.isMain&&onNavigate(col.name)}
                    style={{ background:'none',border:'none',cursor:col.isMain?'default':'pointer',
                      fontFamily:'var(--mono)',fontSize:13,fontWeight:700,
                      color:col.isMain?'var(--amber)':'var(--text)',letterSpacing:'-.01em',
                      padding:0 }}>
                    {col.name}
                  </button>
                  {!col.isMain && (
                    <span style={{ fontSize:9,color:'var(--text3)' }}>
                      {smartLabel(col, mainSpecs).icon} {smartLabel(col, mainSpecs).text}
                    </span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {/* ── Spec rows ── */}
          {activeRows.map((key, ri) => {
            const schema = SPEC_SCHEMA[key]
            const rgb = schema?.color || '148,163,184'
            return (
              <tr key={key} style={{ background: ri%2===0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                <td style={{ ...TD_STYLE, position:'sticky', left:0,
                  background: ri%2===0 ? 'var(--bg2)' : 'var(--bg3)',
                  zIndex:1 }}>
                  <div style={{ display:'flex',alignItems:'center',gap:6 }}>
                    <span style={{ fontSize:11,flexShrink:0 }}>{schema?.icon}</span>
                    <span style={{ fontSize:11,fontWeight:600,fontFamily:'var(--mono)',
                      color:`rgb(${rgb})`,opacity:.8 }}>{schema?.label||key}</span>
                  </div>
                </td>
                {cols.map((col, ci) => (
                  <td key={ci} style={{ ...TD_STYLE, textAlign:'center',
                    borderLeft:`2px solid ${col.isMain?'rgba(232,160,32,0.2)':'var(--border)'}`,
                    background: col.isMain
                      ? ri%2===0 ? 'rgba(232,160,32,0.03)' : 'rgba(232,160,32,0.05)'
                      : ri%2===0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    <CellContent col={col} rowKey={key}/>
                  </td>
                ))}
              </tr>
            )
          })}

          {/* ── Pricing section header ── */}
          <tr>
            <td colSpan={cols.length+1} style={{ padding:'0',
              borderTop:'2px solid var(--border)',
              borderBottom:'1px solid var(--border)' }}>
              <div style={{ padding:'8px 16px',background:'var(--bg)',
                fontSize:9,fontWeight:800,fontFamily:'var(--mono)',
                color:'var(--amber)',textTransform:'uppercase',letterSpacing:'.1em',
                display:'flex',alignItems:'center',gap:6 }}>
                <IcoTag/> PRICING
              </div>
            </td>
          </tr>

          {/* Price @ 1 */}
          {[
            { label:'Price / 1 unit',   key:'qty1'  },
            { label:'Price / 10 units', key:'qty10' },
            { label:'Price / 100 units',key:'qty100'},
          ].map((row, ri) => (
            <tr key={row.key} style={{ background: ri%2===0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
              <td style={{ ...TD_STYLE, position:'sticky',left:0,zIndex:1,
                background: ri%2===0 ? 'var(--bg2)' : 'var(--bg3)' }}>
                <span style={{ fontSize:11,fontWeight:600,fontFamily:'var(--mono)',
                  color:'var(--amber)',opacity:.8 }}>{row.label}</span>
              </td>
              {cols.map((col, ci) => {
                const p = col.isMain ? col.pricing : (pricingMap[col.name] || {})
                const val = p[row.key]
                const isLoading = !col.isMain && pricingLoading
                return (
                  <td key={ci} style={{ ...TD_STYLE, textAlign:'center',
                    borderLeft:`2px solid ${col.isMain?'rgba(232,160,32,0.2)':'var(--border)'}`,
                    background: col.isMain
                      ? ri%2===0 ? 'rgba(232,160,32,0.03)' : 'rgba(232,160,32,0.05)'
                      : ri%2===0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    {isLoading
                      ? <span style={{ fontSize:10,color:'var(--text3)',fontStyle:'italic' }}>…</span>
                      : val
                        ? <span style={{ fontSize:13,fontWeight:800,fontFamily:'var(--mono)',
                            color:'var(--amber)' }}>{val}</span>
                        : <span style={{ color:'var(--text3)',fontSize:12 }}>—</span>
                    }
                  </td>
                )
              })}
            </tr>
          ))}

          {/* Datasheet row */}
          <tr>
            <td style={{ ...TD_STYLE, position:'sticky',left:0,zIndex:1,background:'var(--bg2)' }}>
              <span style={{ fontSize:11,fontWeight:600,fontFamily:'var(--mono)',
                color:'var(--blue)',opacity:.8 }}>Datasheet</span>
            </td>
            {cols.map((col, ci) => (
              <td key={ci} style={{ ...TD_STYLE, textAlign:'center',
                borderLeft:`2px solid ${col.isMain?'rgba(232,160,32,0.2)':'var(--border)'}`,
                background: col.isMain ? 'rgba(232,160,32,0.03)' : 'transparent' }}>
                {col.datasheet_url
                  ? <a href={col.datasheet_url} target="_blank" rel="noopener noreferrer"
                      onClick={e=>e.stopPropagation()}
                      style={{ fontSize:10,color:'var(--blue)',textDecoration:'none',
                        display:'inline-flex',alignItems:'center',gap:4,
                        padding:'3px 8px',background:'var(--blue-dim)',borderRadius:6 }}>
                      <IcoLink/> PDF
                    </a>
                  : <span style={{ color:'var(--text3)',fontSize:12 }}>—</span>
                }
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  )
}

const TH_STYLE = {
  padding:'12px 14px', borderBottom:'2px solid var(--border)',
  fontSize:9, fontWeight:700, fontFamily:'var(--mono)',
  color:'var(--text2)', textTransform:'uppercase', letterSpacing:'.07em',
  textAlign:'center', whiteSpace:'nowrap'
}
const TD_STYLE = {
  padding:'10px 14px', borderBottom:'1px solid var(--border)',
  verticalAlign:'middle'
}

// ─── COMPARISON SECTION (with tabs) ──────────────────────────────────────────
function ComparisonSection({ mainResult, alts, loading, onNavigate, pricingMap, pricingLoading }) {
  const [tab, setTab] = useState('overview')
  const mainSpecs = mainResult?.specs || {}

  if (loading) return (
    <div style={D.card}>
      <SecHead title="Compare with Similar Components" sub="Fetching alternatives…"/>
      <div style={{ display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(200px,1fr))',gap:12 }}>
        {[0,1,2].map(i=>(
          <div key={i} style={{ height:240,borderRadius:12,border:'1px solid var(--border)',
            background:`linear-gradient(90deg,var(--bg2) 25%,var(--bg3) 50%,var(--bg2) 75%)`,
            backgroundSize:'200% 100%',animation:`shimmer 1.4s ${i*.15}s infinite`}}/>
        ))}
      </div>
    </div>
  )

  if (!alts?.length) return (
    <div style={D.card}>
      <SecHead title="Compare with Similar Components" sub="No alternatives found for this component type."/>
    </div>
  )

  return (
    <div style={D.card} className="fade-up">
      {/* Header + tabs */}
      <div style={{ display:'flex',alignItems:'flex-start',justifyContent:'space-between',
        marginBottom:18,flexWrap:'wrap',gap:12 }}>
        <SecHead title="Compare with Similar Components"
          sub={`${alts.length} alternatives · ${tab==='overview'?'click card to navigate':'full parameter comparison'}`}/>
        {/* Tab switcher */}
        <div style={{ display:'flex',background:'var(--bg)',border:'1px solid var(--border)',
          borderRadius:8,padding:3,gap:2,flexShrink:0 }}>
          {[
            { id:'overview', label:'Overview', icon:<IcoCards/> },
            { id:'detailed', label:'Detailed',  icon:<IcoTable/>},
          ].map(t=>(
            <button key={t.id} onClick={()=>setTab(t.id)}
              style={{ display:'flex',alignItems:'center',gap:6,padding:'6px 14px',
                borderRadius:6,border:'none',cursor:'pointer',fontSize:12,fontWeight:600,
                fontFamily:'var(--sans)',transition:'all 0.15s',
                background: tab===t.id ? 'var(--amber)' : 'transparent',
                color: tab===t.id ? '#000' : 'var(--text2)' }}>
              <span style={{ display:'flex',opacity:.8 }}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Overview tab */}
      {tab==='overview' && (
        <div style={{ display:'grid',gridTemplateColumns:'repeat(auto-fill,minmax(220px,1fr))',gap:12 }}>
          {alts.map((alt,i)=>(
            <CompCard key={alt.name} alt={alt} mainSpecs={mainSpecs}
              rank={i} onNavigate={onNavigate}
              pricing={pricingMap[alt.name]}
              pricingLoading={pricingLoading&&!pricingMap[alt.name]}/>
          ))}
        </div>
      )}

      {/* Detailed tab */}
      {tab==='detailed' && (
        <DetailedComparison
          mainResult={mainResult} alts={alts}
          pricingMap={pricingMap} pricingLoading={pricingLoading}
          onNavigate={onNavigate}/>
      )}
    </div>
  )
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────
function SecHead({ title, sub }) {
  return (
    <div style={{ display:'flex',alignItems:'flex-start',gap:10 }}>
      <span style={{ color:'var(--amber)',display:'flex',marginTop:2 }}><IcoScale/></span>
      <div>
        <div style={{ fontSize:14,fontWeight:700,color:'var(--text)',letterSpacing:'-.01em' }}>{title}</div>
        <div style={{ fontSize:11,color:'var(--text2)',marginTop:2,fontFamily:'var(--mono)' }}>{sub}</div>
      </div>
    </div>
  )
}

function SourceBadge({ source }) {
  const MAP = {
    cache:  ['⚡ cached','232,160,32'], dataset:['📦 dataset','52,211,153'],
    live:   ['🌐 scraped','77,158,255'], nexar:  ['🔌 nexar','167,139,250'],
    mouser: ['🛒 mouser','232,160,32'], ai:     ['🤖 ai gen','248,113,113'],
  }
  const [label,rgb] = MAP[source]||MAP.live
  return (
    <span style={{ fontSize:10,fontWeight:700,fontFamily:'var(--mono)',
      padding:'2px 9px',borderRadius:20,letterSpacing:'.04em',
      color:`rgb(${rgb})`,background:`rgba(${rgb},0.12)`,border:`1px solid rgba(${rgb},0.3)` }}>
      {label}
    </span>
  )
}

function Breadcrumb({ history, onBack }) {
  if (!history.length) return null
  return (
    <div style={{ display:'flex',alignItems:'center',gap:8,padding:'8px 14px',
      background:'var(--bg2)',border:'1px solid var(--border)',borderRadius:10 }}>
      <button onClick={onBack} style={{ display:'flex',alignItems:'center',gap:6,
        background:'var(--amber-dim)',border:'1px solid rgba(232,160,32,0.3)',
        borderRadius:7,padding:'5px 12px',color:'var(--amber)',fontSize:12,
        fontWeight:600,cursor:'pointer',fontFamily:'var(--sans)' }}>
        <IcoBack/> Back
      </button>
      <div style={{ display:'flex',alignItems:'center',gap:4,overflow:'hidden',flex:1 }}>
        {history.map((h,i)=>(
          <span key={i} style={{ display:'flex',alignItems:'center',gap:4 }}>
            <span style={{ fontSize:11,fontFamily:'var(--mono)',color:'var(--text2)',
              maxWidth:100,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap' }}>
              {h.result.name}
            </span>
            <span style={{ color:'var(--border2)' }}>›</span>
          </span>
        ))}
        <span style={{ fontSize:11,fontFamily:'var(--mono)',color:'var(--amber)' }}>current</span>
      </div>
    </div>
  )
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
const SUGGESTIONS = ['LM7805','NE555','BC547','IRF540N','LM741','1N4007']

export default function App() {
  const [query,setQuery]         = useState('')
  const [result,setResult]       = useState(null)
  const [alts,setAlts]           = useState(null)
  const [status,setStatus]       = useState('idle')
  const [altStatus,setAltSt]     = useState('idle')
  const [error,setError]         = useState('')
  const [history,setHistory]     = useState([])
  const [pricingMap,setPricingMap] = useState({})    // { name: pricing }
  const [pricingLoading,setPricingLoading] = useState(false)

  const doSearch = useCallback(async (name) => {
    const nm=(name||'').trim(); if(!nm) return
    setQuery(nm); setStatus('loading'); setResult(null)
    setAlts(null); setAltSt('idle'); setError('')
    setPricingMap({}); setPricingLoading(false)
    try {
      const data = await fetchComponent(nm)
      setResult(data); setStatus('success')
      setAltSt('loading')
      const altData = await fetchAlternatives(data.name)
      setAlts(altData); setAltSt('done')
      // Fetch pricing for all alternatives in parallel
      if (altData.length) {
        setPricingLoading(true)
        const names = altData.map(a=>a.name)
        const results = await Promise.all(names.map(n=>fetchPricing(n)))
        const map = {}
        names.forEach((n,i)=>{ map[n] = results[i] })
        setPricingMap(map)
        setPricingLoading(false)
      }
    } catch(err) { setError(err.message); setStatus('error') }
  }, [])

  const navigateTo = useCallback((name) => {
    if (result) setHistory(h=>[...h,{result,alts,query,pricingMap}])
    doSearch(name)
  }, [result,alts,query,pricingMap,doSearch])

  const goBack = useCallback(() => {
    const prev=history[history.length-1]; if(!prev) return
    setHistory(h=>h.slice(0,-1)); setQuery(prev.query)
    setResult(prev.result); setAlts(prev.alts)
    setPricingMap(prev.pricingMap||{})
    setStatus('success'); setAltSt(prev.alts?'done':'idle')
  }, [history])

  return (
    <div style={{ minHeight:'100vh',fontFamily:'var(--sans)' }}>
      {/* Header */}
      <header style={{ position:'sticky',top:0,zIndex:100,
        background:'rgba(8,12,18,0.92)',backdropFilter:'blur(16px)',
        borderBottom:'1px solid var(--border)' }}>
        <div style={{ maxWidth:1100,margin:'0 auto',padding:'12px 24px',
          display:'flex',alignItems:'center',justifyContent:'space-between' }}>
          <div style={{ display:'flex',alignItems:'center',gap:10 }}>
            <span style={{ color:'var(--amber)',display:'flex',
              filter:'drop-shadow(0 0 6px rgba(232,160,32,0.4))' }}><IcoChip/></span>
            <div>
              <div style={{ fontWeight:700,fontSize:14,color:'var(--text)',letterSpacing:'-.01em' }}>
                Smart Component System
              </div>
              <div style={{ fontSize:9,color:'var(--text3)',fontFamily:'var(--mono)',
                marginTop:1,letterSpacing:'.04em' }}>
                FULL SPEC COMPARISON · LIVE PRICING · AI-POWERED
              </div>
            </div>
          </div>
          <div style={{ display:'flex',gap:5 }}>
            {['Mouser','Nexar','OpenRouter'].map(s=>(
              <span key={s} style={{ fontSize:8,fontWeight:700,fontFamily:'var(--mono)',
                color:'var(--teal)',background:'var(--teal-dim)',padding:'2px 7px',
                borderRadius:20,letterSpacing:'.05em',
                border:'1px solid rgba(0,184,160,0.2)',textTransform:'uppercase' }}>{s}</span>
            ))}
          </div>
        </div>
      </header>

      <main style={{ maxWidth:1100,margin:'0 auto',padding:'24px',
        display:'flex',flexDirection:'column',gap:14 }}>

        {/* Search */}
        <div style={D.card}>
          <div style={{ fontSize:9,fontWeight:700,fontFamily:'var(--mono)',
            color:'var(--text3)',textTransform:'uppercase',letterSpacing:'.1em',marginBottom:10 }}>
            Component Search
          </div>
          <div style={{ display:'flex',gap:10 }}>
            <input style={{ flex:1,height:48,background:'var(--bg)',
              border:'1.5px solid var(--border)',borderRadius:9,padding:'0 16px',
              fontSize:14,fontFamily:'var(--sans)',color:'var(--text)',outline:'none',
              transition:'border-color 0.2s' }}
              onFocus={e=>e.target.style.borderColor='var(--amber)'}
              onBlur={e=>e.target.style.borderColor='var(--border)'}
              type="text" value={query}
              placeholder="Enter part number — e.g. LM7805, IRF540N, BC547…"
              onChange={e=>setQuery(e.target.value)}
              onKeyDown={e=>e.key==='Enter'&&doSearch(query)}
              disabled={status==='loading'} autoFocus/>
            <button onClick={()=>doSearch(query)} disabled={status==='loading'}
              style={{ height:48,padding:'0 24px',
                background:status==='loading'?'rgba(232,160,32,0.2)':'linear-gradient(135deg,var(--amber),var(--amber2))',
                color:'#000',border:'none',borderRadius:9,fontSize:13,fontWeight:700,
                cursor:status==='loading'?'not-allowed':'pointer',
                display:'flex',alignItems:'center',gap:7,fontFamily:'var(--sans)',
                boxShadow:status==='loading'?'none':'0 4px 16px rgba(232,160,32,0.25)' }}>
              {status==='loading'
                ?<span style={{ width:18,height:18,border:'2px solid rgba(0,0,0,0.3)',
                    borderTopColor:'#000',borderRadius:'50%',display:'inline-block',
                    animation:'spin 0.7s linear infinite' }}/>
                :<><IcoSearch/><span>Search</span></>}
            </button>
          </div>
          <div style={{ display:'flex',flexWrap:'wrap',gap:6,marginTop:12 }}>
            {SUGGESTIONS.map(sg=>(
              <button key={sg} onClick={()=>doSearch(sg)} disabled={status==='loading'}
                style={{ background:'var(--bg)',border:'1px solid var(--border)',
                  borderRadius:20,padding:'4px 13px',fontSize:11,fontWeight:600,
                  fontFamily:'var(--mono)',color:'var(--text2)',cursor:'pointer',transition:'all 0.15s' }}
                onMouseEnter={e=>{e.target.style.borderColor='var(--amber)';e.target.style.color='var(--amber)'}}
                onMouseLeave={e=>{e.target.style.borderColor='var(--border)';e.target.style.color='var(--text2)'}}>
                {sg}
              </button>
            ))}
          </div>
        </div>

        <Breadcrumb history={history} onBack={goBack}/>

        {/* Main result */}
        {status==='success'&&result&&(
          <div style={D.card} className="fade-up">
            <div style={{ display:'flex',alignItems:'center',gap:8,marginBottom:16 }}>
              <span style={{ width:7,height:7,borderRadius:'50%',flexShrink:0,
                background:'var(--teal)',boxShadow:'0 0 8px var(--teal)',display:'inline-block' }}/>
              <span style={{ fontSize:10,fontWeight:700,fontFamily:'var(--mono)',
                color:'var(--teal)',textTransform:'uppercase',letterSpacing:'.09em' }}>
                Selected Component
              </span>
              <div style={{ marginLeft:'auto',display:'flex',gap:6 }}>
                <SourceBadge source={result.source}/>
              </div>
            </div>

            <div style={{ display:'grid',gridTemplateColumns:'1fr auto',gap:24,
              alignItems:'start',marginBottom:16 }}>
              <div>
                <div style={{ fontSize:28,fontWeight:800,fontFamily:'var(--mono)',
                  color:'var(--amber)',letterSpacing:'-.02em',lineHeight:1,
                  marginBottom:8,filter:'drop-shadow(0 0 12px rgba(232,160,32,0.2))' }}>
                  {result.name}
                </div>
                <p style={{ fontSize:13,lineHeight:1.75,color:'var(--text2)',maxWidth:620 }}>
                  {result.description}
                </p>
              </div>
              {result.pricing?.qty1&&(
                <div style={{ background:'var(--bg)',border:'1px solid rgba(232,160,32,0.25)',
                  borderRadius:12,padding:'16px 20px',minWidth:170,flexShrink:0,textAlign:'center' }}>
                  <div style={{ fontSize:9,fontWeight:700,fontFamily:'var(--mono)',
                    color:'var(--text3)',textTransform:'uppercase',letterSpacing:'.09em',marginBottom:8 }}>
                    Unit Price
                  </div>
                  <div style={{ fontSize:28,fontWeight:800,fontFamily:'var(--mono)',
                    color:'var(--amber)',letterSpacing:'-.02em',lineHeight:1 }}>
                    {result.pricing.qty1}
                  </div>
                  <div style={{ fontSize:9,color:'var(--text3)',marginTop:4,fontFamily:'var(--mono)' }}>
                    {result.pricing.currency||'USD'}
                  </div>
                  {result.pricing.qty100&&result.pricing.qty100!==result.pricing.qty1&&(
                    <div style={{ marginTop:8,paddingTop:8,borderTop:'1px solid var(--border)',
                      fontSize:11,color:'var(--teal)',fontFamily:'var(--mono)' }}>
                      {result.pricing.qty100} at 100+
                    </div>
                  )}
                </div>
              )}
            </div>

            <SpecGrid specs={result.specs}/>

            {result.pricing?.qty1&&(
              <div style={{ marginTop:16 }}><PricingTable pricing={result.pricing}/></div>
            )}

            <div style={{ display:'flex',alignItems:'center',justifyContent:'space-between',
              borderTop:'1px solid var(--border)',paddingTop:14,marginTop:16 }}>
              {result.datasheet_url&&(
                <a href={result.datasheet_url} target="_blank" rel="noopener noreferrer"
                  style={{ display:'inline-flex',alignItems:'center',gap:6,fontSize:12,
                    fontWeight:600,color:'var(--amber)',background:'var(--amber-dim)',
                    padding:'7px 14px',borderRadius:8,textDecoration:'none',
                    border:'1px solid rgba(232,160,32,0.3)' }}>
                  <IcoLink/> View Datasheet
                </a>
              )}
              <span style={{ fontSize:9,color:'var(--text3)',fontFamily:'var(--mono)',
                textTransform:'uppercase',letterSpacing:'.06em' }}>source: {result.source}</span>
            </div>
          </div>
        )}

        {/* Comparison section */}
        {status==='success'&&result&&(
          <ComparisonSection
            mainResult={result} alts={alts}
            loading={altStatus==='loading'} onNavigate={navigateTo}
            pricingMap={pricingMap} pricingLoading={pricingLoading}/>
        )}

        {/* Error */}
        {status==='error'&&(
          <div style={{ ...D.card,borderColor:'rgba(248,113,113,0.3)',
            background:'rgba(248,113,113,0.04)' }} className="fade-up">
            <div style={{ fontSize:13,fontWeight:700,color:'var(--rose)',marginBottom:6 }}>
              Component Not Found
            </div>
            <p style={{ fontSize:13,color:'var(--text2)',marginBottom:8 }}>{error}</p>
            <p style={{ fontSize:11,color:'var(--text3)',fontFamily:'var(--mono)' }}>
              Try: "LM7805" · "NE555" · "BC547" · "IRF540N"
            </p>
          </div>
        )}

        {/* Idle */}
        {status==='idle'&&(
          <div style={{ display:'flex',flexDirection:'column',alignItems:'center',
            gap:14,padding:'64px 20px',opacity:.35 }}>
            <span style={{ color:'var(--amber)',filter:'drop-shadow(0 0 10px rgba(232,160,32,0.3))' }}>
              <IcoChip/>
            </span>
            <p style={{ fontSize:12,color:'var(--text2)',fontFamily:'var(--mono)',letterSpacing:'.04em' }}>
              search a component to begin
            </p>
          </div>
        )}
      </main>
    </div>
  )
}

const D = {
  card:{ background:'var(--bg2)',border:'1px solid var(--border)',borderRadius:13,padding:'22px' }
}