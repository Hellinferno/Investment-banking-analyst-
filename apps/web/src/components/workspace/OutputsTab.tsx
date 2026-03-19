import { useState, useEffect, useCallback } from 'react'
import { downloadOutput, fetchCurrentUser, fetchOutputs, reviewOutput, type OutputInfo } from '../../lib/api'
import { Download, Clock, ShieldCheck } from 'lucide-react'

interface Props { dealId: string }

export default function OutputsTab({ dealId }: Props) {
    const [outputs, setOutputs] = useState<OutputInfo[]>([])
    const [loading, setLoading] = useState(true)
    const [busyId, setBusyId] = useState<string | null>(null)
    const [canApprove, setCanApprove] = useState(false)

    const load = useCallback(async () => {
        try {
            const [data, user] = await Promise.all([
                fetchOutputs(dealId),
                fetchCurrentUser(),
            ])
            setOutputs(data)
            setCanApprove(['reviewer', 'admin'].includes(user.role.toLowerCase()))
        } catch {
            setOutputs([])
            setCanApprove(false)
        } finally {
            setLoading(false)
        }
    }, [dealId])

    useEffect(() => { load() }, [load])

    const handleApprove = async (outputId: string) => {
        setBusyId(outputId)
        try {
            await reviewOutput(outputId, {
                review_status: 'approved',
                reviewer_notes: 'Approved for download from workspace UI.',
            })
            await load()
        } finally {
            setBusyId(null)
        }
    }

    const handleDownload = async (output: OutputInfo) => {
        setBusyId(output.id)
        try {
            await downloadOutput(output.id, output.filename)
        } finally {
            setBusyId(null)
        }
    }

    if (loading) {
        return (
            <div style={{ textAlign: 'center', padding: 60 }}>
                <div className="spinner" style={{ margin: '0 auto' }} />
            </div>
        )
    }

    if (outputs.length === 0) {
        return (
            <div className="animate-fade-in" style={{ textAlign: 'center', padding: 60, color: '#444', fontSize: 12 }}>
                No outputs generated yet — deploy an agent first
            </div>
        )
    }

    return (
        <div className="animate-fade-in">
            <div style={{ border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                {outputs.map((out, i) => {
                    const approved = out.review_status === 'approved'
                    const busy = busyId === out.id
                    return (
                        <div key={out.id} style={{
                            display: 'flex', alignItems: 'center', padding: '14px 18px',
                            borderBottom: i < outputs.length - 1 ? '1px solid #151515' : 'none',
                            gap: 12,
                        }}>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', marginBottom: 2 }}>{out.filename}</div>
                                <div style={{ fontSize: 11, color: '#555', display: 'flex', alignItems: 'center', gap: 6 }}>
                                    <Clock size={10} />
                                    {new Date(out.created_at).toLocaleString()} · {out.output_type}
                                </div>
                            </div>
                            <span className={`badge ${approved ? 'badge-emerald' : 'badge-amber'}`}>
                                {out.review_status}
                            </span>
                            {!approved && canApprove && (
                                <button
                                    className="btn-ghost"
                                    onClick={() => handleApprove(out.id)}
                                    disabled={busy}
                                    style={{ padding: '6px 12px', fontSize: 11, display: 'flex', alignItems: 'center', gap: 5 }}
                                >
                                    <ShieldCheck size={11} /> {busy ? 'APPROVING...' : 'APPROVE'}
                                </button>
                            )}
                            <button
                                className="btn-primary"
                                onClick={() => handleDownload(out)}
                                disabled={!approved || busy}
                                style={{
                                    padding: '6px 14px',
                                    fontSize: 11,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 5,
                                    opacity: !approved || busy ? 0.6 : 1,
                                }}
                            >
                                <Download size={11} /> {busy && approved ? 'DOWNLOADING...' : 'DOWNLOAD'}
                            </button>
                        </div>
                    )
                })}
            </div>
            {!canApprove && (
                <div style={{ marginTop: 12, fontSize: 11, color: '#777' }}>
                    Output approval requires a `reviewer` or `admin` role.
                </div>
            )}
        </div>
    )
}
