import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import {
    deployAgent,
    fetchAgentRun,
    fetchDocuments,
    type AgentRunResult,
    type ValuationResult,
} from '../../lib/api'
import { Play, AlertCircle, ChevronRight } from 'lucide-react'
import DCFResultsView from './DCFResultsView'
import LBOResultsView from './LBOResultsView'
import ExtractionAuditPanel from './ExtractionAuditPanel'

interface Props { dealId: string }

// ---- Agent Registry --------------------------------------------------------

interface AgentParam {
    key: string
    label: string
    type: 'number' | 'text'
    placeholder: string
    defaultValue: string | number
}

interface AgentConfig {
    id: string
    label: string
    agentType: string
    taskName: string
    badge: string
    description: string
    params: AgentParam[]
}

const AGENT_CONFIGS: AgentConfig[] = [
    {
        id: 'dcf',
        label: 'DCF Model',
        agentType: 'modeling',
        taskName: 'dcf_model',
        badge: 'DCF',
        description: 'Discounted Cash Flow valuation · Preparer → Auditor → Triangulator → DCF Engine',
        params: [
            { key: 'projection_years', label: 'PROJECTION YEARS', type: 'number', placeholder: '5', defaultValue: 5 },
            { key: 'terminal_growth_rate', label: 'TERMINAL GROWTH', type: 'number', placeholder: '0.025', defaultValue: 0.025 },
            { key: 'wacc_override', label: 'WACC OVERRIDE', type: 'text', placeholder: '—', defaultValue: '' },
            { key: 'current_market_cap', label: 'CURRENT MARKET CAP', type: 'text', placeholder: 'Optional', defaultValue: '' },
            { key: 'current_share_price', label: 'CURRENT SHARE PRICE', type: 'text', placeholder: 'Optional', defaultValue: '' },
        ],
    },
    {
        id: 'lbo',
        label: 'LBO Model',
        agentType: 'modeling',
        taskName: 'lbo_model',
        badge: 'LBO',
        description: 'Leveraged Buyout analysis · Extract → LBO Engine → IRR/MOIC · Sources & Uses → Debt Schedule',
        params: [
            { key: 'entry_ev_ebitda', label: 'ENTRY EV/EBITDA', type: 'number', placeholder: '8.0', defaultValue: 8.0 },
            { key: 'exit_ev_ebitda', label: 'EXIT EV/EBITDA', type: 'number', placeholder: '10.0', defaultValue: 10.0 },
            { key: 'equity_contribution_pct', label: 'EQUITY CONTRIBUTION %', type: 'number', placeholder: '0.40', defaultValue: 0.40 },
            { key: 'senior_debt_ebitda', label: 'SENIOR DEBT (x EBITDA)', type: 'number', placeholder: '3.0', defaultValue: 3.0 },
            { key: 'projection_years', label: 'HOLD PERIOD (YRS)', type: 'number', placeholder: '5', defaultValue: 5 },
        ],
    },
    {
        id: 'pitchbook',
        label: 'Pitchbook',
        agentType: 'pitchbook',
        taskName: 'generate_pitchbook',
        badge: 'PDF',
        description: 'Executive summary pitch deck · Company Overview → Industry → Financials → Valuation',
        params: [],
    },
    {
        id: 'dd',
        label: 'Due Diligence',
        agentType: 'due_diligence',
        taskName: 'dd_report',
        badge: 'DD',
        description: 'Risk assessment report · Financial → Operational → Legal → Market risks + Red Flags',
        params: [],
    },
    {
        id: 'research',
        label: 'Market Research',
        agentType: 'research',
        taskName: 'industry_brief',
        badge: 'Research',
        description: 'Industry brief PDF + Buyer universe JSON · Market sizing → Competitive landscape → Buyers',
        params: [],
    },
    {
        id: 'cim',
        label: 'CIM Draft',
        agentType: 'doc_drafter',
        taskName: 'cim_draft',
        badge: 'DOCX',
        description: 'Confidential Information Memorandum · 5 sections drafted from uploaded documents',
        params: [],
    },
    {
        id: 'coordination',
        label: 'Meeting Notes',
        agentType: 'coordination',
        taskName: 'extract_tasks',
        badge: 'Tasks',
        description: 'Extract action items, decisions, and follow-ups from meeting notes and documents',
        params: [],
    },
]

