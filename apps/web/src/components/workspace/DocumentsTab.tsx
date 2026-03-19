import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchDocuments, uploadDocuments, deleteDocument, type DocumentInfo } from '../../lib/api'
import { Upload, Trash2, AlertCircle } from 'lucide-react'

interface Props { dealId: string }

function formatBytes(b: number): string {
    if (b < 1024) return `${b} B`
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
    return `${(b / 1024 / 1024).toFixed(1)} MB`
}

export default function DocumentsTab({ dealId }: Props) {
    const [docs, setDocs] = useState<DocumentInfo[]>([])
    const [loading, setLoading] = useState(true)
    const [uploading, setUploading] = useState(false)
    const [error, setError] = useState('')
    const fileInputRef = useRef<HTMLInputElement>(null)

    const load = useCallback(async () => {
        try {
            const data = await fetchDocuments(dealId)
            setDocs(data)
        } catch { setDocs([]) }
        finally { setLoading(false) }
    }, [dealId])

    useEffect(() => { load() }, [load])

    useEffect(() => {
        const hasActiveParsing = docs.some(doc => doc.parse_status === 'parsing' || doc.parse_status === 'pending')
        if (!hasActiveParsing) return
        const interval = window.setInterval(() => {
            load()
        }, 3000)
        return () => window.clearInterval(interval)
    }, [docs, load])

    const handleUpload = async (files: FileList | null) => {
        if (!files || files.length === 0) return
        setUploading(true)
        setError('')
        try {
            const result = await uploadDocuments(dealId, Array.from(files))
            await load()
            if (result.failed.length > 0) {
                setError(result.failed.map(f => `${f.filename}: ${f.reason}`).join(' | '))
            }
        } catch (err: unknown) {
            const maybeAxios = err as { response?: { data?: { detail?: string } }; message?: string }
            const msg = maybeAxios?.response?.data?.detail || maybeAxios?.message || 'Upload failed'
            setError(msg)
        } finally {
            setUploading(false)
        }
    }

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        handleUpload(e.dataTransfer.files)
    }

    const handleRemove = async (docId: string) => {
        try {
            await deleteDocument(dealId, docId)
            setDocs(prev => prev.filter(d => d.id !== docId))
        } catch { setError('Delete failed') }
    }

    return (
        <div className="animate-fade-in">
            {/* Drop Zone */}
            <div
                style={{
                    padding: '28px 0', textAlign: 'center', marginBottom: 16, cursor: 'pointer',
                    border: '1px dashed #333', borderRadius: 3, background: '#050505',
                    transition: 'border-color 0.15s'
                }}
                onDragOver={e => e.preventDefault()}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#ff6600')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#333')}
            >
                <input
                    ref={fileInputRef}
                    type="file" multiple
                    accept=".pdf,.docx,.xlsx,.xls,.csv,.txt,.json"
                    style={{ display: 'none' }}
                    onChange={e => handleUpload(e.target.files)}
                />
                {uploading ? (
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
                        <div className="spinner" style={{ width: 20, height: 20 }} />
                        <span style={{ color: '#666', fontSize: 12 }}>Uploading...</span>
                    </div>
                ) : (
                    <>
                        <Upload size={22} style={{ color: '#444', marginBottom: 8 }} />
                        <p style={{ color: '#888', fontSize: 13, margin: '0 0 2px', fontWeight: 500 }}>
                            Drop files or click to browse
                        </p>
                        <p style={{ color: '#444', fontSize: 11, margin: 0 }}>
                            PDF, DOCX, XLSX, CSV, JSON · up to 150 MB
                        </p>
                    </>
                )}
            </div>

            {error && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
                    background: 'rgba(204,51,51,0.08)', border: '1px solid rgba(204,51,51,0.2)',
                    borderRadius: 3, marginBottom: 12, color: '#cc3333', fontSize: 12
                }}>
                    <AlertCircle size={13} /> {error}
                </div>
            )}

            {/* Documents Table */}
            {loading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                    <div className="spinner" style={{ margin: '0 auto' }} />
                </div>
            ) : docs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: '#444', fontSize: 12 }}>
                    No documents uploaded
                </div>
            ) : (
                <div style={{ border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Type</th>
                                <th>Size</th>
                                <th>Status</th>
                                <th>Uploaded</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {docs.map(doc => (
                                <tr key={doc.id}>
                                    <td style={{ color: '#fff', fontFamily: "'Inter', system-ui, sans-serif", fontWeight: 500 }}>
                                        {doc.filename}
                                    </td>
                                    <td><span className="badge badge-indigo">{doc.file_type.toUpperCase()}</span></td>
                                    <td>{formatBytes(doc.file_size_bytes)}</td>
                                    <td>
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                            <span className={`status-dot ${doc.parse_status === 'parsed' ? 'active' : 'pending'}`} />
                                            {doc.parse_status}
                                        </span>
                                    </td>
                                    <td>{new Date(doc.uploaded_at).toLocaleString()}</td>
                                    <td>
                                        <button className="btn-ghost" style={{ padding: 3, border: 'none' }}
                                            onClick={() => handleRemove(doc.id)}>
                                            <Trash2 size={12} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
