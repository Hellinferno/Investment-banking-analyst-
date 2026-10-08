import { useState } from 'react'
import { ExternalLink, Search, AlertCircle } from 'lucide-react'
import type { ResearchEvidence, ResearchReport } from '../../lib/api'

interface Props { evidence: ResearchEvidence; report?: ResearchReport | null }

export default function ResearchResultsView({ evidence, report }: Props) {
    const [filter, setFilter] = useState('')
    const sources = evidence.sources.filter(source =>
        `${source.title} ${source.publisher} ${source.purpose}`.toLowerCase().includes(filter.toLowerCase()))
    const incomplete = evidence.status !== 'complete'
    return (
        <section className="research-results" aria-label="Research results">
            <div className="research-result-header">
                <div>
                    <h2>{report?.title || 'Search evidence'}</h2>
                    <p>{evidence.company_name} · Retrieved {new Date(evidence.collected_at).toLocaleString()}</p>
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
                                    return source ? <a key={id} href={`#source-${id}`}>[{id}]</a> : null
                                })}
                            </div>
                        </article>
                    ))}
                </div>
            )}
            <div className="research-source-heading">
                <h3>Sources ({evidence.sources.length})</h3>
                <label className="research-filter"><Search size={14} aria-hidden="true" />
                    <input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Filter sources" aria-label="Filter research sources" />
                </label>
            </div>
            {sources.length === 0 && <p className="research-empty">No sources match this view.</p>}
            <div className="research-sources">
                {sources.map(source => (
                    <article key={source.id} id={`source-${source.id}`}>
                        <div><span className="badge badge-indigo">{source.id}</span> <span className="research-source-purpose">{source.purpose}</span></div>
                        <a href={source.url} target="_blank" rel="noopener noreferrer" className="research-source-link">
                            {source.title} <ExternalLink size={13} aria-hidden="true" />
                        </a>
                        <p className="research-source-meta">{source.publisher} · {source.domain} · Published: {source.published_at || 'Not provided'}</p>
                        {source.snippet && <p>{source.snippet}</p>}
                        <p className="research-source-meta">{source.engine} · Search ID: {source.search_id || 'Not provided'}{source.cache_hit ? ' · Cached response' : ''}</p>
                        {source.official_domain_match && <small>Matches the domain you supplied; ownership and content still require review.</small>}
                    </article>
                ))}
            </div>
        </section>
    )
}
