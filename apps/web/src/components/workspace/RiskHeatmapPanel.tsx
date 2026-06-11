import { useState, useEffect } from 'react'
import {
    fetchWMHealth,
    fetchWMRiskScores,
    fetchWMChokepoints,
    type WMRiskScore,
    type WMChokepoint,
    type WMRiskScoresResponse,
} from '../../lib/api'
import { Shield, Anchor, AlertTriangle, Radio, RefreshCw } from 'lucide-react'
import { useWMRefresh } from '../../hooks/useWorldMonitor'

function riskColor(score: number): string {
    if (score >= 70) return 'var(--negative)'
    if (score >= 50) return 'var(--warning)'
    if (score >= 30) return 'var(--text-secondary)'
    return 'var(--positive)'
}

function riskBg(score: number): string {
    if (score >= 70) return 'var(--negative-bg)'
    if (score >= 50) return 'var(--warning-bg)'
    return 'transparent'
}

function riskLabel(score: number): string {
    if (score >= 70) return 'HIGH'
    if (score >= 50) return 'ELEVATED'
    if (score >= 30) return 'MODERATE'
    return 'LOW'
}

function chokepointStatusColor(status: string): string {
    const s = status.toLowerCase()
    if (s === 'disrupted') return 'var(--negative)'
    if (s === 'degraded') return 'var(--warning)'
    return 'var(--positive)'
}

