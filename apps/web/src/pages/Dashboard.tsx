import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchDeals, createDeal, deleteDeal, type Deal, type DealCreatePayload } from '../lib/api'
import { Plus, Search, Trash2, X, ChevronRight } from 'lucide-react'

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

export default function Dashboard() {
    const navigate = useNavigate()
    const [deals, setDeals] = useState<Deal[]>([])
    const [loading, setLoading] = useState(true)
    const [search, setSearch] = useState('')
    const [showModal, setShowModal] = useState(false)
    const [form, setForm] = useState<DealCreatePayload>({
        name: '', company_name: '', deal_type: 'ma', industry: 'Technology', deal_stage: 'preliminary'
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
            setForm({ name: '', company_name: '', deal_type: 'ma', industry: 'Technology', deal_stage: 'preliminary' })
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
        <div style={{ minHeight: '100vh', padding: '24px 32px' }}>
            {/* Header */}
            <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28, borderBottom: '1px solid #222', paddingBottom: 20 }}>
                <div>
                    <h1 style={{ fontSize: 20, fontWeight: 700, margin: 0, letterSpacing: '0.08em', color: '#ff6600' }}>
                        AIBAA
                    </h1>
                    <p style={{ color: '#666', fontSize: 12, margin: '4px 0 0', letterSpacing: '0.02em' }}>
                        AI Investment Banking Analyst Agent
                    </p>
                </div>
                <button className="btn-primary" onClick={() => setShowModal(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Plus size={14} /> NEW DEAL
                </button>
            </header>

            {/* Stats Strip */}
            <div style={{ display: 'flex', gap: 1, marginBottom: 24, background: '#111', border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                {[
                    { label: 'TOTAL', value: deals.length },
                    { label: 'ACTIVE', value: deals.filter(d => d.deal_stage === 'preliminary' || d.deal_stage === 'active').length },
                    { label: 'DOCS', value: deals.reduce((s, d) => s + (d.document_count || 0), 0) },
                    { label: 'OUTPUTS', value: deals.reduce((s, d) => s + (d.output_count || 0), 0) },
                ].map((stat, i) => (
                    <div key={i} style={{
                        flex: 1, padding: '12px 16px', textAlign: 'center',
                        borderRight: i < 3 ? '1px solid #222' : 'none'
                    }}>
                        <div style={{ fontSize: 20, fontWeight: 700, fontFamily: "'SF Mono', Consolas, monospace", color: '#fff' }}>
                            {stat.value}
                        </div>
                        <div style={{ fontSize: 9, color: '#666', letterSpacing: '0.1em', fontWeight: 700, marginTop: 2 }}>
                            {stat.label}
                        </div>
                    </div>
                ))}
            </div>

            {/* Search */}
            <div style={{ position: 'relative', marginBottom: 20, maxWidth: 360 }}>
                <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#666' }} />
                <input
                    className="input-field"
                    placeholder="Search deals..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    style={{ paddingLeft: 34, fontFamily: "'Inter', system-ui, sans-serif" }}
                />
            </div>

            {/* Deal List */}
            {loading ? (
                <div style={{ textAlign: 'center', padding: 60, color: '#666' }}>
                    <div className="spinner" style={{ margin: '0 auto 12px' }} />
                    Loading...
                </div>
            ) : filtered.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 60, color: '#666', border: '1px solid #222', borderRadius: 3 }}>
                    <p style={{ fontSize: 14, margin: '0 0 4px' }}>No deals found</p>
                    <p style={{ fontSize: 12, color: '#444' }}>Create a deal to get started</p>
                </div>
            ) : (
                <div style={{ border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                    {filtered.map((deal, i) => (
                        <div
                            key={deal.id}
                            onClick={() => navigate(`/deals/${deal.id}`)}
                            style={{
                                display: 'flex', alignItems: 'center', padding: '14px 18px',
                                borderBottom: i < filtered.length - 1 ? '1px solid #151515' : 'none',
                                cursor: 'pointer', transition: 'background 0.1s',
                                background: 'transparent',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.background = '#0a0a0a')}
                            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                        >
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 14, fontWeight: 600, color: '#fff', marginBottom: 2 }}>{deal.name}</div>
                                <div style={{ fontSize: 12, color: '#666' }}>{deal.company_name}</div>
                            </div>
                            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginRight: 16 }}>
                                <span className="badge badge-indigo">{deal.deal_type}</span>
                                <span className="badge badge-emerald">{deal.deal_stage}</span>
                            </div>
                            <span style={{ fontSize: 11, color: '#444', marginRight: 12, fontFamily: "'SF Mono', Consolas, monospace" }}>
                                {new Date(deal.created_at).toLocaleDateString()}
                            </span>
                            <button
                                className="btn-ghost"
                                style={{ padding: 4, border: 'none', marginRight: 8 }}
                                onClick={e => { e.stopPropagation(); handleDelete(deal.id) }}
                            >
                                <Trash2 size={13} />
                            </button>
                            <ChevronRight size={14} style={{ color: '#333' }} />
                        </div>
                    ))}
                </div>
            )}

            {/* Create Modal */}
            {showModal && (
                <div className="modal-overlay" onClick={() => setShowModal(false)}>
                    <div className="modal-content" onClick={e => e.stopPropagation()}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
                            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, letterSpacing: '0.02em' }}>NEW DEAL</h2>
                            <button className="btn-ghost" style={{ padding: 4, border: 'none' }} onClick={() => setShowModal(false)}>
                                <X size={16} />
                            </button>
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                            <div>
                                <label style={{ fontSize: 10, color: '#666', display: 'block', marginBottom: 5, letterSpacing: '0.08em', fontWeight: 700, textTransform: 'uppercase' }}>Deal Name</label>
                                <input className="input-field" placeholder="Project Alpha" value={form.name}
                                    onChange={e => setForm(p => ({ ...p, name: e.target.value }))} />
                            </div>
                            <div>
                                <label style={{ fontSize: 10, color: '#666', display: 'block', marginBottom: 5, letterSpacing: '0.08em', fontWeight: 700, textTransform: 'uppercase' }}>Company Name</label>
                                <input className="input-field" placeholder="Acme Corp" value={form.company_name}
                                    onChange={e => setForm(p => ({ ...p, company_name: e.target.value }))} />
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                                <div>
                                    <label style={{ fontSize: 10, color: '#666', display: 'block', marginBottom: 5, letterSpacing: '0.08em', fontWeight: 700, textTransform: 'uppercase' }}>Type</label>
                                    <select className="input-field" value={form.deal_type}
                                        onChange={e => setForm(p => ({ ...p, deal_type: e.target.value }))}>
                                        {DEAL_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                                    </select>
                                </div>
                                <div>
                                    <label style={{ fontSize: 10, color: '#666', display: 'block', marginBottom: 5, letterSpacing: '0.08em', fontWeight: 700, textTransform: 'uppercase' }}>Industry</label>
                                    <select className="input-field" value={form.industry}
                                        onChange={e => setForm(p => ({ ...p, industry: e.target.value }))}>
                                        {INDUSTRIES.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                                    </select>
                                </div>
                            </div>
                            <div>
                                <label style={{ fontSize: 10, color: '#666', display: 'block', marginBottom: 5, letterSpacing: '0.08em', fontWeight: 700, textTransform: 'uppercase' }}>Notes</label>
                                <textarea className="input-field" rows={2} placeholder="Optional notes..."
                                    value={form.notes || ''}
                                    onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                                    style={{ resize: 'vertical' }} />
                            </div>
                        </div>

                        <div style={{ marginTop: 24, borderTop: '1px solid #222', paddingTop: 18 }}>
                            {createError && (
                                <div style={{ color: '#ff4444', fontSize: 12, padding: '6px 10px', background: 'rgba(255,68,68,0.08)', border: '1px solid rgba(255,68,68,0.25)', borderRadius: 3, marginBottom: 12 }}>
                                    {createError}
                                </div>
                            )}
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
                                <button className="btn-ghost" onClick={() => { setShowModal(false); setCreateError(null) }}>Cancel</button>
                                <button className="btn-primary" onClick={handleCreate} disabled={creating || !form.name.trim() || !form.company_name.trim()}>
                                    {creating ? <><div className="spinner" style={{ width: 12, height: 12 }} /> Creating...</> : 'CREATE'}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
