import React, { useState, useEffect } from 'react';
import { api, getDownloadUrl, reviewOutput, type OutputReviewPayload } from '../../lib/api';

interface ReviewQueueItem {
    id: string;
    deal_id: string;
    deal_name: string;
    agent_run_id: string;
    filename: string;
    output_type: string;
    output_category: string;
    review_status: string;
    created_at: string;
    confidence_score: number | null;
    validator_status: string;
}

function getErrorMessage(err: unknown, fallback: string): string {
    if (typeof err === 'object' && err !== null && 'response' in err) {
        const response = (err as { response?: { data?: { detail?: string } } }).response;
        if (response?.data?.detail) return response.data.detail;
    }
    return err instanceof Error ? err.message : fallback;
}

export const ReviewQueueTab: React.FC = () => {
    const [items, setItems] = useState<ReviewQueueItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [notesById, setNotesById] = useState<Record<string, string>>({});

    const loadQueue = async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await api.get('/outputs/review-queue');
            setItems(res.data.data);
        } catch (err: unknown) {
            setError(getErrorMessage(err, 'Failed to load review queue'));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadQueue();
    }, []);

    const handleReview = async (id: string, status: OutputReviewPayload['review_status']) => {
        const notes = notesById[id]?.trim() || '';
        if ((status === 'rejected' || status === 'needs_changes') && !notes) {
            alert('Add a reviewer note before rejecting or requesting changes.');
            return;
        }
        
        try {
            await reviewOutput(id, { review_status: status, reviewer_notes: notes });
            setNotesById(prev => ({ ...prev, [id]: '' }));
            await loadQueue();
        } catch (err: unknown) {
            alert('Review failed: ' + getErrorMessage(err, 'Unknown error'));
        }
    };

    if (loading) return <div className="p-8 text-center text-gray-500">Loading queue...</div>;
    if (error) return <div className="p-8 text-center text-red-500">{error}</div>;
    if (items.length === 0) return <div className="p-8 text-center text-gray-500">No items pending review.</div>;

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-6">
                <h2 className="text-2xl font-bold text-gray-900">Maker-Checker Review Queue</h2>
                <button onClick={loadQueue} className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-50">Refresh</button>
            </div>
            
            <div className="bg-white shadow rounded-lg overflow-hidden border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Deal</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Document</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Confidence</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Reviewer Note</th>
                            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {items.map(item => (
                            <tr key={item.id} className="hover:bg-gray-50">
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <div className="text-sm font-medium text-gray-900">{item.deal_name}</div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <div className="text-sm font-medium text-gray-900 truncate max-w-xs">{item.filename}</div>
                                    <div className="text-xs text-gray-500">{item.output_category}</div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    {item.confidence_score != null ? (
                                        <div className="flex items-center">
                                            <div className="w-16 bg-gray-200 rounded-full h-2 mr-2">
                                                <div 
                                                    className={`h-2 rounded-full ${item.confidence_score > 0.8 ? 'bg-green-500' : item.confidence_score > 0.6 ? 'bg-amber-500' : 'bg-red-500'}`} 
                                                    style={{ width: `${Math.round(item.confidence_score * 100)}%` }}
                                                ></div>
                                            </div>
                                            <span className="text-xs font-medium text-gray-700">{Math.round(item.confidence_score * 100)}%</span>
                                        </div>
                                    ) : (
                                        <span className="text-xs text-gray-400">N/A</span>
                                    )}
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-yellow-100 text-yellow-800">
                                        {item.review_status.toUpperCase()}
                                    </span>
                                </td>
                                <td className="px-6 py-4">
                                    <textarea
                                        value={notesById[item.id] || ''}
                                        onChange={e => setNotesById(prev => ({ ...prev, [item.id]: e.target.value }))}
                                        placeholder="Reviewer comment"
                                        className="w-full min-w-[180px] rounded border border-gray-300 px-2 py-1 text-xs"
                                        rows={2}
                                    />
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                                    <a 
                                        href={getDownloadUrl(item.id)}
                                        target="_blank" rel="noopener noreferrer"
                                        className="text-blue-600 hover:text-blue-900 px-2"
                                    >
                                        View
                                    </a>
                                    <button 
                                        onClick={() => handleReview(item.id, 'approved')}
                                        className="text-green-600 hover:text-green-900 px-2"
                                    >
                                        Approve
                                    </button>
                                    <button 
                                        onClick={() => handleReview(item.id, 'needs_changes')}
                                        className="text-amber-600 hover:text-amber-900 px-2"
                                    >
                                        Revise
                                    </button>
                                    <button 
                                        onClick={() => handleReview(item.id, 'rejected')}
                                        className="text-red-600 hover:text-red-900 px-2"
                                    >
                                        Reject
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
};
