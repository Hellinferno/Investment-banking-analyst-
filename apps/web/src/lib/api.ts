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
});

const authApi = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
    timeout: DEFAULT_API_TIMEOUT_MS,
});

function looksLikeJwt(token: string | null | undefined): boolean {
    return Boolean(token && token.split('.').length === 3);
}

let accessToken: string | null = looksLikeJwt(BOOTSTRAP_TOKEN) ? BOOTSTRAP_TOKEN : null;
let authBootstrapPromise: Promise<string | null> | null = null;
let currentUserCache: CurrentUserInfo | null = null;

async function bootstrapDevToken(): Promise<string | null> {
    if (!BOOTSTRAP_TOKEN || looksLikeJwt(BOOTSTRAP_TOKEN)) {
        return accessToken;
    }

    const res = await authApi.post<APIResponse<AuthTokenSession>>(
        '/auth/dev-token',
        { requested_role: DEV_AUTH_ROLE },
        {
            headers: {
                'X-Dev-API-Token': BOOTSTRAP_TOKEN,
            },
        }
    );
    accessToken = res.data.data.access_token;
    currentUserCache = res.data.data.user;
    return accessToken;
}

async function ensureAuthToken(): Promise<string | null> {
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
    review_status: 'draft' | 'in_review' | 'approved' | 'rejected';
    reviewer_notes?: string;
}

export interface CurrentUserInfo {
    user_id: string;
    tenant_id: string;
    role: string;
    email?: string | null;
    token_id?: string | null;
}

interface AuthTokenSession {
    access_token: string;
    token_type: string;
    expires_at: string;
    user: CurrentUserInfo;
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
