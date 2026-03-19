import type { FC } from 'react'

interface Props {
    data: Record<string, unknown>
}

function fmt(n: unknown, decimals = 0): string {
    if (n === null || n === undefined || n === '') return '—'
    const num = Number(n)
    if (isNaN(num)) return String(n)
    if (decimals === 0) return num.toLocaleString('en-IN', { maximumFractionDigits: 0 })
    return num.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function pct(n: unknown): string {
    if (n === null || n === undefined) return '—'
    return `${fmt(Number(n), 1)}%`
}

function multiple(n: unknown): string {
    if (n === null || n === undefined) return '—'
    return `${fmt(Number(n), 2)}x`
}

function dscrColor(val: number): string {
    if (val >= 1.4) return '#00cc66'
    if (val >= 1.0) return '#ffa500'
    return '#cc3333'
}

const LBOResultsView: FC<Props> = ({ data }) => {
    const su = (data.sources_uses as Record<string, number>) || {}
    const opModel = (data.operating_model as Record<string, number[]>) || {}
    const debtSchedule = (data.debt_schedule as Record<string, unknown>[]) || []
    const dscrByYear = (data.dscr_by_year as Record<string, number>) || {}
    const warnings = (data.warnings as string[]) || []
    const sensitivity = (data.irr_sensitivity as Record<string, Record<string, number | null>>) || {}

    const years = debtSchedule.map(d => d.year as number)

    const headerStyle: React.CSSProperties = {
        padding: '8px 18px', background: '#0a0a0a', borderBottom: '1px solid #222',
        fontSize: 10, color: '#555', fontWeight: 700, letterSpacing: '0.1em',
    }
    const sectionStyle: React.CSSProperties = {
        border: '1px solid #222', borderRadius: 3, marginBottom: 16, overflow: 'hidden',
    }
    const rowStyle: React.CSSProperties = {
        display: 'grid', borderBottom: '1px solid #111',
    }
    const labelStyle: React.CSSProperties = {
        padding: '8px 18px', fontSize: 11, color: '#888', fontWeight: 600,
    }
    const valueStyle: React.CSSProperties = {
        padding: '8px 18px', fontSize: 11, color: '#fff', fontWeight: 700, textAlign: 'right' as const,
    }
    const greenValue: React.CSSProperties = { ...valueStyle, color: '#00cc66' }
    const redValue: React.CSSProperties = { ...valueStyle, color: '#cc3333' }

    return (
        <div className="animate-fade-in" style={{ marginTop: 24 }}>
            {/* ---- Key Returns ---- */}
            <div style={{ marginBottom: 16, border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                <div style={headerStyle}>RETURNS SUMMARY</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', borderBottom: '1px solid #111' }}>
                    {[
                        { label: 'IRR', value: pct(data.irr_pct), style: (Number(data.irr_pct) >= 20 ? greenValue : Number(data.irr_pct) >= 10 ? valueStyle : redValue) },
                        { label: 'MOIC', value: multiple(data.moic), style: (Number(data.moic) >= 2.0 ? greenValue : Number(data.moic) >= 1.5 ? valueStyle : redValue) },
                        { label: 'MIN DSCR', value: multiple(data.dscr_minimum), style: (Number(data.dscr_minimum) >= 1.4 ? greenValue : Number(data.dscr_minimum) >= 1.0 ? valueStyle : redValue) },
                        { label: 'HOLD PERIOD', value: `${years.length}y`, style: valueStyle },
                    ].map(({ label, value, style }) => (
                        <div key={label} style={{ padding: '16px 18px', borderRight: '1px solid #111', textAlign: 'center' }}>
                            <div style={{ fontSize: 10, color: '#555', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 6 }}>{label}</div>
                            <div style={{ ...style, padding: 0, textAlign: 'center', fontSize: 22 }}>{value}</div>
                        </div>
                    ))}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)' }}>
                    {[
                        { label: 'ENTRY EV', value: fmt(data.entry_ev) },
                        { label: 'EXIT EV', value: fmt(data.exit_ev) },
                        { label: 'EXIT EQUITY', value: fmt(data.exit_equity) },
                    ].map(({ label, value }) => (
                        <div key={label} style={{ padding: '12px 18px', borderRight: '1px solid #111', textAlign: 'center' }}>
                            <div style={{ fontSize: 9, color: '#555', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 4 }}>{label}</div>
                            <div style={{ fontSize: 14, color: '#aaa', fontWeight: 700 }}>{value}</div>
                        </div>
                    ))}
                </div>
            </div>

            {/* ---- Warnings ---- */}
            {warnings.length > 0 && (
                <div style={{ ...sectionStyle, border: '1px solid rgba(255,165,0,0.3)', marginBottom: 16 }}>
                    <div style={{ ...headerStyle, background: 'rgba(255,165,0,0.08)', color: '#ffa500', borderBottom: '1px solid rgba(255,165,0,0.2)' }}>
                        ⚠ WARNINGS ({warnings.length})
                    </div>
                    {warnings.map((w, i) => (
                        <div key={i} style={{ padding: '8px 18px', fontSize: 11, color: '#ffa500', borderBottom: '1px solid #111' }}>{w}</div>
                    ))}
                </div>
            )}

            {/* ---- Sources & Uses ---- */}
            <div style={sectionStyle}>
                <div style={headerStyle}>SOURCES & USES</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
                    <div style={{ borderRight: '1px solid #222' }}>
                        <div style={{ padding: '6px 18px', fontSize: 9, color: '#444', fontWeight: 700, letterSpacing: '0.1em', borderBottom: '1px solid #111' }}>SOURCES</div>
                        {[
                            { label: 'Equity', value: fmt(su.equity) },
                            { label: 'Senior Debt (TLA + TLB)', value: fmt(su.senior_debt) },
                            { label: 'Mezzanine Debt', value: fmt(su.mezz_debt) },
                        ].map(({ label, value }) => (
                            <div key={label} style={{ ...rowStyle, gridTemplateColumns: '1fr auto', borderBottom: '1px solid #0a0a0a' }}>
                                <div style={labelStyle}>{label}</div>
                                <div style={valueStyle}>{value}</div>
                            </div>
                        ))}
                        <div style={{ ...rowStyle, gridTemplateColumns: '1fr auto', background: '#111' }}>
                            <div style={{ ...labelStyle, color: '#fff', fontWeight: 800 }}>Total Sources</div>
                            <div style={{ ...valueStyle, color: '#00cc66' }}>{fmt(su.total_sources)}</div>
                        </div>
                    </div>
                    <div>
                        <div style={{ padding: '6px 18px', fontSize: 9, color: '#444', fontWeight: 700, letterSpacing: '0.1em', borderBottom: '1px solid #111' }}>USES</div>
                        {[
                            { label: 'Entry EV (Purchase Price)', value: fmt(su.entry_ev) },
                            { label: 'Equity %', value: `${fmt(su.equity_pct, 1)}%` },
                            { label: 'Leverage (x EBITDA)', value: multiple(su.leverage_multiple) },
                        ].map(({ label, value }) => (
                            <div key={label} style={{ ...rowStyle, gridTemplateColumns: '1fr auto', borderBottom: '1px solid #0a0a0a' }}>
                                <div style={labelStyle}>{label}</div>
                                <div style={valueStyle}>{value}</div>
                            </div>
                        ))}
                        <div style={{ ...rowStyle, gridTemplateColumns: '1fr auto', background: '#111' }}>
                            <div style={{ ...labelStyle, color: '#fff', fontWeight: 800 }}>Total Uses</div>
                            <div style={{ ...valueStyle, color: '#00cc66' }}>{fmt(su.total_uses)}</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* ---- Operating Model ---- */}
            {opModel.revenues && opModel.revenues.length > 0 && (
                <div style={sectionStyle}>
                    <div style={headerStyle}>OPERATING MODEL</div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                            <thead>
                                <tr style={{ background: '#0a0a0a' }}>
                                    <th style={{ padding: '8px 18px', textAlign: 'left', color: '#555', fontWeight: 700, fontSize: 9, letterSpacing: '0.1em' }}>METRIC</th>
                                    {years.map(y => (
                                        <th key={y} style={{ padding: '8px 12px', textAlign: 'right', color: '#555', fontWeight: 700, fontSize: 9, letterSpacing: '0.1em' }}>YR {y}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {[
                                    { label: 'Revenue', key: 'revenues' },
                                    { label: 'EBITDA', key: 'ebitda' },
                                    { label: 'EBIT', key: 'ebit' },
                                    { label: 'Unlevered FCF', key: 'ufcf' },
                                ].map(({ label, key }) => (
                                    <tr key={key} style={{ borderBottom: '1px solid #111' }}>
                                        <td style={{ padding: '8px 18px', color: '#888', fontWeight: 600 }}>{label}</td>
                                        {(opModel[key] || []).map((v, i) => (
                                            <td key={i} style={{ padding: '8px 12px', textAlign: 'right', color: v >= 0 ? '#fff' : '#cc3333', fontFamily: "'SF Mono', monospace" }}>{fmt(v)}</td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ---- Debt Schedule with DSCR ---- */}
            {debtSchedule.length > 0 && (
                <div style={sectionStyle}>
                    <div style={headerStyle}>DEBT SCHEDULE & DSCR</div>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                            <thead>
                                <tr style={{ background: '#0a0a0a' }}>
                                    {['Year', 'Opening Debt', 'Cash Interest', 'Mandatory Amort', 'Cash Sweep', 'Closing Debt', 'DSCR'].map(h => (
                                        <th key={h} style={{ padding: '8px 12px', textAlign: h === 'Year' ? 'left' : 'right', color: '#555', fontWeight: 700, fontSize: 9, letterSpacing: '0.1em' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {debtSchedule.map((ds, i) => {
                                    const yr = ds.year as number
                                    const dscr = dscrByYear[yr]
                                    return (
                                        <tr key={i} style={{ borderBottom: '1px solid #111' }}>
                                            <td style={{ padding: '8px 12px', color: '#888', fontWeight: 700 }}>Yr {yr}</td>
                                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#aaa', fontFamily: "'SF Mono', monospace" }}>{fmt(ds.opening_debt)}</td>
                                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#cc3333', fontFamily: "'SF Mono', monospace" }}>{fmt(ds.cash_interest)}</td>
                                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#aaa', fontFamily: "'SF Mono', monospace" }}>{fmt(ds.mandatory_amort)}</td>
                                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#00cc66', fontFamily: "'SF Mono', monospace" }}>{fmt(ds.cash_sweep)}</td>
                                            <td style={{ padding: '8px 12px', textAlign: 'right', color: '#fff', fontFamily: "'SF Mono', monospace", fontWeight: 700 }}>{fmt(ds.closing_debt)}</td>
                                            <td style={{ padding: '8px 12px', textAlign: 'right', color: dscr !== undefined ? dscrColor(dscr) : '#555', fontWeight: 700 }}>
                                                {dscr !== undefined ? multiple(dscr) : '—'}
                                            </td>
                                        </tr>
                                    )
                                })}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ---- IRR Sensitivity ---- */}
            {Object.keys(sensitivity).length > 0 && (() => {
                const entryMultiples = Object.keys(sensitivity).map(Number).sort((a, b) => a - b)
                const exitMultiples = Object.keys(Object.values(sensitivity)[0]).map(Number).sort((a, b) => a - b)
                return (
                    <div style={sectionStyle}>
                        <div style={headerStyle}>IRR SENSITIVITY — ENTRY × EXIT EV/EBITDA</div>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                                <thead>
                                    <tr style={{ background: '#0a0a0a' }}>
                                        <th style={{ padding: '8px 14px', textAlign: 'left', color: '#555', fontWeight: 700, fontSize: 9, letterSpacing: '0.1em' }}>ENTRY \ EXIT</th>
                                        {exitMultiples.map(xm => (
                                            <th key={xm} style={{ padding: '8px 14px', textAlign: 'center', color: '#555', fontWeight: 700, fontSize: 9, letterSpacing: '0.1em' }}>{xm}x</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {entryMultiples.map(em => (
                                        <tr key={em} style={{ borderBottom: '1px solid #111' }}>
                                            <td style={{ padding: '8px 14px', color: '#888', fontWeight: 700 }}>{em}x</td>
                                            {exitMultiples.map(xm => {
                                                const irrPct = sensitivity[em]?.[xm]
                                                const bg = irrPct === null || irrPct === undefined ? 'transparent'
                                                    : irrPct >= 20 ? 'rgba(0,204,102,0.15)'
                                                        : irrPct >= 10 ? 'rgba(255,165,0,0.10)'
                                                            : 'rgba(204,51,51,0.10)'
                                                const color = irrPct === null || irrPct === undefined ? '#444'
                                                    : irrPct >= 20 ? '#00cc66'
                                                        : irrPct >= 10 ? '#ffa500'
                                                            : '#cc3333'
                                                return (
                                                    <td key={xm} style={{ padding: '8px 14px', textAlign: 'center', background: bg, color, fontWeight: 700, fontFamily: "'SF Mono', monospace" }}>
                                                        {irrPct !== null && irrPct !== undefined ? pct(irrPct) : '—'}
                                                    </td>
                                                )
                                            })}
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div style={{ padding: '6px 18px', fontSize: 9, color: '#333', borderTop: '1px solid #111' }}>
                            <span style={{ color: '#00cc66' }}>■</span> ≥20% IRR &nbsp;
                            <span style={{ color: '#ffa500' }}>■</span> 10-20% IRR &nbsp;
                            <span style={{ color: '#cc3333' }}>■</span> &lt;10% IRR
                        </div>
                    </div>
                )
            })()}
        </div>
    )
}

export default LBOResultsView
