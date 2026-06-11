import { useState, useEffect } from 'react'
import {
    fetchWMHealth,
    fetchWMMacroSignals,
    fetchWMFredSeries,
    fetchWMFearGreed,
    fetchWMMarketQuotes,
    type WMMacroSignals,
    type WMFredSeries,
    type WMFearGreedResponse,
    type WMMarketQuote,
} from '../../lib/api'
import { Activity, TrendingUp, TrendingDown, Minus, Radio, BarChart3, RefreshCw } from 'lucide-react'
import { useWMRefresh } from '../../hooks/useWorldMonitor'

interface FredSnapshot {
    label: string
    seriesId: string
    value: number | null
    date: string | null
}

const FRED_SERIES: { id: string; label: string }[] = [
    { id: 'DGS10', label: '10Y Treasury' },
    { id: 'FEDFUNDS', label: 'Fed Funds' },
    { id: 'VIXCLS', label: 'VIX' },
    { id: 'T10Y2Y', label: '10Y-2Y Spread' },
]

function regimeColor(verdict: string): string {
    const v = verdict.toUpperCase()
    if (v.includes('BULLISH')) return 'var(--positive)'
    if (v.includes('BEARISH')) return 'var(--negative)'
    return 'var(--text-muted)'
}

function regimeBg(verdict: string): string {
    const v = verdict.toUpperCase()
    if (v.includes('BULLISH')) return 'var(--positive-bg)'
    if (v.includes('BEARISH')) return 'var(--negative-bg)'
    return 'var(--info-bg)'
}

function regimeBorder(verdict: string): string {
    const v = verdict.toUpperCase()
    if (v.includes('BULLISH')) return 'var(--positive-border)'
    if (v.includes('BEARISH')) return 'var(--negative-border)'
    return 'var(--info-border)'
}

function fgColor(value: number): string {
    if (value <= 25) return 'var(--negative)'
    if (value <= 45) return 'var(--warning)'
    if (value <= 55) return 'var(--text-secondary)'
    if (value <= 75) return 'var(--positive)'
    return 'var(--positive)'
}

