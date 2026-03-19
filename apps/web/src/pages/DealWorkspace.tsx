import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchCurrentUser, fetchDeal, type CurrentUserInfo, type Deal } from '../lib/api'
import { ArrowLeft, FileText, Bot, Download, LayoutDashboard, CheckSquare } from 'lucide-react'
import DocumentsTab from '../components/workspace/DocumentsTab'
import AgentsTab from '../components/workspace/AgentsTab'
import OutputsTab from '../components/workspace/OutputsTab'
import TasksTab from '../components/workspace/TasksTab'

type TabKey = 'overview' | 'documents' | 'agents' | 'outputs' | 'tasks'

const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: 'Overview', icon: <LayoutDashboard size={13} /> },
    { key: 'documents', label: 'Data Room', icon: <FileText size={13} /> },
    { key: 'agents', label: 'Agents', icon: <Bot size={13} /> },
    { key: 'outputs', label: 'Outputs', icon: <Download size={13} /> },
    { key: 'tasks', label: 'Tasks', icon: <CheckSquare size={13} /> },
]

export default function DealWorkspace() {
    const { dealId } = useParams<{ dealId: string }>()
    const navigate = useNavigate()
    const [deal, setDeal] = useState<Deal | null>(null)
    const [currentUser, setCurrentUser] = useState<CurrentUserInfo | null>(null)
    const [loading, setLoading] = useState(true)
    const [activeTab, setActiveTab] = useState<TabKey>('overview')

    const loadDeal = useCallback(async () => {
        if (!dealId) return
        try {
            const [d, user] = await Promise.all([
                fetchDeal(dealId),
                fetchCurrentUser(),
            ])
            setDeal(d)
            setCurrentUser(user)
        } catch {
            console.error('Failed to load deal')
        } finally {
            setLoading(false)
        }
    }, [dealId])

    useEffect(() => { loadDeal() }, [loadDeal])

    if (loading) {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
                <div className="spinner" style={{ width: 24, height: 24 }} />
            </div>
        )
    }

    if (!deal) {
        return (
            <div style={{ textAlign: 'center', padding: 80 }}>
                <p style={{ color: '#666' }}>Deal not found</p>
                <button className="btn-ghost" onClick={() => navigate('/')}>Go Home</button>
            </div>
        )
    }

    return (
        <div style={{ minHeight: '100vh' }}>
            {/* Top Bar */}
            <div style={{
                padding: '12px 28px',
                borderBottom: '1px solid #222',
                display: 'flex', alignItems: 'center', gap: 14,
                background: '#000'
            }}>
                <button className="btn-ghost" style={{ padding: 4, border: 'none' }} onClick={() => navigate('/')}>
                    <ArrowLeft size={16} />
                </button>
                <div style={{ flex: 1 }}>
                    <h1 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: '#fff' }}>{deal.name}</h1>
                    <p style={{ color: '#555', fontSize: 11, margin: 0 }}>{deal.company_name} · {deal.deal_type}</p>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    {currentUser && <span className="badge badge-amber">{currentUser.role}</span>}
                    <span className="badge badge-indigo">{deal.deal_type}</span>
                    <span className="badge badge-emerald">{deal.deal_stage}</span>
                </div>
            </div>

            {/* Tab Nav */}
            <div style={{
                display: 'flex', gap: 0, padding: '0 28px',
                borderBottom: '1px solid #222',
                background: '#000'
            }}>
                {TABS.map(tab => (
                    <button
                        key={tab.key}
                        className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
                        onClick={() => setActiveTab(tab.key)}
                        style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                        {tab.icon} {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab Content */}
            <div style={{ padding: '24px 28px' }}>
                {activeTab === 'overview' && (
                    <div className="animate-fade-in">
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1, marginBottom: 20, border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                            {[
                                { label: 'INDUSTRY', value: deal.industry },
                                { label: 'STAGE', value: deal.deal_stage },
                                { label: 'CREATED', value: new Date(deal.created_at).toLocaleDateString() },
                            ].map((item, i) => (
                                <div key={i} style={{
                                    padding: '16px 18px', background: '#0a0a0a',
                                    borderRight: i < 2 ? '1px solid #222' : 'none'
                                }}>
                                    <div style={{ fontSize: 9, color: '#555', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 6 }}>{item.label}</div>
                                    <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>{item.value}</div>
                                </div>
                            ))}
                        </div>
                        {deal.notes && (
                            <div style={{ padding: '14px 18px', background: '#0a0a0a', border: '1px solid #222', borderRadius: 3 }}>
                                <div style={{ fontSize: 9, color: '#555', letterSpacing: '0.1em', fontWeight: 700, marginBottom: 6 }}>NOTES</div>
                                <p style={{ color: '#aaa', fontSize: 13, margin: 0, lineHeight: 1.6 }}>{deal.notes}</p>
                            </div>
                        )}
                    </div>
                )}
                {activeTab === 'documents' && <DocumentsTab dealId={dealId!} />}
                {activeTab === 'agents' && <AgentsTab dealId={dealId!} />}
                {activeTab === 'outputs' && <OutputsTab dealId={dealId!} />}
                {activeTab === 'tasks' && <TasksTab dealId={dealId!} />}
            </div>
        </div>
    )
}
