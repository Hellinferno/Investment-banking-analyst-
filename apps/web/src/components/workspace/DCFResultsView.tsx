import type { ValuationResult } from '../../lib/api'
import { TrendingUp, BarChart3, Target, Shield, Activity } from 'lucide-react'

interface Props { data: ValuationResult }

function fmt(n: number | undefined | null, decimals = 0): string {
    if (n === undefined || n === null) return '-'
    if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(1)}B`
    if (Math.abs(n) >= 1e7) return `${(n / 1e7).toFixed(1)} Cr`
    if (Math.abs(n) >= 1e5) return `${(n / 1e5).toFixed(1)}L`
    return n.toLocaleString('en-IN', { maximumFractionDigits: decimals })
}

function pct(n: number | undefined | null): string {
    if (n === undefined || n === null) return '-'
    return `${(n * 100).toFixed(1)}%`
}

function currency(n: number | undefined | null, cur = 'Rs '): string {
    if (n === undefined || n === null) return '-'
    return `${cur}${fmt(n, 2)}`
}

function titleCase(label: string): string {
    return label
        .replace(/_/g, ' ')
        .replace(/\b\w/g, c => c.toUpperCase())
        .replace('Tgr', 'TGR')
        .replace('Wacc', 'WACC')
}

function formatBridgeValue(key: string, value: unknown, cur: string): string {
    if (typeof value === 'boolean') return value ? 'Yes' : 'No'
    if (typeof value !== 'number') return String(value ?? '-')
    if (key.includes('percent')) return pct(value)
    if (key.includes('shares')) return fmt(value, 0)
    return currency(value, cur)
}

function formatTvCrosscheckValue(key: string, value: unknown, cur: string): string {
    if (value === undefined || value === null) return '-'
    if (typeof value !== 'number') return String(value)
    if (key.includes('gap_pct')) return `${value.toFixed(1)}%`
    if (key.includes('multiple_used')) return `${value.toFixed(1)}x`
    if (key.includes('metric_value')) return currency(value, cur)
    return currency(value, cur)
}

export default function DCFResultsView({ data }: Props) {
    const h = data.header
    const cur = h.currency === 'USD' ? '$' : 'Rs '
    const isPrivate = Boolean(h.is_private_company)
    const hasPerShareValue = h.implied_share_price !== undefined && h.implied_share_price !== null
    const checkpoint = data.extraction_quality?.checkpoint
    const checkpointStatus = String(checkpoint?.status || '').toLowerCase()
    const checkpointBlockingIssues = Array.isArray(checkpoint?.blocking_issues) ? checkpoint!.blocking_issues! : []
    const topBlockingIssues = checkpointBlockingIssues.slice(0, 3)
    const sensitivityMetric = !isPrivate && data.sensitivity_labels?.metric !== 'equity_value' && hasPerShareValue
        ? 'Share Price'
        : 'Equity Value'

    const heroMetrics = isPrivate
        ? [
            { label: 'ENTERPRISE VALUE', value: currency(h.enterprise_value, cur) },
            { label: 'EQUITY VALUE', value: currency(h.equity_value, cur), highlight: true },
            { label: 'LIQUIDITY DISC.', value: pct(h.liquidity_discount) },
            { label: 'WACC', value: pct(h.wacc) },
            { label: 'TV METHOD', value: h.terminal_method || 'Gordon' },
        ]
        : [
            { label: 'ENTERPRISE VALUE', value: currency(h.enterprise_value, cur) },
            { label: 'EQUITY VALUE', value: currency(h.equity_value, cur) },
            { label: 'PER-SHARE VALUE', value: hasPerShareValue ? `${cur}${h.implied_share_price!.toFixed(2)}` : 'Unavailable', highlight: true },
            { label: 'WACC', value: pct(h.wacc) },
            { label: 'TV METHOD', value: h.terminal_method || 'Gordon' },
        ]

    return (
        <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{
                background: '#0a0a0a', border: '1px solid #222', borderRadius: 3,
                padding: '20px 24px'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                    <TrendingUp size={16} style={{ color: '#ff6600' }} />
                    <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.04em' }}>DCF VALUATION</span>
                    <span className={`badge ${isPrivate ? 'badge-amber' : hasPerShareValue ? 'badge-emerald' : 'badge-amber'}`} style={{ marginLeft: 'auto' }}>
                        {isPrivate ? 'PRIVATE CO' : hasPerShareValue ? 'PUBLIC CO' : 'PUBLIC CO · EQ VALUE ONLY'}
                    </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 0, border: '1px solid #1a1a1a', borderRadius: 2, overflow: 'hidden' }}>
                    {heroMetrics.map((metric, i) => (
                        <div key={i} style={{
                            textAlign: 'center', padding: '14px 10px',
                            borderRight: i < heroMetrics.length - 1 ? '1px solid #1a1a1a' : 'none',
                            background: metric.highlight ? 'rgba(255,102,0,0.04)' : 'transparent'
                        }}>
                            <div style={{ fontSize: 9, color: '#555', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 6 }}>{metric.label}</div>
                            <div style={{
                                fontSize: metric.highlight ? 22 : 16, fontWeight: 700,
                                color: metric.highlight ? '#ff6600' : '#fff',
                                fontFamily: "'SF Mono', Consolas, monospace"
                            }}>{metric.value}</div>
                        </div>
                    ))}
                </div>
            </div>

            {(data.warnings?.length || data.extraction_quality) && (
                <div style={{ background: '#120d08', border: '1px solid #4a2a14', borderRadius: 3, padding: '14px 18px' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: data.warnings?.length ? 12 : 0 }}>
                        <span style={{ fontSize: 10, color: '#ffb36b', fontWeight: 700, letterSpacing: '0.08em' }}>MODEL WARNINGS</span>
                        {checkpointStatus && (
                            <span className={`badge ${checkpointStatus === 'passed' ? 'badge-emerald' : 'badge-rose'}`}>
                                Checkpoint: {checkpointStatus === 'passed' ? 'PASSED' : 'FAILED'}
                            </span>
                        )}
                        {data.extraction_quality?.mode && (
                            <span style={{ fontSize: 11, color: '#c98a4a' }}>Source Mode: {data.extraction_quality.mode}</span>
                        )}
                        {typeof data.extraction_quality?.triangulation?.overall_verdict === 'string' && (
                            <span style={{ fontSize: 11, color: '#c98a4a' }}>
                                Triangulation: {data.extraction_quality.triangulation.overall_verdict.toUpperCase()}
                            </span>
                        )}
                        {!isPrivate && (
                            <span style={{ fontSize: 11, color: '#c98a4a' }}>
                                Per-share: {hasPerShareValue ? 'Available' : 'Suppressed'}
                            </span>
                        )}
                    </div>

                    {topBlockingIssues.length > 0 && (
                        <div style={{ marginBottom: data.warnings?.length ? 12 : 0, padding: '10px 12px', border: '1px solid rgba(204,51,51,0.25)', borderRadius: 2, background: 'rgba(204,51,51,0.05)' }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: '#ff9b9b', letterSpacing: '0.06em', marginBottom: 6 }}>
                                CHECKPOINT BLOCKING ISSUES
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {topBlockingIssues.map((issue, idx) => (
                                    <div key={idx} style={{ fontSize: 12, color: '#f3d2b3', lineHeight: 1.45 }}>
                                        • {issue}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {data.warnings?.length ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {data.warnings.map((warning, index) => (
                                <div key={index} style={{ fontSize: 12, color: '#f3d2b3', lineHeight: 1.45 }}>
                                    {warning}
                                </div>
                            ))}
                        </div>
                    ) : null}
                </div>
            )}

            {data.scenarios && (
                <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: 3 }}>
                    <div style={{ padding: '10px 20px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <BarChart3 size={13} style={{ color: '#3399ff' }} />
                        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: '#aaa' }}>SCENARIO ANALYSIS</span>
                    </div>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Scenario</th>
                                <th>Rev CAGR</th>
                                <th>EBITDA Mgn</th>
                                <th>EV</th>
                                <th>Equity</th>
                                {!isPrivate && hasPerShareValue && <th>Share Price</th>}
                            </tr>
                        </thead>
                        <tbody>
                            {(['bear', 'base', 'bull'] as const).map(key => {
                                const scenario = data.scenarios![key]
                                const colors: Record<string, string> = { bear: '#cc3333', base: '#fff', bull: '#00cc66' }
                                return (
                                    <tr key={key}>
                                        <td style={{ fontWeight: 700, color: colors[key], fontFamily: "'Inter', system-ui, sans-serif" }}>{scenario.label}</td>
                                        <td>{pct(scenario.revenue_cagr)}</td>
                                        <td>{pct(scenario.ebitda_margin)}</td>
                                        <td>{currency(scenario.valuation?.enterprise_value, cur)}</td>
                                        <td>{currency(scenario.valuation?.equity_value, cur)}</td>
                                        {!isPrivate && hasPerShareValue && (
                                            <td style={{ fontWeight: 700, color: colors[key] }}>
                                                {scenario.valuation?.share_price !== undefined && scenario.valuation?.share_price !== null
                                                    ? `${cur}${scenario.valuation.share_price.toFixed(2)}`
                                                    : '-'}
                                            </td>
                                        )}
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {data.ev_bridge && (
                <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: 3 }}>
                    <div style={{ padding: '10px 20px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Target size={13} style={{ color: '#3399ff' }} />
                        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: '#aaa' }}>EV TO EQUITY BRIDGE</span>
                    </div>
                    <div style={{ padding: '4px 0' }}>
                        {Object.entries(data.ev_bridge).map(([label, value]) => (
                            <div key={label} style={{
                                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                                padding: '8px 20px', borderBottom: '1px solid #111'
                            }}>
                                <span style={{ fontSize: 12, color: '#888', fontFamily: "'Inter', system-ui, sans-serif" }}>
                                    {titleCase(label)}
                                </span>
                                <span style={{
                                    fontSize: 13, fontWeight: 600, fontFamily: "'SF Mono', Consolas, monospace",
                                    color: typeof value === 'number' && value < 0 ? '#cc3333' : '#fff'
                                }}>
                                    {formatBridgeValue(label, value, cur)}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {data.tv_crosscheck && (
                <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: 3 }}>
                    <div style={{ padding: '10px 20px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Shield size={13} style={{ color: '#ffaa00' }} />
                        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: '#aaa' }}>TV CROSS-CHECK</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Object.keys(data.tv_crosscheck).length}, 1fr)`, gap: 0 }}>
                        {Object.entries(data.tv_crosscheck).map(([label, value], i, arr) => (
                            <div key={label} style={{
                                textAlign: 'center', padding: '14px 10px',
                                borderRight: i < arr.length - 1 ? '1px solid #1a1a1a' : 'none'
                            }}>
                                <div style={{ fontSize: 9, color: '#555', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 6 }}>
                                    {titleCase(label).toUpperCase()}
                                </div>
                                <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', fontFamily: "'SF Mono', Consolas, monospace" }}>
                                    {formatTvCrosscheckValue(label, value, cur)}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {data.sensitivity_wacc_tgr && data.sensitivity_labels && (
                <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: 3 }}>
                    <div style={{ padding: '10px 20px', borderBottom: '1px solid #222', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Activity size={13} style={{ color: '#00cc66' }} />
                        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: '#aaa' }}>
                            WACC x TGR SENSITIVITY ({sensitivityMetric.toUpperCase()})
                        </span>
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                        <table className="data-table" style={{ minWidth: 500 }}>
                            <thead>
                                <tr>
                                    <th style={{ fontSize: 9 }}>WACC \ TGR</th>
                                    {data.sensitivity_labels.tgr.map(t => (
                                        <th key={t} style={{ textAlign: 'center' }}>{pct(t)}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data.sensitivity_wacc_tgr.map((row, wi) => (
                                    <tr key={wi}>
                                        <td style={{ fontWeight: 700, color: '#fff' }}>
                                            {pct(data.sensitivity_labels!.wacc[wi])}
                                        </td>
                                        {row.map((val, ti) => {
                                            const isBase = wi === Math.floor(data.sensitivity_wacc_tgr!.length / 2) && ti === Math.floor(row.length / 2)
                                            return (
                                                <td key={ti} style={{
                                                    textAlign: 'center', fontWeight: isBase ? 700 : 400,
                                                    color: isBase ? '#ff6600' : '#999',
                                                    background: isBase ? 'rgba(255,102,0,0.06)' : 'transparent',
                                                }}>
                                                    {typeof val === 'number' ? currency(val, cur) : '-'}
                                                </td>
                                            )
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {data.company_classification && (
                <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: 3, padding: '12px 20px' }}>
                    <span style={{ fontSize: 10, color: '#555', fontWeight: 700, letterSpacing: '0.08em' }}>COMPANY CLASSIFICATION</span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, marginTop: 8, fontSize: 11, color: '#666' }}>
                        <div><span style={{ color: '#888' }}>Type: </span>{data.company_classification.entity_type}</div>
                        <div><span style={{ color: '#888' }}>Listing: </span>{data.company_classification.listing_status}</div>
                        {data.company_classification.cin && <div><span style={{ color: '#888' }}>CIN: </span>{data.company_classification.cin}</div>}
                    </div>
                </div>
            )}
        </div>
    )
}
