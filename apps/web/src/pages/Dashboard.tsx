import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchDeals, createDeal, deleteDeal, type Deal, type DealCreatePayload } from '../lib/api'
import { Plus, Search, Trash2, ArrowUpRight, Briefcase } from 'lucide-react'
import KPICard from '../components/ui/KPICard'
import EmptyState from '../components/ui/EmptyState'
import Modal from '../components/ui/Modal'

const DEAL_TYPES: { label: string; value: string }[] = [
    { label: 'M&A',          value: 'ma' },
    { label: 'IPO',          value: 'ipo' },
    { label: 'LBO',          value: 'lbo' },
    { label: 'Debt Raise',   value: 'debt_raise' },
    { label: 'Equity Raise', value: 'equity_raise' },
    { label: 'Restructuring',value: 'restructuring' },
    { label: 'Other',        value: 'other' },
]
const INDUSTRIES = ['Technology', 'Healthcare', 'Financial Services', 'Consumer', 'Energy', 'Industrials', 'Real Estate', 'Telecom', 'Other']

const STAGE_VARIANT: Record<string, 'positive' | 'warning' | 'accent' | 'default'> = {
    active: 'positive',
    preliminary: 'accent',
    closed: 'default',
}

export default function Dashboard() {
    const navigate = useNavigate()
    const [deals, setDeals] = useState<Deal[]>([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [showModal, setShowModal] = useState(false)
    const [form, setForm] = useState<DealCreatePayload>({
        name: '', company_name: '', deal_type: 'ma', industry: 'Technology', deal_stage: 'preliminary', process_stage: 'nda_negotiation'
    })
    const [creating, setCreating] = useState(false)
    const [createError, setCreateError] = useState<string | null>(null)

    const load = useCallback(async () => {
        try {
            const data = await fetchDeals()
            setDeals(data)
        } catch (err) {
            console.error('Failed to load deals', err)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => { load() }, [load])

    const handleCreate = async () => {
        if (!form.name.trim() || !form.company_name.trim()) return
        setCreating(true)
        setCreateError(null)
        try {
            const newDeal = await createDeal(form)
            setShowModal(false)
            setForm({ name: '', company_name: '', deal_type: 'ma', industry: 'Technology', deal_stage: 'preliminary', process_stage: 'nda_negotiation' })
            setCreateError(null)
            navigate(`/deals/${newDeal.id}`)
        } catch (err: unknown) {
            const axErr = err as { response?: { data?: { detail?: string } }; message?: string }
            const msg = axErr?.response?.data?.detail || axErr?.message || 'Failed to create deal'
            setCreateError(typeof msg === 'string' ? msg : JSON.stringify(msg))
            console.error('Create deal failed', err)
        } finally {
            setCreating(false)
        }
    }

    const handleDelete = async (id: string) => {
        try {
            await deleteDeal(id)
            setDeals(prev => prev.filter(d => d.id !== id))
        } catch (err) {
            console.error('Delete failed', err)
        }
    }

    const filtered = deals.filter(d =>
        d.name.toLowerCase().includes(search.toLowerCase()) ||
        d.company_name.toLowerCase().includes(search.toLowerCase())
    )

    return (
        <div className="p-6 md:p-10 max-w-[1400px] mx-auto">
            {/* Page Header */}
            <div
                className="flex flex-col md:flex-row md:items-end justify-between mb-8 animate-fade-in-up"
                style={{ animationDelay: '0ms' }}
            >
                <div>
                    <h1
                        style={{
                            fontSize: 28,
                            fontWeight: 700,
                            color: 'var(--text-primary)',
                            letterSpacing: '-0.03em',
                            marginBottom: 4,
                        }}
                    >
                        Deal Pipeline
                    </h1>
                    <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                        Manage and track your active investment banking engagements
                    </p>
                </div>
                <button
                    className="btn-primary group flex items-center gap-2 mt-4 md:mt-0"
                    onClick={() => setShowModal(true)}
                >
                    <Plus size={16} className="group-hover:rotate-90 transition-transform duration-300" />
                    New Deal
                </button>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-10">
                <KPICard label="Total Deals" value={deals.length} delay={50} />
                <KPICard
                    label="Active Pipeline"
                    value={deals.filter(d => d.deal_stage === 'preliminary' || d.deal_stage === 'active').length}
                    trend="up"
                    delay={100}
                />
                <KPICard
                    label="Indexed Documents"
                    value={deals.reduce((s, d) => s + (d.document_count || 0), 0)}
                    delay={150}
                />
                <KPICard
                    label="AI Outputs"
                    value={deals.reduce((s, d) => s + (d.output_count || 0), 0)}
                    trend="up"
                    delay={200}
                />
            </div>

            {/* Pipeline Section */}
            <div
                className="glass-card-static animate-fade-in-up"
                style={{ overflow: 'hidden', animationDelay: '150ms' }}
            >
                {/* Section Header */}
                <div
                    className="flex flex-col md:flex-row md:items-center justify-between gap-4 px-6 py-4"
                    style={{ borderBottom: '1px solid var(--border-glass)' }}
                >
                    <h2 style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                        All Deals
                        <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 400, marginLeft: 8 }}>
                            {filtered.length} {filtered.length === 1 ? 'deal' : 'deals'}
                        </span>
                    </h2>
                    <div className="relative w-full md:w-72">
                        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--text-muted)' }} />
                        <input
                            className="input-field"
                            style={{ paddingLeft: 34, fontSize: 12, background: 'var(--bg-surface)' }}
                            placeholder="Search deals..."
                            value={search}
                            onChange={e => setSearch(e.target.value)}
                        />
                    </div>
                </div>

                {/* Deal List */}
                {loading ? (
                    <div className="py-20 flex flex-col items-center justify-center" style={{ gap: 12 }}>
                        <div className="spinner" />
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.08em', textTransform: 'uppercase', fontFamily: "'JetBrains Mono', monospace" }}>
                            Loading deals
                        </span>
                    </div>
                ) : filtered.length === 0 ? (
                    <div className="p-6">
                        <EmptyState
                            icon={<Briefcase size={22} />}
                            title="No deals found"
                            subtitle={search ? 'Try adjusting your search query' : 'Create your first deal to get started'}
                            action={
                                !search ? (
                                    <button className="btn-primary" onClick={() => setShowModal(true)}>
                                        <Plus size={14} style={{ marginRight: 6 }} /> Create First Deal
                                    </button>
                                ) : undefined
                            }
                        />
                    </div>
                ) : (
                    <div>
                        {filtered.map((deal, idx) => (
                            <div
                                key={deal.id}
                                onClick={() => navigate(`/deals/${deal.id}`)}
                                className="group flex flex-col md:flex-row md:items-center px-6 py-4 cursor-pointer transition-all duration-200"
                                style={{
                                    borderBottom: idx < filtered.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                                    background: 'transparent',
                                    animation: `fadeInUp 0.3s ease ${idx * 30}ms both`,
                                }}
                                onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
                                onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
                            >
                                {/* Deal Info */}
                                <div className="flex-1 min-w-0 mb-3 md:mb-0">
                                    <div className="flex items-center gap-3 mb-1">
                                        <div
                                            style={{
                                                fontSize: 14,
                                                fontWeight: 600,
                                                color: 'var(--text-primary)',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap',
                                            }}
                                        >
                                            {deal.name}
                                        </div>
                                    </div>
                                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                                        {deal.company_name}
                                    </div>
                                </div>

                                {/* Badges & Actions */}
                                <div className="flex flex-wrap md:flex-nowrap gap-2 items-center md:justify-end md:w-auto">
                                    <span className="badge badge-indigo">{deal.deal_type}</span>
                                    <span className={`badge badge-${STAGE_VARIANT[deal.deal_stage] || 'default'}`}>
                                        {deal.deal_stage}
                                    </span>
                                    <span
                                        className="hidden md:block"
                                        style={{
                                            fontSize: 11,
                                            color: 'var(--text-muted)',
                                            fontFamily: "'JetBrains Mono', monospace",
                                            width: 90,
                                            textAlign: 'right',
                                            flexShrink: 0,
                                        }}
                                    >
                                        {new Date(deal.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                                    </span>
                                    <div className="flex items-center gap-1 ml-auto md:ml-3">
                                        <button
                                            className="cursor-pointer flex items-center justify-center"
                                            style={{
                                                background: 'transparent',
                                                border: 'none',
                                                color: 'var(--text-muted)',
                                                padding: 6,
                                                borderRadius: 'var(--radius-sm)',
                                                transition: 'all 0.2s',
                                            }}
                                            onClick={e => { e.stopPropagation(); handleDelete(deal.id) }}
                                            title="Delete Deal"
                                            onMouseEnter={e => {
                                                e.currentTarget.style.color = 'var(--negative)';
                                                e.currentTarget.style.background = 'var(--negative-bg)';
                                            }}
                                            onMouseLeave={e => {
                                                e.currentTarget.style.color = 'var(--text-muted)';
                                                e.currentTarget.style.background = 'transparent';
                                            }}
                                        >
                                            <Trash2 size={14} />
                                        </button>
                                        <div
                                            style={{
                                                padding: 6,
                                                color: 'var(--text-muted)',
                                                transition: 'color 0.2s',
                                            }}
                                            className="group-hover:!text-[var(--accent-light)]"
                                        >
                                            <ArrowUpRight size={16} />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Create Deal Modal */}
            <Modal
                open={showModal}
                onClose={() => { setShowModal(false); setCreateError(null) }}
                title="Create New Deal"
                footer={
                    <>
                        <button
                            className="btn-ghost"
                            onClick={() => { setShowModal(false); setCreateError(null) }}
                        >
                            Cancel
                        </button>
                        <button
                            className="btn-primary flex items-center justify-center"
                            style={{ minWidth: 130 }}
                            onClick={handleCreate}
                            disabled={creating || !form.name.trim() || !form.company_name.trim()}
                        >
                            {creating ? <div className="spinner" style={{ width: 16, height: 16, borderTopColor: '#fff' }} /> : 'Create Deal'}
                        </button>
                    </>
                }
            >
                <div className="flex flex-col gap-5">
                    {createError && (
                        <div
                            style={{
                                background: 'var(--negative-bg)',
                                border: '1px solid var(--negative-border)',
                                borderRadius: 'var(--radius-sm)',
                                padding: '10px 14px',
                                fontSize: 12,
                                color: 'var(--negative)',
                            }}
                        >
                            {createError}
                        </div>
                    )}

                    <div>
                        <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                            Deal Name *
                        </label>
                        <input
                            className="input-field"
                            placeholder="Project Alpha"
                            value={form.name}
                            onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                            autoFocus
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                            Company Name *
                        </label>
                        <input
                            className="input-field"
                            placeholder="Acme Corp"
                            value={form.company_name}
                            onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))}
                        />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                                Transaction Type
                            </label>
                            <select
                                className="input-field"
                                value={form.deal_type}
                                onChange={e => setForm(p => ({ ...p, deal_type: e.target.value }))}
                            >
                                {DEAL_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                                Industry
                            </label>
                            <select
                                className="input-field"
                                value={form.industry}
                                onChange={e => setForm(p => ({ ...p, industry: e.target.value }))}
                            >
                                {INDUSTRIES.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                            </select>
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                                Process Stage
                            </label>
                            <select
                                className="input-field"
                                value={form.process_stage || 'nda_negotiation'}
                                onChange={e => setForm(p => ({ ...p, process_stage: e.target.value }))}
                            >
                                <option value="nda_negotiation">NDA Negotiation</option>
                                <option value="nda_signed">NDA Signed</option>
                                <option value="teaser_sent">Teaser Sent</option>
                                <option value="cim_sent">CIM Sent</option>
                                <option value="io_received">IO Received</option>
                                <option value="loi_signed">LOI Signed</option>
                                <option value="exclusivity">Exclusivity</option>
                                <option value="definitive_agreement">Definitive Agreement</option>
                            </select>
                        </div>
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 6, fontFamily: "'JetBrains Mono', monospace" }}>
                            Internal Notes
                        </label>
                        <textarea
                            className="input-field"
                            style={{ minHeight: 80, resize: 'vertical' }}
                            placeholder="Strategy background, key stakeholders..."
                            value={form.notes || ''}
                            onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                        />
                    </div>
                </div>
            </Modal>
        </div>
    )
}
