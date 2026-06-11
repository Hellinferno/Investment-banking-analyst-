import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
    fetchBuyers,
    fetchCurrentUser,
    fetchDeal,
    fetchProcessStatus,
    updateBuyerOutreach,
    updateDeal,
    type BuyerOutreach,
    type CurrentUserInfo,
    type Deal,
    type ProcessStatus,
} from '../lib/api'
import { ArrowLeft, FileText, Bot, Download, LayoutDashboard, CheckSquare } from 'lucide-react'
import DocumentsTab from '../components/workspace/DocumentsTab'
import AgentsTab from '../components/workspace/AgentsTab'
import OutputsTab from '../components/workspace/OutputsTab'
import TasksTab from '../components/workspace/TasksTab'
import MacroContextPanel from '../components/workspace/MacroContextPanel'
import RiskHeatmapPanel from '../components/workspace/RiskHeatmapPanel'
import LoadingScreen from '../components/ui/LoadingScreen'
import StatusBadge from '../components/ui/StatusBadge'

type TabKey = 'overview' | 'documents' | 'agents' | 'outputs' | 'tasks'

const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'Overview', icon: <LayoutDashboard size={14} /> },
    { key: 'documents', label: 'Data Room', icon: <FileText size={14} /> },
    { key: 'agents', label: 'Agents', icon: <Bot size={14} /> },
    { key: 'outputs', label: 'Outputs', icon: <Download size={14} /> },
    { key: 'tasks', label: 'Tasks', icon: <CheckSquare size={14} /> },
]

const PROCESS_STAGES = ['origination', 'teaser', 'nda', 'cim', 'ioi', 'management_meetings', 'loi', 'diligence', 'close']
const OUTREACH_STATUSES = ['not_contacted', 'teaser_sent', 'nda_signed', 'cim_sent', 'ioi_received', 'passed']

