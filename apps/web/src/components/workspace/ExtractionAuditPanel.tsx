import { useState } from 'react'
import { Shield, CheckCircle, XCircle, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react'

interface AuditEntry {
    field: string
    confidence: number
    source: string
    auditor_status: string
    triangulation: string
}

interface TriangulationCheck {
    identity: string
    passed: boolean
    expected: number
    actual: number
    deviation_pct: number
    details: string
    severity: string
}

interface ExtractionQuality {
    mode: string
    pipeline_stages?: string[]
    audit_trail?: AuditEntry[]
    triangulation?: {
        overall_verdict: string
        total_checks: number
        passed: number
        failed: number
        critical_failures: number
        results: TriangulationCheck[]
    }
    data_sources?: string[]
}

interface Props { data: ExtractionQuality }

function formatFieldName(name: string): string {
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        .replace('Ebitda', 'EBITDA').replace('Fy', 'FY').replace('Da ', 'D&A ').replace('Wacc', 'WACC')
}

export default function ExtractionAuditPanel({ data }: Props) {
    const [expanded, setExpanded] = useState(false)
    const [selectedField, setSelectedField] = useState<AuditEntry | null>(null)

    const auditTrail = data.audit_trail || []
    const triangulation = data.triangulation
    const pipelineStages = data.pipeline_stages || []

    if (auditTrail.length === 0 && !triangulation) return null

    const highConf = auditTrail.filter(a => a.confidence >= 0.8).length
    const medConf = auditTrail.filter(a => a.confidence >= 0.5 && a.confidence < 0.8).length
    const lowConf = auditTrail.filter(a => a.confidence < 0.5).length

    return (
        <div style={{
            marginBottom: 16, background: '#0a0a0a',
            border: '1px solid #222', borderRadius: 3, overflow: 'hidden'
        }}>
            {/* Header */}
            <div
                onClick={() => setExpanded(!expanded)}
                style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 18px', cursor: 'pointer',
                    borderBottom: expanded ? '1px solid #222' : 'none'
                }}
            >
                <Shield size={14} style={{ color: '#00cc66' }} />
                <div style={{ flex: 1 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.06em', color: '#aaa' }}>
                        AUDIT TRAIL
                    </span>
                    <span style={{ fontSize: 10, color: '#444', marginLeft: 10 }}>
                        {pipelineStages.join(' → ')} · {auditTrail.length} fields
                    </span>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {highConf > 0 && <span className="badge badge-emerald">{highConf} PASS</span>}
                    {medConf > 0 && <span className="badge badge-amber">{medConf} WARN</span>}
                    {lowConf > 0 && <span className="badge badge-rose">{lowConf} FAIL</span>}
                    {expanded ? <ChevronUp size={13} style={{ color: '#444' }} />
                        : <ChevronDown size={13} style={{ color: '#444' }} />}
                </div>
            </div>

            {/* Expanded */}
            {expanded && (
                <div>
                    {/* Triangulation */}
                    {triangulation && (
                        <div style={{
                            padding: '10px 18px', margin: '8px 12px',
                            background: triangulation.overall_verdict === 'pass' ? 'rgba(0,204,102,0.04)' : 'rgba(204,51,51,0.04)',
                            border: `1px solid ${triangulation.overall_verdict === 'pass' ? 'rgba(0,204,102,0.15)' : 'rgba(204,51,51,0.15)'}`,
                            borderRadius: 2
                        }}>
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
                                fontSize: 11, fontWeight: 700,
                                color: triangulation.overall_verdict === 'pass' ? '#00cc66'
                                    : triangulation.overall_verdict === 'halt' ? '#cc3333' : '#ffaa00'
                            }}>
                                {triangulation.overall_verdict === 'pass' ? <CheckCircle size={13} /> :
                                    triangulation.overall_verdict === 'halt' ? <XCircle size={13} /> :
                                        <AlertTriangle size={13} />}
                                TRIANGULATION: {triangulation.passed}/{triangulation.total_checks} PASSED
                            </div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                                {triangulation.results.map((check, i) => (
                                    <span key={i} className={`badge ${check.passed ? 'badge-emerald' : 'badge-rose'}`}>
                                        {check.passed ? '✓' : '✗'} {check.identity}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Table */}
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>Field</th>
                                <th style={{ textAlign: 'center' }}>Confidence</th>
                                <th style={{ textAlign: 'center' }}>Auditor</th>
                                <th style={{ textAlign: 'center' }}>Source</th>
                            </tr>
                        </thead>
                        <tbody>
                            {auditTrail.map((entry, i) => (
                                <tr key={i}
                                    onClick={() => setSelectedField(selectedField?.field === entry.field ? null : entry)}
                                    style={{
                                        cursor: 'pointer',
                                        background: selectedField?.field === entry.field ? '#111' : undefined
                                    }}
                                >
                                    <td style={{ fontWeight: 500, color: '#fff', fontFamily: "'Inter', system-ui, sans-serif", fontSize: 12 }}>
                                        {formatFieldName(entry.field)}
                                    </td>
                                    <td style={{ textAlign: 'center' }}>
                                        <span className={`badge ${entry.confidence >= 0.8 ? 'badge-emerald'
                                                : entry.confidence >= 0.5 ? 'badge-amber' : 'badge-rose'
                                            }`}>
                                            {(entry.confidence * 100).toFixed(0)}%
                                        </span>
                                    </td>
                                    <td style={{ textAlign: 'center' }}>
                                        <span className={`badge ${entry.auditor_status === 'approved' ? 'badge-emerald'
                                                : entry.auditor_status === 'flagged' ? 'badge-amber'
                                                    : entry.auditor_status === 'rejected' ? 'badge-rose'
                                                        : 'badge-indigo'
                                            }`}>
                                            {entry.auditor_status}
                                        </span>
                                    </td>
                                    <td style={{ textAlign: 'center', color: '#444', fontSize: 11 }}>
                                        {entry.source ? '📄' : '—'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {/* Citation */}
                    {selectedField && (
                        <div style={{ padding: '12px 18px', borderTop: '1px solid #222' }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: '#ff6600', letterSpacing: '0.06em', marginBottom: 6 }}>
                                SOURCE — {formatFieldName(selectedField.field).toUpperCase()}
                            </div>
                            <div style={{
                                fontSize: 12, lineHeight: 1.6, color: '#888',
                                padding: '10px 12px', background: '#050505', borderRadius: 2,
                                border: '1px solid #1a1a1a', fontFamily: "'SF Mono', Consolas, monospace"
                            }}>
                                {selectedField.source || 'No citation provided.'}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
