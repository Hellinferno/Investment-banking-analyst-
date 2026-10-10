import { useEffect, useState, type FormEvent, type MouseEvent } from 'react'
import { AlertCircle, ExternalLink, FileText, Pencil, Plus, Save, Search, Trash2 } from 'lucide-react'
import {
    createResearchReviewItem,
    deleteResearchReviewItem,
    exportResearchReviewBoard,
    fetchResearchReviewItems,
    updateResearchReviewItem,
    type ResearchEvidence,
    type ResearchReport,
    type ResearchReviewItem,
    type ResearchReviewItemPayload,
} from '../../lib/api'

interface Props {
    dealId: string
    runId: string
    evidence: ResearchEvidence
    report?: ResearchReport | null
}

const emptyDraft = (sourceId?: string): ResearchReviewItemPayload => ({
    kind: 'observation',
    title: '',
    note: '',
    next_action: '',
    source_ids: sourceId ? [sourceId] : [],
    status: 'unreviewed',
})

function requestError(error: unknown): string {
    const response = (error as { response?: { data?: { detail?: unknown } } })?.response
    const detail = response?.data?.detail
    if (typeof detail === 'string') return detail
    return error instanceof Error ? error.message : 'The review action could not be completed.'
}

export default function ResearchResultsView({ dealId, runId, evidence, report }: Props) {
    const [filter, setFilter] = useState('')
    const [reviewItems, setReviewItems] = useState<ResearchReviewItem[]>([])
    const [draft, setDraft] = useState<ResearchReviewItemPayload>(emptyDraft())
    const [editingId, setEditingId] = useState<string | null>(null)
    const [reviewBusy, setReviewBusy] = useState(false)
    const [reviewMessage, setReviewMessage] = useState('')
    const [reviewError, setReviewError] = useState('')
    const sources = evidence.sources.filter(source =>
        `${source.title} ${source.publisher} ${source.purpose}`.toLowerCase().includes(filter.toLowerCase()))
    const incomplete = evidence.status !== 'complete'

    useEffect(() => {
        let cancelled = false
        setReviewItems([])
        setDraft(emptyDraft())
        setEditingId(null)
        setReviewMessage('')
        setReviewError('')
        fetchResearchReviewItems(dealId, runId)
            .then(items => { if (!cancelled) setReviewItems(items) })
            .catch(error => { if (!cancelled) setReviewError(requestError(error)) })
        return () => { cancelled = true }
    }, [dealId, runId])

    const revealSource = (event: MouseEvent<HTMLAnchorElement>, sourceId: string) => {
        event.preventDefault()
        setFilter('')
        window.requestAnimationFrame(() => {
            const target = document.getElementById(`source-${sourceId}`)
            target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
            target?.focus({ preventScroll: true })
        })
    }

    const startDraft = (sourceId?: string) => {
        setEditingId(null)
        setDraft(emptyDraft(sourceId))
        setReviewMessage('')
        window.requestAnimationFrame(() => document.getElementById('review-form-title')?.focus())
    }

    const startEdit = (item: ResearchReviewItem) => {
        setEditingId(item.id)
        setDraft({
            kind: item.kind,
            title: item.title,
            note: item.note,
            next_action: item.next_action || '',
            source_ids: [...item.source_ids],
            status: item.status,
        })
        setReviewMessage('')
        window.requestAnimationFrame(() => document.getElementById('review-form-title')?.focus())
    }

    const toggleSource = (sourceId: string) => {
        setDraft(current => {
            const selected = current.source_ids.includes(sourceId)
            if (!selected && current.source_ids.length >= 8) return current
            return {
                ...current,
                source_ids: selected
                    ? current.source_ids.filter(id => id !== sourceId)
                    : [...current.source_ids, sourceId],
            }
        })
    }

    const saveReviewItem = async (event: FormEvent) => {
        event.preventDefault()
        setReviewError('')
        setReviewMessage('')
        if (!draft.title.trim() || draft.source_ids.length === 0) {
            setReviewError('Add a title and select at least one source from this research run.')
            return
        }
        setReviewBusy(true)
        try {
            if (editingId) {
                const saved = await updateResearchReviewItem(dealId, runId, editingId, draft)
                setReviewItems(items => items.map(item => item.id === saved.id ? saved : item))
                setReviewMessage('Review item updated.')
            } else {
                const saved = await createResearchReviewItem(dealId, runId, draft)
                setReviewItems(items => [...items, saved])
                setReviewMessage('Review item saved to this research run.')
            }
            setEditingId(null)
            setDraft(emptyDraft())
        } catch (error) {
            setReviewError(requestError(error))
        } finally {
            setReviewBusy(false)
        }
    }

    const changeStatus = async (item: ResearchReviewItem, status: ResearchReviewItem['status']) => {
        setReviewBusy(true)
        setReviewError('')
        try {
            const saved = await updateResearchReviewItem(dealId, runId, item.id, { status })
            setReviewItems(items => items.map(current => current.id === saved.id ? saved : current))
            setReviewMessage('Review status saved.')
        } catch (error) {
            setReviewError(requestError(error))
        } finally {
            setReviewBusy(false)
        }
    }

    const removeReviewItem = async (item: ResearchReviewItem) => {
        if (!window.confirm(`Remove “${item.title}” from this review board?`)) return
        setReviewBusy(true)
        setReviewError('')
        try {
            await deleteResearchReviewItem(dealId, runId, item.id)
            setReviewItems(items => items.filter(current => current.id !== item.id))
            if (editingId === item.id) {
                setEditingId(null)
                setDraft(emptyDraft())
            }
            setReviewMessage('Review item removed.')
        } catch (error) {
            setReviewError(requestError(error))
        } finally {
            setReviewBusy(false)
        }
    }

    const exportBoard = async () => {
        setReviewBusy(true)
        setReviewError('')
        try {
            const result = await exportResearchReviewBoard(dealId, runId)
            setReviewMessage(`Version ${result.version} PDF and JSON drafts were created in Outputs.`)
        } catch (error) {
            setReviewError(requestError(error))
        } finally {
            setReviewBusy(false)
        }
    }

    return (
        <section className="research-results" aria-label="Research results">
            <div className="research-result-header">
                <div>
                    <h2>{report?.title || 'Search evidence'}</h2>
                    <p>
                        {evidence.company_name} · {evidence.industry}
                        {evidence.official_domain ? ` · ${evidence.official_domain}` : ''}
                        {evidence.country ? ` · ${evidence.country.toUpperCase()}` : ''}
                        {' · '}Retrieved {new Date(evidence.collected_at).toLocaleString()}
                    </p>
                </div>
                <div className="research-badges">
                    <span className={`badge ${evidence.mode === 'demo' ? 'badge-amber' : 'badge-indigo'}`}>
                        {evidence.mode === 'demo' ? 'SYNTHETIC DEMO' : 'SERPAPI SEARCH'}
                    </span>
                    <span className={`badge ${incomplete ? 'badge-amber' : 'badge-emerald'}`}>
                        {evidence.status.toUpperCase()} COVERAGE
                    </span>
                    <span className="badge badge-indigo">{report?.synthesis_mode === 'llm' ? 'AI INTERPRETATION' : 'SOURCE EXCERPTS'}</span>
                </div>
            </div>
            <div className="research-note">
                <AlertCircle size={16} aria-hidden="true" />
                <div>{report?.summary}
                    {(report?.warnings || evidence.warnings).map((warning, i) => <p key={i}>{warning}</p>)}
                </div>
            </div>
            <div className="research-coverage">
                {evidence.searches.map((search, i) => (
                    <div key={i} className="research-coverage-item">
                        <strong>{search.purpose}</strong>
                        <span>{search.status} · {search.result_count} results {search.cache_hit ? '· cached' : ''}</span>
                        {search.error && <p role="alert">{search.error}</p>}
                        <details><summary>Query</summary><p>{search.query}</p></details>
                    </div>
                ))}
            </div>
            {report && report.findings.length > 0 && (
                <div className="research-findings">
                    <h3>Observations for analyst review</h3>
                    {report.findings.map((finding, i) => (
                        <article key={i}>
                            <small>{finding.category} · {finding.verification.replaceAll('_', ' ')}</small>
                            <p>{finding.statement}</p>
                            <div className="research-citations">
                                {finding.source_ids.map(id => {
                                    const source = evidence.sources.find(s => s.id === id)
                                    return source ? <a key={id} href={`#source-${id}`} onClick={event => revealSource(event, id)}>[{id}]</a> : null
                                })}
                            </div>
                        </article>
                    ))}
                </div>
            )}

            <section className="research-review-board" aria-labelledby="review-board-heading">
                <div className="research-review-heading">
                    <div>
                        <h3 id="review-board-heading">Analyst Review Board ({reviewItems.length})</h3>
                        <p>Reviewed means handled by an analyst; it does not independently verify a search claim.</p>
                    </div>
                    <button className="research-secondary-button" type="button" disabled={reviewBusy} onClick={exportBoard}>
                        <FileText size={14} /> Export board snapshot
                    </button>
                </div>
                {reviewError && <p className="research-review-error" role="alert">{reviewError}</p>}
                {reviewMessage && <p className="research-review-success" role="status">{reviewMessage}</p>}
                {reviewItems.length === 0 && <p className="research-empty">No saved review items yet. Add an observation or question and link it to the evidence below.</p>}
                <div className="research-review-items">
                    {reviewItems.map(item => (
                        <article key={item.id}>
                            <div className="research-review-item-heading">
                                <div>
                                    <small>{item.kind}</small>
                                    <h4>{item.title}</h4>
                                </div>
                                <select
                                    aria-label={`Review status for ${item.title}`}
                                    value={item.status}
                                    disabled={reviewBusy}
                                    onChange={event => void changeStatus(item, event.target.value as ResearchReviewItem['status'])}
                                >
                                    <option value="unreviewed">Unreviewed</option>
                                    <option value="reviewed">Reviewed</option>
                                    <option value="needs_follow_up">Needs follow-up</option>
                                </select>
                            </div>
                            {item.note && <p>{item.note}</p>}
                            {item.next_action && <p><strong>Next action:</strong> {item.next_action}</p>}
                            <div className="research-review-sources">
                                {item.source_ids.map(id => (
                                    <a key={id} href={`#source-${id}`} onClick={event => revealSource(event, id)}>{id}</a>
                                ))}
                            </div>
                            <p className="research-source-meta">Updated {new Date(item.updated_at).toLocaleString()} by {item.updated_by}</p>
                            <div className="research-review-actions">
                                <button type="button" disabled={reviewBusy} onClick={() => startEdit(item)}><Pencil size={13} /> Edit</button>
                                <button type="button" disabled={reviewBusy} onClick={() => void removeReviewItem(item)}><Trash2 size={13} /> Remove</button>
                            </div>
                        </article>
                    ))}
                </div>
                <form className="research-review-form" onSubmit={saveReviewItem}>
                    <div className="research-review-form-heading">
                        <h4>{editingId ? 'Edit review item' : 'Add review item'}</h4>
                        {!editingId && <button type="button" onClick={() => startDraft()}><Plus size={13} /> Clear form</button>}
                    </div>
                    <div className="research-review-form-grid">
                        <label>Type
                            <select value={draft.kind} disabled={reviewBusy} onChange={event => setDraft(current => ({ ...current, kind: event.target.value as ResearchReviewItemPayload['kind'] }))}>
                                <option value="observation">Observation</option>
                                <option value="question">Open question</option>
                            </select>
                        </label>
                        <label>Status
                            <select value={draft.status} disabled={reviewBusy} onChange={event => setDraft(current => ({ ...current, status: event.target.value as ResearchReviewItemPayload['status'] }))}>
                                <option value="unreviewed">Unreviewed</option>
                                <option value="reviewed">Reviewed</option>
                                <option value="needs_follow_up">Needs follow-up</option>
                            </select>
                        </label>
                    </div>
                    <label>Title
                        <input id="review-form-title" required maxLength={160} value={draft.title} disabled={reviewBusy} onChange={event => setDraft(current => ({ ...current, title: event.target.value }))} />
                    </label>
                    <label>Analyst note
                        <textarea maxLength={2000} rows={3} value={draft.note} disabled={reviewBusy} onChange={event => setDraft(current => ({ ...current, note: event.target.value }))} />
                    </label>
                    <label>Next action (optional)
                        <input maxLength={500} value={draft.next_action || ''} disabled={reviewBusy} onChange={event => setDraft(current => ({ ...current, next_action: event.target.value }))} />
                    </label>
                    <fieldset>
                        <legend>Linked sources (select 1–8)</legend>
                        <div className="research-review-source-picker">
                            {evidence.sources.map(source => (
                                <label key={source.id} title={source.title}>
                                    <input
                                        type="checkbox"
                                        checked={draft.source_ids.includes(source.id)}
                                        disabled={reviewBusy || (!draft.source_ids.includes(source.id) && draft.source_ids.length >= 8)}
                                        onChange={() => toggleSource(source.id)}
                                    />
                                    {source.id}
                                </label>
                            ))}
                        </div>
                    </fieldset>
                    <div className="research-review-form-actions">
                        <button className="research-primary-button" type="submit" disabled={reviewBusy}><Save size={14} /> {editingId ? 'Save changes' : 'Save item'}</button>
                        {editingId && <button className="research-secondary-button" type="button" disabled={reviewBusy} onClick={() => { setEditingId(null); setDraft(emptyDraft()) }}>Cancel</button>}
                    </div>
                </form>
            </section>

            <div className="research-source-heading">
                <h3>Sources ({evidence.sources.length})</h3>
                <label className="research-filter"><Search size={14} aria-hidden="true" />
                    <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter sources" aria-label="Filter research sources" />
                </label>
            </div>
            {sources.length === 0 && <p className="research-empty">No sources match this view.</p>}
            <div className="research-sources">
                {sources.map(source => (
                    <article key={source.id} id={`source-${source.id}`} tabIndex={-1}>
                        <div><span className="badge badge-indigo">{source.id}</span> <span className="research-source-purpose">{source.purpose}</span></div>
                        <a href={source.url} target="_blank" rel="noopener noreferrer" className="research-source-link">
                            {source.title} <ExternalLink size={13} aria-hidden="true" />
                        </a>
                        <p className="research-source-meta">{source.publisher} · {source.domain} · Published: {source.published_at || 'Not provided'}</p>
                        {source.snippet && <p>{source.snippet}</p>}
                        <p className="research-source-meta">{source.engine} · Search ID: {source.search_id || 'Not provided'}{source.cache_hit ? ' · Cached response' : ''}</p>
                        {source.official_domain_match && <small>Matches the domain you supplied; ownership and content still require review.</small>}
                        <button className="research-source-add" type="button" onClick={() => startDraft(source.id)}><Plus size={13} /> Add to review board</button>
                    </article>
                ))}
            </div>
        </section>
    )
}