export default function DealWorkspace() {
    const { dealId } = useParams<{ dealId: string }>()
    const navigate = useNavigate()
    const [deal, setDeal] = useState<Deal | null>(null)
    const [currentUser, setCurrentUser] = useState<CurrentUserInfo | null>(null)
    const [processStatus, setProcessStatus] = useState<ProcessStatus | null>(null)
    const [buyers, setBuyers] = useState<BuyerOutreach[]>([])
    const [loading, setLoading] = useState(true)
    const [activeTab, setActiveTab] = useState<TabKey>('overview')

    const loadDeal = useCallback(async () => {
        if (!dealId) return
        try {
            const [d, user, status, buyerRows] = await Promise.all([
                fetchDeal(dealId),
                fetchCurrentUser(),
                fetchProcessStatus(dealId).catch(() => null),
                fetchBuyers(dealId).catch(() => []),
            ])
            setDeal(d)
            setCurrentUser(user)
            setProcessStatus(status)
            setBuyers(buyerRows)
        } catch {
            console.error('Failed to load deal')
        } finally {
            setLoading(false)
        }
    }, [dealId])

    useEffect(() => { loadDeal() }, [loadDeal])

    const handleProcessStageChange = async (stage: string) => {
        if (!dealId || !deal) return
        await updateDeal(dealId, { process_stage: stage })
        await loadDeal()
    }

    const handleBuyerStatusChange = async (buyerIdx: number, status: string) => {
        if (!dealId) return
        await updateBuyerOutreach(dealId, buyerIdx, status)
        const buyerRows = await fetchBuyers(dealId)
        setBuyers(buyerRows)
    }

    if (loading) return <LoadingScreen label="Loading Workspace" />

    if (!deal) {
        return (
            <div className="flex flex-col items-center justify-center" style={{ minHeight: '60vh', gap: 16 }}>
                <p style={{ fontSize: 13, color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em', textTransform: 'uppercase' }}>
                    Deal not found
                </p>
                <button className="btn-secondary" onClick={() => navigate('/')}>Return to Pipeline</button>
            </div>
        )
    }

    return (
        <div className="animate-fade-in" style={{ minHeight: '100%' }}>
            {/* Deal Header */}
            <div
                className="px-6 md:px-10 py-5"
                style={{ borderBottom: '1px solid var(--border-primary)' }}
            >
                <div className="flex items-start md:items-center justify-between flex-col md:flex-row gap-4 max-w-[1400px] mx-auto">
                    <div className="flex items-center gap-4">
                        <button
                            className="cursor-pointer flex items-center justify-center flex-shrink-0"
                            style={{
                                background: 'transparent',
                                border: '1px solid var(--border-primary)',
                                color: 'var(--text-muted)',
                                padding: 7,
                                borderRadius: 'var(--radius-sm)',
                                transition: 'color 0.15s',
                            }}
                            onClick={() => navigate('/')}
                            title="Back to Pipeline"
                            onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)' }}
                            onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
                        >
                            <ArrowLeft size={14} />
                        </button>
                        <div>
                            <h1 style={{ fontSize: 20, fontWeight: 600, color: 'var(--text-primary)', letterSpacing: '-0.02em', margin: 0, lineHeight: 1.3 }}>
                                {deal.name}
                            </h1>
                            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2, fontFamily: "'JetBrains Mono', monospace" }}>
                                {deal.company_name} · {deal.deal_type.toUpperCase()}
                            </p>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-2">
                        {currentUser && <StatusBadge variant="warning" dot>{currentUser.role}</StatusBadge>}
                        <StatusBadge variant="accent">{deal.deal_type}</StatusBadge>
                        <StatusBadge variant={deal.deal_stage === 'active' ? 'positive' : deal.deal_stage === 'preliminary' ? 'accent' : 'default'} dot>{deal.deal_stage}</StatusBadge>
                    </div>
                </div>
            </div>

            {/* Tab Navigation */}
            <div style={{ borderBottom: '1px solid var(--border-primary)' }}>
                <div className="flex px-6 md:px-10 max-w-[1400px] mx-auto overflow-x-auto">
                    {TABS.map(tab => (
                        <button
                            key={tab.key}
                            className="flex items-center gap-2 cursor-pointer"
                            style={{
                                padding: '12px 18px',
                                fontSize: 12,
                                fontWeight: activeTab === tab.key ? 600 : 400,
                                color: activeTab === tab.key ? 'var(--text-primary)' : 'var(--text-muted)',
                                background: 'transparent',
                                border: 'none',
                                borderBottom: activeTab === tab.key ? '1px solid var(--text-primary)' : '1px solid transparent',
                                whiteSpace: 'nowrap',
                                transition: 'color 0.15s',
                            }}
                            onClick={() => setActiveTab(tab.key)}
                            onMouseEnter={e => { if (activeTab !== tab.key) e.currentTarget.style.color = 'var(--text-secondary)' }}
                            onMouseLeave={e => { if (activeTab !== tab.key) e.currentTarget.style.color = 'var(--text-muted)' }}
                        >
                            {tab.icon} {tab.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Tab Content */}
            <div className="p-6 md:p-10 max-w-[1400px] mx-auto">
                {activeTab === 'overview' && (
                    <div className="animate-fade-in">
                        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
                            {[
                                { label: 'Industry', value: deal.industry },
                                { label: 'Internal Phase', value: deal.deal_stage },
                                { label: 'Process Stage', value: deal.process_stage?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'N/A' },
                                { label: 'Stage Updated', value: deal.stage_last_updated ? new Date(deal.stage_last_updated).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A' },
                                { label: 'Created', value: new Date(deal.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) },
                            ].map((item, i) => (
                                <div
                                    key={i}
                                    className="glass-card"
                                    style={{ padding: '20px 24px', animation: `fadeInUp 0.3s ease ${i * 60}ms both` }}
                                >
                                    <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10, fontFamily: "'JetBrains Mono', monospace" }}>
                                        {item.label}
                                    </div>
                                    <div style={{ fontSize: 18, fontWeight: 500, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
                                        {item.value}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-8">
                            <div className="glass-card" style={{ padding: '20px 24px' }}>
                                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10, fontFamily: "'JetBrains Mono', monospace" }}>
                                    Process Stage
                                </div>
                                <select
                                    className="input-field"
                                    value={deal.process_stage || 'origination'}
                                    onChange={e => handleProcessStageChange(e.target.value)}
                                >
                                    {PROCESS_STAGES.map(stage => (
                                        <option key={stage} value={stage}>{stage.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</option>
                                    ))}
                                </select>
                                {processStatus && (
                                    <div style={{ marginTop: 12, fontSize: 12, color: processStatus.ready_for_next_stage ? 'var(--positive)' : 'var(--warning)' }}>
                                        {processStatus.ready_for_next_stage ? `Ready for ${processStatus.next_stage.replace(/_/g, ' ')}` : `${processStatus.blockers.length} blocker(s)`}
                                    </div>
                                )}
                            </div>

                            <div className="glass-card lg:col-span-2" style={{ padding: '20px 24px' }}>
                                <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10, fontFamily: "'JetBrains Mono', monospace" }}>
                                    Stage Blockers
                                </div>
                                {processStatus?.blockers?.length ? (
                                    <div style={{ display: 'grid', gap: 8 }}>
                                        {processStatus.blockers.map((blocker, idx) => (
                                            <div key={idx} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                                                {blocker}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>No blockers recorded.</div>
                                )}
                            </div>
                        </div>

                        <div className="glass-card" style={{ padding: '20px 24px', marginBottom: 8 }}>
                            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 14, fontFamily: "'JetBrains Mono', monospace" }}>
                                Buyer Outreach
                            </div>
                            {buyers.length === 0 ? (
                                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Run Buyer Universe to populate outreach tracking.</div>
                            ) : (
                                <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-3">
                                    {OUTREACH_STATUSES.map(status => (
                                        <div key={status} style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', padding: 10, minHeight: 120 }}>
                                            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 8 }}>
                                                {status.replace(/_/g, ' ')}
                                            </div>
                                            <div style={{ display: 'grid', gap: 8 }}>
                                                {buyers.filter(b => b.outreach_status === status).map(buyer => (
                                                    <div key={buyer.id} style={{ padding: 8, border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-surface)' }}>
                                                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>{buyer.name}</div>
                                                        <select
                                                            className="input-field"
                                                            style={{ fontSize: 11, padding: '6px 8px' }}
                                                            value={buyer.outreach_status}
                                                            onChange={e => handleBuyerStatusChange(buyer.buyer_idx, e.target.value)}
                                                        >
                                                            {OUTREACH_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                                                        </select>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {deal.notes && (
                            <div className="glass-card" style={{ padding: '20px 24px' }}>
                                <div style={{ fontSize: 10, fontWeight: 500, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 10, fontFamily: "'JetBrains Mono', monospace" }}>
                                    Internal Notes
                                </div>
                                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, maxWidth: '80ch', margin: 0, whiteSpace: 'pre-wrap' }}>
                                    {deal.notes}
                                </p>
                            </div>
                        )}

                        {/* WorldMonitor Intelligence Panels */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-8">
                            <MacroContextPanel />
                            <RiskHeatmapPanel />
                        </div>
                    </div>
                )}

                {activeTab === 'documents' && <div className="animate-fade-in"><DocumentsTab dealId={dealId!} /></div>}
                {activeTab === 'agents' && <div className="animate-fade-in"><AgentsTab dealId={dealId!} /></div>}
                {activeTab === 'outputs' && <div className="animate-fade-in"><OutputsTab dealId={dealId!} /></div>}
                {activeTab === 'tasks' && <div className="animate-fade-in"><TasksTab dealId={dealId!} /></div>}
            </div>
        </div>
    )
}
