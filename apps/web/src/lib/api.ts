import axios from 'axios';

const rawApiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();
const API_BASE_URL = rawApiBase && rawApiBase.length > 0 ? rawApiBase.replace(/\/$/, '') : '/api/v1';
const BOOTSTRAP_TOKEN = (import.meta.env.VITE_API_TOKEN as string | undefined)?.trim() || 'dev-local-token';
const DEV_AUTH_ROLE = (import.meta.env.VITE_DEV_AUTH_ROLE as string | undefined)?.trim() || 'reviewer';
const DEFAULT_API_TIMEOUT_MS = 30_000;
const AGENT_RUN_TIMEOUT_MS = 5 * 60_000;

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: DEFAULT_API_TIMEOUT_MS,
    withCredentials: true,
});

const authApi = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: DEFAULT_API_TIMEOUT_MS,
    withCredentials: true,
});

function looksLikeJwt(token: string | null | undefined): boolean {
    return Boolean(token && token.split('.').length === 3);
}

const accessToken: string | null = looksLikeJwt(BOOTSTRAP_TOKEN) ? BOOTSTRAP_TOKEN : null;
let authBootstrapPromise: Promise<string | null> | null = null;
let currentUserCache: CurrentUserInfo | null = null;

async function bootstrapDevToken(): Promise<string | null> {
    if (!BOOTSTRAP_TOKEN || looksLikeJwt(BOOTSTRAP_TOKEN)) {
        return accessToken;
    }

    // Use the backend's /auth/login endpoint with demo credentials
    const res = await authApi.post<APIResponse<LoginResponse>>(
        '/auth/login',
        { username: DEV_AUTH_ROLE, password: 'AIBAA-demo-2026!' },
    );
    // The backend sets a session cookie; also extract user for cache
    currentUserCache = res.data.data.user;
    return 'session-cookie-auth';
}

export async function ensureAuthToken(): Promise<string | null> {
    if (accessToken) {
        return accessToken;
    }
    if (!authBootstrapPromise) {
        authBootstrapPromise = bootstrapDevToken().finally(() => {
            authBootstrapPromise = null;
        });
    }
    return authBootstrapPromise;
}