export default function RiskHeatmapPanel() {
    const { refreshKey, refresh, isRefreshing, markDone } = useWMRefresh()
    const [connected, setConnected] = useState<boolean | null>(null)
    const [riskScores, setRiskScores] = useState<WMRiskScore[]>([])
    const [strategicRisks, setStrategicRisks] = useState<WMRiskScoresResponse['strategicRisks']>([])
    const [chokepoints, setChokepoints] = useState<WMChokepoint[]>([])
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

                const [riskRes, chokeRes] = await Promise.all([
                    fetchWMRiskScores(),
                    fetchWMChokepoints(),
                ])

                if (cancelled) return

                if (riskRes.available) {
                    setRiskScores(riskRes.ciiScores || [])
                    setStrategicRisks(riskRes.strategicRisks || [])
                }
                setChokepoints(chokeRes.chokepoints || [])
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
                        Loading risk intelligence
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
                        WorldMonitor offline — risk data unavailable
                    </span>
                </div>
            </div>
        )
    }

    const sortedScores = [...riskScores].sort((a, b) => b.combinedScore - a.combinedScore)
    const disrupted = chokepoints.filter(c => c.disruptionScore > 40)
    const operational = chokepoints.filter(c => c.disruptionScore <= 40)

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, animation: 'fadeInUp 0.3s ease both' }}>
            {/* Header */}
            <div className="flex items-center gap-2" style={{ marginBottom: 2 }}>
                <Shield size={14} style={{ color: 'var(--text-muted)' }} />
                <span style={{
                    fontSize: 11, fontWeight: 600, letterSpacing: '0.06em',
                    textTransform: 'uppercase', color: 'var(--text-muted)',
                    fontFamily: "'JetBrains Mono', monospace",
                }}>
                    Risk Intelligence
                </span>
                <span className="badge badge-emerald" style={{ fontSize: 9 }}>LIVE</span>
                <button
                    type="button"
                    onClick={refresh}
                    disabled={isRefreshing}
                    title="Refresh risk data"
                    style={{
                        marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer',
                        padding: 4, color: 'var(--text-muted)', display: 'flex', alignItems: 'center',
                        opacity: isRefreshing ? 0.4 : 0.7,
                    }}
                >
                    <RefreshCw size={12} style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }} />
                </button>
            </div>

            {/* Country Risk Scores Table */}
            {sortedScores.length > 0 && (
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                }}>
                    <div style={{
                        padding: '10px 16px', borderBottom: '1px solid var(--border-primary)',
                        display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                        <Shield size={11} style={{ color: 'var(--warning)' }} />
                        <span style={{
                            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                            color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace",
                        }}>
                            COUNTRY INTELLIGENCE INDEX
                        </span>
                        <span style={{
                            fontSize: 9, color: 'var(--text-muted)',
                            fontFamily: "'JetBrains Mono', monospace", marginLeft: 'auto',
                        }}>
                            {sortedScores.length} regions
                        </span>
                    </div>
                    <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--border-primary)' }}>
                                    {['REGION', 'SCORE', 'TREND', 'LEVEL'].map(h => (
                                        <th key={h} style={{
                                            padding: '8px 14px', fontSize: 9, fontWeight: 700,
                                            color: 'var(--text-muted)', letterSpacing: '0.08em',
                                            textAlign: h === 'REGION' ? 'left' : 'center',
                                            fontFamily: "'JetBrains Mono', monospace",
                                        }}>
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {sortedScores.map(s => (
                                    <tr key={s.region} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                        <td style={{
                                            padding: '8px 14px', fontSize: 12, fontWeight: 500,
                                            color: 'var(--text-primary)',
                                        }}>
                                            {s.region}
                                        </td>
                                        <td style={{
                                            padding: '8px 14px', textAlign: 'center',
                                            fontSize: 13, fontWeight: 700,
                                            color: riskColor(s.combinedScore),
                                            fontFamily: "'SF Mono', Consolas, monospace",
                                            background: riskBg(s.combinedScore),
                                        }}>
                                            {s.combinedScore.toFixed(0)}
                                        </td>
                                        <td style={{
                                            padding: '8px 14px', textAlign: 'center',
                                            fontSize: 10, color: 'var(--text-muted)',
                                            fontFamily: "'JetBrains Mono', monospace",
                                        }}>
                                            {s.trend}
                                        </td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center' }}>
                                            <span style={{
                                                fontSize: 9, fontWeight: 600,
                                                color: riskColor(s.combinedScore),
                                                letterSpacing: '0.06em',
                                                fontFamily: "'JetBrains Mono', monospace",
                                            }}>
                                                {riskLabel(s.combinedScore)}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Strategic Risks */}
            {strategicRisks.length > 0 && (
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                }}>
                    <div style={{
                        padding: '10px 16px', borderBottom: '1px solid var(--border-primary)',
                        display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                        <AlertTriangle size={11} style={{ color: 'var(--negative)' }} />
                        <span style={{
                            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                            color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace",
                        }}>
                            STRATEGIC RISK ALERTS
                        </span>
                    </div>
                    <div style={{ padding: '4px 0' }}>
                        {strategicRisks.map((r, i) => (
                            <div key={i} style={{
                                display: 'flex', alignItems: 'center', gap: 12,
                                padding: '10px 16px',
                                borderBottom: i < strategicRisks.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                            }}>
                                <span style={{
                                    fontSize: 12, fontWeight: 500, color: 'var(--text-primary)',
                                    minWidth: 100,
                                }}>
                                    {r.region}
                                </span>
                                <span className={`badge ${r.level === 'critical' ? 'badge-negative' : r.level === 'high' ? 'badge-warning' : 'badge-accent'}`}>
                                    {r.level}
                                </span>
                                <span style={{
                                    fontSize: 11, color: 'var(--text-muted)', flex: 1,
                                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                }}>
                                    {r.factors.join(' / ')}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Supply Chain Chokepoints */}
            {chokepoints.length > 0 && (
                <div style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-primary)',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                }}>
                    <div style={{
                        padding: '10px 16px', borderBottom: '1px solid var(--border-primary)',
                        display: 'flex', alignItems: 'center', gap: 6,
                    }}>
                        <Anchor size={11} style={{ color: 'var(--info)' }} />
                        <span style={{
                            fontSize: 9, fontWeight: 700, letterSpacing: '0.08em',
                            color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace",
                        }}>
                            MARITIME CHOKEPOINTS
                        </span>
                        {disrupted.length > 0 && (
                            <span className="badge badge-warning" style={{ fontSize: 9, marginLeft: 8 }}>
                                {disrupted.length} DISRUPTED
                            </span>
                        )}
                    </div>
                    <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid var(--border-primary)' }}>
                                    {['CHOKEPOINT', 'STATUS', 'DISRUPTION', 'WARNINGS'].map(h => (
                                        <th key={h} style={{
                                            padding: '8px 14px', fontSize: 9, fontWeight: 700,
                                            color: 'var(--text-muted)', letterSpacing: '0.08em',
                                            textAlign: h === 'CHOKEPOINT' ? 'left' : 'center',
                                            fontFamily: "'JetBrains Mono', monospace",
                                        }}>
                                            {h}
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {[...disrupted, ...operational].map(c => (
                                    <tr key={c.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                        <td style={{
                                            padding: '8px 14px', fontSize: 12, fontWeight: 500,
                                            color: 'var(--text-primary)',
                                        }}>
                                            {c.name}
                                        </td>
                                        <td style={{ padding: '8px 14px', textAlign: 'center' }}>
                                            <span style={{
                                                fontSize: 10, fontWeight: 600,
                                                color: chokepointStatusColor(c.status),
                                                letterSpacing: '0.04em',
                                                fontFamily: "'JetBrains Mono', monospace",
                                                textTransform: 'uppercase',
                                            }}>
                                                {c.status}
                                            </span>
                                        </td>
                                        <td style={{
                                            padding: '8px 14px', textAlign: 'center',
                                            fontSize: 13, fontWeight: 700,
                                            color: riskColor(c.disruptionScore),
                                            fontFamily: "'SF Mono', Consolas, monospace",
                                        }}>
                                            {c.disruptionScore.toFixed(0)}
                                        </td>
                                        <td style={{
                                            padding: '8px 14px', textAlign: 'center',
                                            fontSize: 12, color: c.activeWarnings > 0 ? 'var(--warning)' : 'var(--text-muted)',
                                            fontFamily: "'SF Mono', Consolas, monospace",
                                        }}>
                                            {c.activeWarnings}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* Attribution */}
            <div style={{
                fontSize: 9, color: 'var(--text-muted)', textAlign: 'right',
                fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em',
                opacity: 0.6,
            }}>
                Source: WorldMonitor CII + ACLED + Maritime Intelligence
            </div>
        </div>
    )
}