// ---- Component -------------------------------------------------------------

export default function AgentsTab({ dealId }: Props) {
    const [selectedAgentId, setSelectedAgentId] = useState<string>('dcf')
    const [paramValues, setParamValues] = useState<Record<string, Record<string, string | number>>>({})

    const [deploying, setDeploying] = useState(false)
    const [result, setResult] = useState<AgentRunResult | null>(null)
    const [valuation, setValuation] = useState<ValuationResult | null>(null)
    const [lboResult, setLboResult] = useState<Record<string, unknown> | null>(null)
    const [error, setError] = useState('')
    const [activeRunId, setActiveRunId] = useState<string | null>(null)
    const [documentsReady, setDocumentsReady] = useState(true)
    const [documentStatusNote, setDocumentStatusNote] = useState('')

    const selectedAgent = AGENT_CONFIGS.find(a => a.id === selectedAgentId) ?? AGENT_CONFIGS[0]

    // Initialise param values for an agent if not already set
    const getParamValue = (agentId: string, paramKey: string, defaultValue: string | number) => {
        return paramValues[agentId]?.[paramKey] ?? defaultValue
    }
    const setParamValue = (agentId: string, paramKey: string, value: string | number) => {
        setParamValues(prev => ({
            ...prev,
            [agentId]: { ...prev[agentId], [paramKey]: value },
        }))
    }

    const refreshDocumentReadiness = useCallback(async () => {
        try {
            const docs = await fetchDocuments(dealId)
            const blocked = docs.filter(doc => doc.parse_status !== 'parsed')
            if (blocked.length === 0) {
                setDocumentsReady(true)
                setDocumentStatusNote(docs.length > 0 ? 'All uploaded documents are parsed and ready.' : '')
            } else {
                setDocumentsReady(false)
                setDocumentStatusNote(
                    `Waiting on ${blocked.length} document(s): ${blocked.map(doc => doc.filename).slice(0, 3).join(', ')}`
                )
            }
            return blocked.length === 0
        } catch {
            setDocumentsReady(true)
            setDocumentStatusNote('')
            return true
        }
    }, [dealId])

    useEffect(() => { refreshDocumentReadiness() }, [refreshDocumentReadiness])

    useEffect(() => {
        if (documentsReady) return
        const interval = window.setInterval(() => { refreshDocumentReadiness() }, 3000)
        return () => window.clearInterval(interval)
    }, [documentsReady, refreshDocumentReadiness])

    useEffect(() => {
        if (!activeRunId) return
        const startTime = Date.now()
        const interval = window.setInterval(async () => {
            const elapsed = Date.now() - startTime
            try {
                const run = await fetchAgentRun(dealId, activeRunId)
                setResult(run)
                if (run.valuation_result) setValuation(run.valuation_result)
                if ((run as Record<string, unknown>).lbo_result) {
                    setLboResult((run as Record<string, unknown>).lbo_result as Record<string, unknown>)
                }
                if (run.status === 'completed') {
                    setDeploying(false)
                    setActiveRunId(null)
                } else if (run.status === 'failed') {
                    setDeploying(false)
                    setActiveRunId(null)
                    setError(run.error_message || 'Agent run failed')
                } else if (elapsed > 10 * 60 * 1000) {
                    setDeploying(false)
                    setActiveRunId(null)
                    setError('Agent run timed out after 10 minutes. Check server logs.')
                }
            } catch {
                setDeploying(false)
                setActiveRunId(null)
                setError('Failed to refresh agent status')
            }
        }, elapsed < 30000 ? 2500 : elapsed < 120000 ? 5000 : 10000)
        return () => window.clearInterval(interval)
    }, [activeRunId, dealId])

    const handleDeploy = async () => {
        setDeploying(true)
        setError('')
        setResult(null)
        setValuation(null)
        setLboResult(null)

        const docsReady = await refreshDocumentReadiness()
        if (!docsReady) {
            setDeploying(false)
            setError('Documents are still parsing. Wait until all files are marked parsed before running the agent.')
            return
        }

        try {
            const params: Record<string, unknown> = {}
            for (const p of selectedAgent.params) {
                const v = getParamValue(selectedAgent.id, p.key, p.defaultValue)
                if (v !== '' && v !== null && v !== undefined) {
                    params[p.key] = typeof p.defaultValue === 'number' ? Number(v) : v
                }
            }

            const res = await deployAgent(dealId, {
                agent_type: selectedAgent.agentType,
                task_name: selectedAgent.taskName,
                parameters: params,
            })
            setResult(res)
            if (res.valuation_result) setValuation(res.valuation_result)
            if ((res as Record<string, unknown>).lbo_result) {
                setLboResult((res as Record<string, unknown>).lbo_result as Record<string, unknown>)
            }

            if (res.status === 'completed') {
                setDeploying(false)
            } else if (res.status === 'failed') {
                setDeploying(false)
                setError(res.error_message || 'Agent run failed')
            } else {
                setActiveRunId(res.run_id)
            }
        } catch (err: unknown) {
            let msg = err instanceof Error ? err.message : 'Deployment failed'
            if (axios.isAxiosError(err) && err.code === 'ECONNABORTED') {
                msg = 'Agent run is taking longer than the browser timeout. Results will appear when complete.'
            }
            if (axios.isAxiosError(err)) {
                msg = (err.response?.data as { detail?: string } | undefined)?.detail || msg
            }
            setError(msg)
            setDeploying(false)
            setActiveRunId(null)
        }
    }

    const showDCFResults = result?.status === 'completed' && selectedAgent.id === 'dcf' && valuation
    const showLBOResults = result?.status === 'completed' && selectedAgent.id === 'lbo' && lboResult
    const showGenericSuccess = result?.status === 'completed' && !showDCFResults && !showLBOResults

    return (
        <div className="animate-fade-in">
            {/* ---- Agent Picker ---- */}
            <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 10, color: '#555', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 8 }}>
                    SELECT AGENT
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {AGENT_CONFIGS.map(agent => (
                        <button
                            key={agent.id}
                            onClick={() => { setSelectedAgentId(agent.id); setResult(null); setError(''); setValuation(null); setLboResult(null) }}
                            style={{
                                display: 'flex', alignItems: 'center', gap: 6,
                                padding: '7px 12px',
                                background: selectedAgentId === agent.id ? '#fff' : '#0a0a0a',
                                border: selectedAgentId === agent.id ? '1px solid #fff' : '1px solid #333',
                                borderRadius: 3,
                                color: selectedAgentId === agent.id ? '#000' : '#888',
                                fontSize: 11, fontWeight: 700, cursor: 'pointer',
                                letterSpacing: '0.03em',
                                transition: 'all 0.1s',
                            }}
                        >
                            <span style={{
                                fontSize: 9, fontWeight: 800, padding: '2px 5px',
                                background: selectedAgentId === agent.id ? '#000' : '#222',
                                color: selectedAgentId === agent.id ? '#fff' : '#555',
                                borderRadius: 2, letterSpacing: '0.05em',
                            }}>
                                {agent.badge}
                            </span>
                            {agent.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* ---- Selected Agent Header ---- */}
            <div style={{
                padding: '14px 18px', marginBottom: 16,
                background: '#0a0a0a', border: '1px solid #222', borderRadius: 3,
                display: 'flex', alignItems: 'center', justifyContent: 'space-between'
            }}>
                <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 2 }}>
                        {selectedAgent.label}
                    </div>
                    <div style={{ fontSize: 11, color: '#555' }}>
                        {selectedAgent.description}
                    </div>
                </div>
                <span className="badge badge-indigo">{selectedAgent.badge}</span>
            </div>

            {/* ---- Document Readiness Warning ---- */}
            {!documentsReady && documentStatusNote && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
                    background: 'rgba(255,153,0,0.08)', border: '1px solid rgba(255,153,0,0.2)',
                    borderRadius: 3, marginBottom: 16, color: '#ff9900', fontSize: 12
                }}>
                    <AlertCircle size={14} /> {documentStatusNote}
                </div>
            )}

            {/* ---- Parameters ---- */}
            {selectedAgent.params.length > 0 && (
                <div style={{ marginBottom: 16, border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ padding: '8px 18px', background: '#0a0a0a', borderBottom: '1px solid #222' }}>
                        <span style={{ fontSize: 10, color: '#555', fontWeight: 700, letterSpacing: '0.1em' }}>PARAMETERS</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 0 }}>
                        {selectedAgent.params.map((param, i) => (
                            <div key={param.key} style={{
                                padding: '12px 18px',
                                borderRight: '1px solid #1a1a1a',
                                borderBottom: i < selectedAgent.params.length - 2 ? '1px solid #1a1a1a' : 'none'
                            }}>
                                <div style={{ fontSize: 9, color: '#555', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 6 }}>
                                    {param.label}
                                </div>
                                <input
                                    type={param.type}
                                    className="input-field"
                                    value={String(getParamValue(selectedAgent.id, param.key, param.defaultValue))}
                                    placeholder={param.placeholder}
                                    onChange={e => setParamValue(selectedAgent.id, param.key, e.target.value)}
                                    step={param.type === 'number' ? 0.01 : undefined}
                                    style={{ padding: '8px 10px' }}
                                />
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ---- Deploy Button ---- */}
            <button
                className="btn-primary"
                onClick={handleDeploy}
                disabled={deploying || !documentsReady}
                style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    justifyContent: 'center', width: '100%', padding: '12px 0',
                    marginBottom: 20, fontSize: 13, fontWeight: 700, letterSpacing: '0.04em',
                    opacity: deploying || !documentsReady ? 0.7 : 1,
                }}
            >
                {deploying ? (
                    <><div className="spinner" style={{ width: 14, height: 14, borderTopColor: '#000' }} /> RUNNING {selectedAgent.label.toUpperCase()}...</>
                ) : (
                    <><Play size={14} /> DEPLOY {selectedAgent.label.toUpperCase()}</>
                )}
            </button>

            {/* ---- Error ---- */}
            {error && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
                    background: 'rgba(204,51,51,0.08)', border: '1px solid rgba(204,51,51,0.2)',
                    borderRadius: 3, marginBottom: 16, color: '#cc3333', fontSize: 12
                }}>
                    <AlertCircle size={14} /> {error}
                </div>
            )}

            {/* ---- Run Status ---- */}
            {result && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '10px 14px', marginBottom: 16,
                    background: result.status === 'completed'
                        ? 'rgba(0,204,102,0.06)'
                        : result.status === 'failed'
                            ? 'rgba(204,51,51,0.08)'
                            : '#0a0a0a',
                    border: result.status === 'completed'
                        ? '1px solid rgba(0,204,102,0.15)'
                        : result.status === 'failed'
                            ? '1px solid rgba(204,51,51,0.2)'
                            : '1px solid #222',
                    borderRadius: 3
                }}>
                    <span className={`status-dot ${result.status === 'completed' ? 'active' : 'pending'}`} />
                    <span style={{ fontSize: 12, fontWeight: 700, color: result.status === 'completed' ? '#00cc66' : '#aaa' }}>
                        STATUS: {result.status.toUpperCase()}
                    </span>
                    <span style={{ fontSize: 11, color: '#444', marginLeft: 'auto', fontFamily: "'SF Mono', Consolas, monospace" }}>
                        {result.run_id?.slice(0, 8)}
                    </span>
                </div>
            )}

            {/* ---- Generic success (non-DCF/LBO agents) ---- */}
            {showGenericSuccess && (
                <div style={{
                    padding: '16px 18px', background: 'rgba(0,204,102,0.06)',
                    border: '1px solid rgba(0,204,102,0.15)', borderRadius: 3, marginBottom: 16,
                }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#00cc66', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span className="status-dot active" />
                        {selectedAgent.label} Complete
                    </div>
                    <div style={{ fontSize: 11, color: '#555', display: 'flex', alignItems: 'center', gap: 4 }}>
                        Output files are ready for download in the <strong style={{ color: '#888' }}>Outputs</strong> tab.
                        <ChevronRight size={12} style={{ color: '#444' }} />
                    </div>
                </div>
            )}

            {/* ---- DCF Results ---- */}
            {valuation?.extraction_quality && (
                <ExtractionAuditPanel data={valuation.extraction_quality} />
            )}
            {showDCFResults && <DCFResultsView data={valuation!} />}

            {/* ---- LBO Results ---- */}
            {showLBOResults && <LBOResultsView data={lboResult!} />}
        </div>
    )
}