api.interceptors.request.use(async (config) => {
    const token = await ensureAuthToken();
    if (token) {
        config.headers = config.headers ?? {};
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// ─── Types ───

export interface Deal {
    id: string;
    name: string;
    company_name: string;
    deal_type: string;
    industry: string;
    deal_stage: string;
    process_stage: string;
    stage_last_updated?: string | null;
    notes?: string;
    created_at: string;
    document_count?: number;
    output_count?: number;
}

export interface DealCreatePayload {
    name: string;
    company_name: string;
    deal_type: string;
    industry: string;
    deal_stage?: string;
    process_stage?: string;
    notes?: string;
}

export interface DocumentInfo {
    id: string;
    filename: string;
    file_type: string;
    file_size_bytes: number;
    doc_category?: string;
    parse_status: string;
    uploaded_at: string;
}

export interface UploadFailure {
    filename: string;
    reason: string;
}

export interface AgentRunPayload {
    agent_type: string;
    task_name: string;
    parameters: Record<string, unknown>;
}

export interface AgentRunResult {
    run_id: string;
    status: string;
    steps: Array<Record<string, unknown>>;
    valuation_result?: ValuationResult;
    lbo_result?: Record<string, unknown> | null;
    error_message?: string | null;
    confidence_score?: number | null;
    route?: Record<string, unknown>;
}

export interface ValuationResult {
    header: {
        enterprise_value: number;
        equity_value: number;
        implied_share_price?: number | null;
        wacc: number;
        terminal_method: string;
        currency?: string;
        valuation_basis?: 'share_price' | 'equity_value';
        is_private_company?: boolean;
        company_type?: string;
        liquidity_discount?: number | null;
        control_premium?: number | null;
        projection_horizon_years?: number;
        per_share_value_available?: boolean;
    };
    scenarios?: {
        bear: ScenarioCase;
        base: ScenarioCase;
        bull: ScenarioCase;
    };
    ev_bridge?: Record<string, number | boolean | string | null>;
    tv_crosscheck?: Record<string, unknown>;
    sensitivity_wacc_tgr?: Array<Array<number | null>>;
    sensitivity_labels?: { wacc: number[]; tgr: number[]; metric?: string };
    sbc_adjusted?: Record<string, unknown>;
    operating_leverage?: Record<string, unknown>;
    margin_sensitivity?: Record<string, unknown>;
    capex_sensitivity?: Record<string, unknown>;
    extraction_metadata?: Record<string, unknown>;
    extraction_quality?: {
        mode: string;
        pipeline_stages?: string[];
        checkpoint?: {
            status: 'passed' | 'failed' | string;
            summary?: string;
            blocking_issues?: string[];
            warnings?: string[];
            checks?: Array<{
                name: string;
                passed: boolean;
                details: string;
                blocking: boolean;
            }>;
        };
        audit_trail?: Array<{
            field: string;
            confidence: number;
            source: string;
            auditor_status: string;
            triangulation: string;
        }>;
        triangulation?: {
            overall_verdict: string;
            total_checks: number;
            passed: number;
            failed: number;
            critical_failures: number;
            results: Array<{
                identity: string;
                passed: boolean;
                expected: number;
                actual: number;
                deviation_pct: number;
                details: string;
                severity: string;
            }>;
        };
        company_classification?: {
            is_private_company: boolean;
            entity_type: string;
            listing_status: string;
            cin?: string | null;
            evidence?: string[];
        };
        data_sources?: string[];
        key_field_status?: {
            shares_verified: boolean;
            per_share_value_available: boolean;
            tax_loss_carryforward_modeled: boolean;
        };
    };
    company_classification?: {
        is_private_company: boolean;
        entity_type: string;
        listing_status: string;
        cin?: string | null;
        evidence?: string[];
    };
    warnings?: string[];
}

export interface ScenarioCase {
    label: string;
    revenue_cagr: number;
    ebitda_margin: number;
    valuation: {
        enterprise_value: number;
        equity_value: number;
        share_price?: number | null;
    };
}

export interface OutputInfo {
    id: string;
    agent_run_id: string;
    filename: string;
    output_type: string;
    output_category: string;
    review_status: string;
    created_at: string;
}

export interface OutputReviewPayload {
    review_status: 'draft' | 'in_review' | 'approved' | 'rejected' | 'needs_changes';
    reviewer_notes?: string;
}

export interface CurrentUserInfo {
    user_id: string;
    tenant_id: string;
    role: string;
    email?: string | null;
    token_id?: string | null;
}

interface LoginResponse {
    user: CurrentUserInfo;
    session_expires_at: string;
}

interface APIResponse<T> {
    success: boolean;
    data: T;
    meta: { timestamp: string; request_id: string };
}

export async function fetchCurrentUser(forceRefresh = false): Promise<CurrentUserInfo> {
    if (currentUserCache && !forceRefresh) {
        return currentUserCache;
    }
    await ensureAuthToken();
    const res = await api.get<APIResponse<CurrentUserInfo>>('/auth/me');
    currentUserCache = res.data.data;
    return currentUserCache;
}

// ─── Deals ───

export async function fetchDeals(): Promise<Deal[]> {
    const res = await api.get<APIResponse<{ deals: Deal[]; total: number }>>('/deals');
    return res.data.data.deals;
}

export async function fetchDeal(dealId: string): Promise<Deal> {
    const res = await api.get<APIResponse<Deal>>(`/deals/${dealId}`);
    return res.data.data;
}

export async function createDeal(payload: DealCreatePayload): Promise<Deal> {
    const res = await api.post<APIResponse<Deal>>('/deals', payload);
    return res.data.data;
}

export async function updateDeal(dealId: string, payload: Partial<DealCreatePayload>): Promise<void> {
    await api.patch(`/deals/${dealId}`, payload);
}

export async function deleteDeal(dealId: string): Promise<void> {
    await api.delete(`/deals/${dealId}`);
}

// ─── Documents ───

export async function fetchDocuments(dealId: string): Promise<DocumentInfo[]> {
    const res = await api.get<APIResponse<DocumentInfo[]>>(`/deals/${dealId}/documents`);
    return res.data.data;
}

export async function uploadDocuments(
    dealId: string,
    files: File[],
    category?: string
): Promise<{ uploaded: DocumentInfo[]; failed: UploadFailure[] }> {
    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));
    if (category) formData.append('category', category);

    const res = await api.post<APIResponse<{ uploaded: DocumentInfo[]; failed: UploadFailure[] }>>(
        `/deals/${dealId}/documents`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    const payload = res.data.data as { uploaded: DocumentInfo[]; failed?: UploadFailure[] };
    return {
        uploaded: payload.uploaded ?? [],
        failed: payload.failed ?? [],
    };
}

export async function deleteDocument(dealId: string, docId: string): Promise<void> {
    await api.delete(`/deals/${dealId}/documents/${docId}`);
}

// ─── Agents ───

export async function deployAgent(dealId: string, payload: AgentRunPayload): Promise<AgentRunResult> {
    const res = await api.post<APIResponse<AgentRunResult>>(
        `/deals/${dealId}/agents/run`,
        payload,
        { timeout: AGENT_RUN_TIMEOUT_MS }
    );
    return res.data.data;
}

export async function fetchAgentRun(dealId: string, runId: string): Promise<AgentRunResult> {
    const res = await api.get<APIResponse<AgentRunResult>>(`/deals/${dealId}/agents/runs/${runId}`);
    return res.data.data;
}

// ─── Outputs ───

export async function fetchOutputs(dealId: string): Promise<OutputInfo[]> {
    const res = await api.get<APIResponse<OutputInfo[]>>(`/deals/${dealId}/outputs`);
    return res.data.data;
}

export function getDownloadUrl(outputId: string): string {
    return `${API_BASE_URL}/outputs/${outputId}/download`;
}

export async function reviewOutput(outputId: string, payload: OutputReviewPayload): Promise<void> {
    await api.patch(`/outputs/${outputId}/review`, payload);
}

export interface ProcessStatus {
    current_stage: string;
    next_stage: string;
    ready_for_next_stage: boolean;
    blockers: string[];
    open_task_count: number;
    buyer_count: number;
    approved_output_categories: string[];
    draft_output_categories: string[];
}

export interface BuyerOutreach {
    id: string;
    buyer_idx: number;
    name: string;
    buyer_type: string;
    outreach_status: string;
    payload: Record<string, unknown>;
    updated_at?: string | null;
}

export async function fetchProcessStatus(dealId: string): Promise<ProcessStatus> {
    const res = await api.get<APIResponse<ProcessStatus>>(`/deals/${dealId}/process-status`);
    return res.data.data;
}

export async function fetchBuyers(dealId: string): Promise<BuyerOutreach[]> {
    const res = await api.get<APIResponse<BuyerOutreach[]>>(`/deals/${dealId}/buyers`);
    return res.data.data;
}

export async function updateBuyerOutreach(dealId: string, buyerIdx: number, outreachStatus: string): Promise<void> {
    await api.patch(`/deals/${dealId}/buyers/${buyerIdx}`, { outreach_status: outreachStatus });
}

export async function downloadOutput(outputId: string, filename: string): Promise<void> {
    const res = await api.get<Blob>(`/outputs/${outputId}/download`, {
        responseType: 'blob',
    });
    const blobUrl = window.URL.createObjectURL(res.data);
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(blobUrl);
}

// ---- Tasks ----

export interface Task {
    task_id: string;
    deal_id: string;
    title: string;
    status: 'todo' | 'in_progress' | 'done' | 'blocked';
    priority: 'low' | 'medium' | 'high';
    owner: string;
    is_ai_generated: boolean;
    created_at: string | null;
}

export interface TaskCreatePayload {
    title: string;
    priority?: 'low' | 'medium' | 'high';
    owner?: string;
}

export interface TaskUpdatePayload {
    title?: string;
    status?: 'todo' | 'in_progress' | 'done' | 'blocked';
    priority?: 'low' | 'medium' | 'high';
    owner?: string;
}

export async function fetchTasks(dealId: string): Promise<Task[]> {
    await ensureAuthToken();
    const res = await api.get<APIResponse<{ tasks: Task[]; total: number }>>(`/deals/${dealId}/tasks`);
    return res.data.data.tasks;
}

export async function createTask(dealId: string, payload: TaskCreatePayload): Promise<Task> {
    await ensureAuthToken();
    const res = await api.post<APIResponse<Task>>(`/deals/${dealId}/tasks`, payload);
    return res.data.data;
}

export async function updateTask(dealId: string, taskId: string, update: TaskUpdatePayload): Promise<Task> {
    await ensureAuthToken();
    const res = await api.patch<APIResponse<Task>>(`/deals/${dealId}/tasks/${taskId}`, update);
    return res.data.data;
}

export async function deleteTask(dealId: string, taskId: string): Promise<void> {
    await ensureAuthToken();
    await api.delete(`/deals/${dealId}/tasks/${taskId}`);
}

// ── WorldMonitor (macro/market/risk data) ──

export interface WMHealthResponse {
    connected: boolean;
    enabled: boolean;
}

export interface WMMacroSignals {
    available: boolean;
    signals: {
        timestamp: string;
        verdict: string;
        bullishCount: number;
        totalCount: number;
        unavailable: boolean;
    } | null;
}

export interface WMFredSeries {
    available: boolean;
    series: {
        seriesId: string;
        title: string;
        observations: Array<{ date: string; value: number }>;
    } | null;
}

export interface WMRiskScore {
    region: string;
    staticBaseline: number;
    dynamicScore: number;
    combinedScore: number;
    trend: string;
    components: {
        newsActivity: number;
        ciiContribution: number;
        geoConvergence: number;
        militaryActivity: number;
    };
}

export interface WMRiskScoresResponse {
    available: boolean;
    ciiScores: WMRiskScore[];
    strategicRisks: Array<{
        region: string;
        level: string;
        score: number;
        factors: string[];
    }>;
}

export interface WMChokepoint {
    id: string;
    name: string;
    lat: number;
    lon: number;
    disruptionScore: number;
    status: string;
    activeWarnings: number;
    congestionLevel: string;
    affectedRoutes: string[];
    description: string;
}

export interface WMChokepointsResponse {
    available: boolean;
    chokepoints: WMChokepoint[];
}

export interface WMFearGreedResponse {
    available: boolean;
    data: {
        value: number;
        classification: string;
        previous_close: number;
        one_week_ago: number;
        one_month_ago: number;
    } | null;
}

export interface WMMarketQuote {
    symbol: string;
    name: string;
    price: number;
    change: number;
    changePercent: number;
    marketCap: number | null;
}

export async function fetchWMHealth(): Promise<WMHealthResponse> {
    const res = await api.get<WMHealthResponse>('/world-monitor/health');
    return res.data;
}

export async function fetchWMMacroSignals(): Promise<WMMacroSignals> {
    const res = await api.get<WMMacroSignals>('/world-monitor/macro-signals');
    return res.data;
}

export async function fetchWMFredSeries(seriesId: string, limit = 120): Promise<WMFredSeries> {
    const res = await api.get<WMFredSeries>(`/world-monitor/fred/${seriesId}`, { params: { limit } });
    return res.data;
}

export async function fetchWMRiskScores(): Promise<WMRiskScoresResponse> {
    const res = await api.get<WMRiskScoresResponse>('/world-monitor/risk-scores');
    return res.data;
}

export async function fetchWMChokepoints(): Promise<WMChokepointsResponse> {
    const res = await api.get<WMChokepointsResponse>('/world-monitor/chokepoints');
    return res.data;
}

export async function fetchWMFearGreed(): Promise<WMFearGreedResponse> {
    const res = await api.get<WMFearGreedResponse>('/world-monitor/fear-greed');
    return res.data;
}

export async function fetchWMMarketQuotes(symbols?: string): Promise<{ available: boolean; quotes: WMMarketQuote[] }> {
    const params = symbols ? { symbols } : {};
    const res = await api.get<{ available: boolean; quotes: WMMarketQuote[] }>('/world-monitor/market-quotes', { params });
    return res.data;
}

export { api, authApi }
