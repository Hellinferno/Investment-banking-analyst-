import { FileSpreadsheet } from 'lucide-react'

// Basic view just to show that the 3-statement model ran and produced a result.
interface ThreeStatementResult {
    fy_labels?: string[];
    assumptions?: {
        revenue_cagr?: number;
        avg_ebitda_margin?: number;
        tax_rate?: number;
    };
    [key: string]: unknown;
}

export default function ThreeStatementResultsView({ data }: { data: ThreeStatementResult | null }) {
    if (!data) return null;
    
    return (
        <div className="animate-fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div style={{
                background: '#0a0a0a', border: '1px solid #222', borderRadius: 3,
                padding: '20px 24px'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
                    <FileSpreadsheet size={16} style={{ color: '#00cc66' }} />
                    <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.04em' }}>3-STATEMENT MODEL</span>
                </div>
                
                <p style={{ fontSize: 13, color: '#aaa', lineHeight: 1.6, margin: 0, marginBottom: 16 }}>
                    The 3-statement operating model has been projected for {data.fy_labels?.length || 5} years based on historicals.
                </p>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
                     <div style={{ border: '1px solid #222', padding: 12, borderRadius: 3 }}>
                        <div style={{ fontSize: 10, color: '#555', letterSpacing: '0.06em', marginBottom: 4 }}>REVENUE CAGR</div>
                        <div style={{ fontSize: 18, color: '#fff', fontFamily: "'SF Mono', Consolas, monospace" }}>
                            {((data.assumptions?.revenue_cagr || 0) * 100).toFixed(1)}%
                        </div>
                     </div>
                     <div style={{ border: '1px solid #222', padding: 12, borderRadius: 3 }}>
                        <div style={{ fontSize: 10, color: '#555', letterSpacing: '0.06em', marginBottom: 4 }}>AVG EBITDA MARGIN</div>
                        <div style={{ fontSize: 18, color: '#fff', fontFamily: "'SF Mono', Consolas, monospace" }}>
                            {((data.assumptions?.avg_ebitda_margin || 0) * 100).toFixed(1)}%
                        </div>
                     </div>
                     <div style={{ border: '1px solid #222', padding: 12, borderRadius: 3 }}>
                        <div style={{ fontSize: 10, color: '#555', letterSpacing: '0.06em', marginBottom: 4 }}>TAX RATE</div>
                        <div style={{ fontSize: 18, color: '#fff', fontFamily: "'SF Mono', Consolas, monospace" }}>
                            {((data.assumptions?.tax_rate || 0) * 100).toFixed(1)}%
                        </div>
                     </div>
                </div>
            </div>
        </div>
    )
}
