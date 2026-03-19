import { useEffect, useState, useCallback } from 'react'
import { fetchTasks, createTask, updateTask, deleteTask, type Task } from '../../lib/api'
import { Plus, Trash2, AlertCircle } from 'lucide-react'

interface Props { dealId: string }

const PRIORITY_COLORS: Record<string, string> = {
    high: '#cc3333',
    medium: '#ffa500',
    low: '#00cc66',
}

const STATUS_LABELS: Record<string, string> = {
    todo: 'To Do',
    in_progress: 'In Progress',
    done: 'Done',
    blocked: 'Blocked',
}

const STATUS_COLORS: Record<string, string> = {
    todo: '#555',
    in_progress: '#4a9eff',
    done: '#00cc66',
    blocked: '#cc3333',
}

export default function TasksTab({ dealId }: Props) {
    const [tasks, setTasks] = useState<Task[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState('')
    const [newTitle, setNewTitle] = useState('')
    const [newPriority, setNewPriority] = useState<'low' | 'medium' | 'high'>('medium')
    const [adding, setAdding] = useState(false)
    const [showForm, setShowForm] = useState(false)

    const load = useCallback(async () => {
        try {
            setLoading(true)
            const data = await fetchTasks(dealId)
            setTasks(data)
            setError('')
        } catch {
            setError('Failed to load tasks')
        } finally {
            setLoading(false)
        }
    }, [dealId])

    useEffect(() => { load() }, [load])

    const handleAddTask = async () => {
        if (!newTitle.trim()) return
        setAdding(true)
        try {
            const t = await createTask(dealId, { title: newTitle.trim(), priority: newPriority })
            setTasks(prev => [t, ...prev])
            setNewTitle('')
            setShowForm(false)
        } catch {
            setError('Failed to create task')
        } finally {
            setAdding(false)
        }
    }

    const handleStatusChange = async (taskId: string, newStatus: Task['status']) => {
        try {
            const updated = await updateTask(dealId, taskId, { status: newStatus })
            setTasks(prev => prev.map(t => t.task_id === taskId ? updated : t))
        } catch {
            setError('Failed to update task')
        }
    }

    const handleDelete = async (taskId: string) => {
        try {
            await deleteTask(dealId, taskId)
            setTasks(prev => prev.filter(t => t.task_id !== taskId))
        } catch {
            setError('Failed to delete task')
        }
    }

    const aiTasks = tasks.filter(t => t.is_ai_generated)
    const manualTasks = tasks.filter(t => !t.is_ai_generated)

    const taskStyle: React.CSSProperties = {
        padding: '12px 16px',
        borderBottom: '1px solid #111',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
    }

    const renderTask = (task: Task) => (
        <div key={task.task_id} style={taskStyle}>
            {/* Priority indicator */}
            <div style={{
                width: 3, height: 36, borderRadius: 2, flexShrink: 0, marginTop: 2,
                background: PRIORITY_COLORS[task.priority] || '#555',
            }} />

            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                    fontSize: 12, color: task.status === 'done' ? '#444' : '#ccc', fontWeight: 600,
                    textDecoration: task.status === 'done' ? 'line-through' : 'none',
                    marginBottom: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                }}>
                    {task.title}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    {task.owner && (
                        <span style={{ fontSize: 10, color: '#555' }}>{task.owner.split(' | ')[0]}</span>
                    )}
                    <span style={{
                        fontSize: 9, fontWeight: 700, padding: '2px 5px', borderRadius: 2,
                        background: `${PRIORITY_COLORS[task.priority]}22`,
                        color: PRIORITY_COLORS[task.priority],
                        letterSpacing: '0.05em',
                    }}>
                        {task.priority.toUpperCase()}
                    </span>
                    {task.is_ai_generated && (
                        <span style={{ fontSize: 9, color: '#4a9eff', fontWeight: 600 }}>AI</span>
                    )}
                </div>
            </div>

            {/* Status selector */}
            <select
                value={task.status}
                onChange={e => handleStatusChange(task.task_id, e.target.value as Task['status'])}
                style={{
                    background: '#111', border: '1px solid #333', borderRadius: 2,
                    color: STATUS_COLORS[task.status] || '#888', fontSize: 10, fontWeight: 700,
                    padding: '4px 6px', cursor: 'pointer', flexShrink: 0,
                }}
            >
                {Object.entries(STATUS_LABELS).map(([val, label]) => (
                    <option key={val} value={val}>{label}</option>
                ))}
            </select>

            {/* Delete */}
            <button
                onClick={() => handleDelete(task.task_id)}
                style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: '#333', padding: '4px', flexShrink: 0,
                    display: 'flex', alignItems: 'center',
                }}
                onMouseEnter={e => (e.currentTarget.style.color = '#cc3333')}
                onMouseLeave={e => (e.currentTarget.style.color = '#333')}
            >
                <Trash2 size={12} />
            </button>
        </div>
    )

    return (
        <div className="animate-fade-in">
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 2 }}>Tasks</div>
                    <div style={{ fontSize: 11, color: '#555' }}>
                        {tasks.length} task{tasks.length !== 1 ? 's' : ''} · {tasks.filter(t => t.status === 'done').length} completed
                    </div>
                </div>
                <button
                    className="btn-secondary"
                    onClick={() => setShowForm(!showForm)}
                    style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', fontSize: 11 }}
                >
                    <Plus size={12} /> Add Task
                </button>
            </div>

            {/* Add Task Form */}
            {showForm && (
                <div style={{ border: '1px solid #333', borderRadius: 3, padding: 16, marginBottom: 16, background: '#0a0a0a' }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                        <input
                            type="text"
                            className="input-field"
                            placeholder="Task title..."
                            value={newTitle}
                            onChange={e => setNewTitle(e.target.value)}
                            onKeyDown={e => e.key === 'Enter' && handleAddTask()}
                            style={{ flex: 1, padding: '8px 10px' }}
                            autoFocus
                        />
                        <select
                            value={newPriority}
                            onChange={e => setNewPriority(e.target.value as 'low' | 'medium' | 'high')}
                            style={{
                                background: '#111', border: '1px solid #333', borderRadius: 2,
                                color: PRIORITY_COLORS[newPriority], fontSize: 11, fontWeight: 700, padding: '8px 10px',
                            }}
                        >
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <button
                            className="btn-primary"
                            onClick={handleAddTask}
                            disabled={!newTitle.trim() || adding}
                            style={{ flex: 1, padding: '8px 0', fontSize: 11 }}
                        >
                            {adding ? 'Adding...' : 'Add Task'}
                        </button>
                        <button
                            className="btn-secondary"
                            onClick={() => { setShowForm(false); setNewTitle('') }}
                            style={{ padding: '8px 16px', fontSize: 11 }}
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px',
                    background: 'rgba(204,51,51,0.08)', border: '1px solid rgba(204,51,51,0.2)',
                    borderRadius: 3, marginBottom: 16, color: '#cc3333', fontSize: 12
                }}>
                    <AlertCircle size={14} /> {error}
                </div>
            )}

            {/* Loading */}
            {loading ? (
                <div style={{ padding: '40px 0', textAlign: 'center', color: '#444', fontSize: 12 }}>
                    Loading tasks...
                </div>
            ) : tasks.length === 0 ? (
                <div style={{
                    padding: '40px 0', textAlign: 'center', color: '#333', fontSize: 12,
                    border: '1px dashed #222', borderRadius: 3,
                }}>
                    No tasks yet. Run the Meeting Notes agent to extract tasks automatically,<br />or add them manually above.
                </div>
            ) : (
                <>
                    {/* AI-generated tasks */}
                    {aiTasks.length > 0 && (
                        <div style={{ border: '1px solid #222', borderRadius: 3, marginBottom: 12, overflow: 'hidden' }}>
                            <div style={{ padding: '6px 16px', background: '#0a0a0a', borderBottom: '1px solid #222', fontSize: 9, color: '#4a9eff', fontWeight: 700, letterSpacing: '0.1em' }}>
                                AI EXTRACTED ({aiTasks.length})
                            </div>
                            {aiTasks.map(renderTask)}
                        </div>
                    )}

                    {/* Manual tasks */}
                    {manualTasks.length > 0 && (
                        <div style={{ border: '1px solid #222', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{ padding: '6px 16px', background: '#0a0a0a', borderBottom: '1px solid #222', fontSize: 9, color: '#555', fontWeight: 700, letterSpacing: '0.1em' }}>
                                MANUAL ({manualTasks.length})
                            </div>
                            {manualTasks.map(renderTask)}
                        </div>
                    )}
                </>
            )}
        </div>
    )
}