function fgLabel(classification: string): string {
    return classification.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

export default function MacroContextPanel() {
    const { refreshKey, refresh, isRefreshing, markDone } = useWMRefresh()
    const [connected, setConnected] = useState<boolean | null>(null)
    const [macro, setMacro] = useState<WMMacroSignals | null>(null)
    const [fredData, setFredData] = useState<FredSnapshot[]>([])
    const [fearGreed, setFearGreed] = useState<WMFearGreedResponse | null>(null)
    const [quotes, setQuotes] = useState<WMMarketQuote[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let cancelled = false
        setLoading(true)

        async function load() {
            try {
                const health = await fetchWMHealth()
                if (cancelled) return
                setConnected(health.connected)

                if (!health.connected) {
                    setLoading(false)
                    markDone()
                    return
                }

                const [macroRes, fgRes, quotesRes, ...fredResults] = await Promise.all([
                    fetchWMMacroSignals(),
                    fetchWMFearGreed(),
                    fetchWMMarketQuotes('SPY,QQQ,DIA,IWM'),
                    ...FRED_SERIES.map(s => fetchWMFredSeries(s.id, 1)),
                ])

                if (cancelled) return

                setMacro(macroRes)
                setFearGreed(fgRes)
                setQuotes(quotesRes.quotes || [])

                const snapshots: FredSnapshot[] = FRED_SERIES.map((s, i) => {
                    const res = fredResults[i] as WMFredSeries
                    const obs = res?.series?.observations
                    const last = obs && obs.length > 0 ? obs[obs.length - 1] : null
                    return {
                        label: s.label,
                        seriesId: s.id,
                        value: last ? last.value : null,
                        date: last ? last.date : null,
                    }
                })
                setFredData(snapshots)
            } catch {
                if (!cancelled) setConnected(false)
            } finally {
                if (!cancelled) { setLoading(false); markDone() }
            }
        }

        load()
        return () => { cancelled = true }
    }, [refreshKey]) // eslint-disable-line react-hooks/exhaustive-deps

    if (loading) {
        return (
            <div className="glass-card" style={{ padding: '24px', animation: 'fadeInUp 0.3s ease both' }}>
                <div className="flex items-center gap-3">
                    <div className="spinner" style={{ width: 14, height: 14 }} />
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', fontFamily: "'JetBrains Mono', monospace" }}>
                        Connecting to WorldMonitor
                    </span>
                </div>
            </div>
        )
    }

    if (!connected) {
        return (
            <div className="glass-card" style={{ padding: '16px 20px', animation: 'fadeInUp 0.3s ease both' }}>
                <div className="flex items-center gap-2">
                    <Radio size={13} style={{ color: 'var(--text-muted)' }} />
                    <span style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.04em', fontFamily: "'JetBrains Mono', monospace" }}>
                        WorldMonitor offline — using hardcoded defaults
                    </span>
                </div>
            </div>
        )
    }

    const verdict = macro?.signals?.verdict || 'UNKNOWN'
    const bullish = macro?.signals?.bullishCount ?? 0
    const total = macro?.signals?.totalCount ?? 0

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, animation: 'fadeInUp 0.3s ease both' }}>
            {/* Header */}
            <div className="flex items-center gap-2" style={{ marginBottom: 2 }}>
                <Activity size={14} style={{ color: 'var(--text-muted)' }} />
                <span style={{
                    fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
                    textTransform: 'uppercase', color: 'var(--text-muted)',
                    fontFamily: "'JetBrains Mono', monospace",
                }}>
                    Market Intelligence
                </span>
                <span className="badge badge-emerald" style={{ fontSize: 9 }}>LIVE</span>
                <button
                    type="button"
                    onClick={refresh}
                    disabled={isRefreshing}
                    title="Refresh market data"
                    style={{
                        marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer',
                        padding: 4, color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                        opacity: isRefreshing ? 0.4 : 0.7,
                    }}
                >
                    <RefreshCw size={12} style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }} />
                </button>
            </div>

            {/* Row 1: Regime + Fear & Greed */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* Macro Regime */}
                <div style={{
                    background: regimeBg(verdict),
                    border: `1px solid ${regimeBorder(verdict)}`,
                    borderRadius: 'var(--radius-md)',
                    padding: '16px 20px',
                }}>
                    <div style={{
                        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
                        color: 'var(--text-muted)', textTransform: 'uppercase',
                        marginBottom: 10, fontFamily: "'JetBrains Mono', monospace",
                    }}>
                        MACRO REGIME
                    </div>
                    <div className="flex items-end justify-between gap-4">
                        <div className="flex items-center gap-2">
                            {verdict.includes('BULLISH')
                                ? <TrendingUp size={20} style={{ color: regimeColor(verdict) }} />
                                : verdict.includes('BEARISH')
                                    ? <TrendingDown size={20} style={{ color: regimeColor(verdict) }} />
                                    : <Minus size={20} style={{ color: regimeColor(verdict) }} />
                            }
                            <span style={{
                                fontSize: 22, fontWeight: 700, color: regimeColor(verdict),
                                letterSpacing: '0.04em', fontFamily: "'JetBrains Mono', monospace",
                            }}>
                                {verdict}
                            </span>
                        </div>
                        <span style={{
                            fontSize: 11, color: 'var(--text-muted)',
                            fontFamily: "'JetBrains Mono', monospace",
                        }}>
                            {bullish}/{total} bullish
                        </span>
                    </div>
                </div>

                {/* Fear & Greed */}
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    padding: '16px 20px',
                }}>
                    <div style={{
                        fontSize: 9, fontWeight: 700, letterSpacing: '0.1em',
                        color: 'var(--text-muted)', textTransform: 'uppercase',
                        marginBottom: 10, fontFamily: "'JetBrains Mono', monospace",
                    }}>
                        FEAR & GREED INDEX
                    </div>
                    {fearGreed?.data ? (
                        <div className="flex items-end justify-between gap-4">
                            <div>
                                <span style={{
                                    fontSize: 28, fontWeight: 300, color: fgColor(fearGreed.data.value),
                                    lineHeight: 1, letterSpacing: '-0.03em',
                                    fontFamily: "'JetBrains Mono', monospace",
                                }}>
                                    {fearGreed.data.value}
                                </span>
                                <span style={{
                                    fontSize: 11, color: fgColor(fearGreed.data.value),
                                    marginLeft: 8, fontWeight: 500,
                                }}>
                                    {fgLabel(fearGreed.data.classification)}
                                </span>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                                    1W: {fearGreed.data.one_week_ago}
                                </div>
                                <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                                    1M: {fearGreed.data.one_month_ago}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Unavailable</span>
                    )}
                </div>
            </div>

            {/* Row 2: Key Rates */}
            <div style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-md)',
                overflow: 'hidden',
            }}>
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${fredData.length}, 1fr)`,
                    gap: 0,
                }}>
                    {fredData.map((s, i) => (
                        <div key={s.seriesId} style={{
                            textAlign: 'center',
                            padding: '14px 10px',
                            borderRight: i < fredData.length - 1 ? '1px solid var(--border-primary)' : 'none',
                        }}>
                            <div style={{
                                fontSize: 9, color: 'var(--text-muted)', letterSpacing: '0.1em',
                                fontWeight: 700, marginBottom: 6,
                                fontFamily: "'JetBrains Mono', monospace",
                            }}>
                                {s.label.toUpperCase()}
                            </div>
                            <div style={{
                                fontSize: 18, fontWeight: 600, color: 'var(--text-primary)',
                                fontFamily: "'SF Mono', Consolas, monospace",
                            }}>
                                {s.value !== null ? (
                                    s.seriesId === 'VIXCLS' ? s.value.toFixed(1) : `${s.value.toFixed(2)}%`
                                ) : '-'}
                            </div>
                            {s.date && (
                                <div style={{
                                    fontSize: 9, color: 'var(--text-muted)',
                                    marginTop: 4, fontFamily: "'JetBrains Mono', monospace",
                                }}>
                                    {s.date}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* Row 3: Market Quotes (if available) */}
            {quotes.length > 0 && (
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                }}>
                    <div style={{
                        padding: '8px 16px', borderBottom: '1px solid var(--border-primary)',
                        display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                        <BarChart3 size={11} style={{ color: 'var(--text-muted)' }} />
                        <span style={{
                            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                            color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace",
                        }}>
                            INDICES
                        </span>
                    </div>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: `repeat(${quotes.length}, 1fr)`,
                        gap: 0,
                    }}>
                        {quotes.map((q, i) => {
                            const isUp = q.changePercent >= 0
                            return (
                                <div key={q.symbol} style={{
                                    padding: '12px 14px',
                                    borderRight: i < quotes.length - 1 ? '1px solid var(--border-primary)' : 'none',
                                }}>
                                    <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                                        <span style={{
                                            fontSize: 10, fontWeight: 700,
                                            color: 'var(--text-secondary)', letterSpacing: '0.04em',
                                            fontFamily: "'JetBrains Mono', monospace",
                                        }}>
                                            {q.symbol}
                                        </span>
                                        {isUp
                                            ? <TrendingUp size={10} style={{ color: 'var(--positive)' }} />
                                            : <TrendingDown size={10} style={{ color: 'var(--negative)' }} />
                                        }
                                    </div>
                                    <div style={{
                                        fontSize: 14, fontWeight: 600, color: 'var(--text-primary)',
                                        fontFamily: "'SF Mono', Consolas, monospace",
                                    }}>
                                        ${q.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </div>
                                    <div style={{
                                        fontSize: 10, fontWeight: 500, marginTop: 2,
                                        color: isUp ? 'var(--positive)' : 'var(--negative)',
                                        fontFamily: "'JetBrains Mono', monospace",
                                    }}>
                                        {isUp ? '+' : ''}{q.changePercent.toFixed(2)}%
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* Attribution */}
            <div style={{
                fontSize: 9, color: 'var(--text-muted)', textAlign: 'right',
                fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em',
                opacity: 0.6,
            }}>
                Source: WorldMonitor real-time intelligence feed
            </div>
        </div>
    )
}
