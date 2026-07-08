/** TypeScript mirrors of the backend contracts (BeelineResponse & friends). */

export type VisualizationType =
  | 'text' | 'grid' | 'kpi' | 'line' | 'area' | 'bar' | 'pie' | 'donut'
  | 'scatter' | 'heatmap' | 'treemap' | 'pivot' | 'mixed';

export type ResponseKind = 'answer' | 'clarification' | 'preview' | 'blocked' | 'error';

export interface ConfidenceBreakdown {
  business: number;
  metadata: number;
  sql: number;
  overall: number;
}

export interface KpiCard {
  label: string;
  value: string;
  raw_value?: number | null;
  unit?: string | null;
  trend?: number | null;
  trend_label?: string | null;
  severity: 'neutral' | 'good' | 'warning' | 'bad';
}

export interface ChartSeries {
  name: string;
  data: unknown[];
  type?: string | null;
}

export interface ChartSpec {
  chart_type: 'line' | 'area' | 'bar' | 'pie' | 'donut' | 'scatter' | 'heatmap' | 'treemap';
  title?: string | null;
  categories: unknown[];
  series: ChartSeries[];
  x_label?: string | null;
  y_label?: string | null;
  stacked: boolean;
}

export interface TableColumn {
  field: string;
  header: string;
  data_type: string;
  is_metric: boolean;
}

export interface TableSpec {
  columns: TableColumn[];
  rows: Record<string, unknown>[];
  total_rows: number;
  truncated: boolean;
}

export interface CostEstimate {
  estimated_rows_scanned?: number | null;
  estimated_result_rows?: number | null;
  estimated_runtime_seconds?: number | null;
  scan_bytes?: number | null;
  partition_pruned?: boolean | null;
  join_count: number;
  warnings: string[];
  blocked: boolean;
  block_reason?: string | null;
  suggestions: string[];
}

export interface SqlExplanation {
  summary: string;
  table_reasons: string[];
  filter_reasons: string[];
  aggregation_reasons: string[];
  grouping_reasons: string[];
}

export interface ClarificationOption {
  label: string;
  value: string;
  description?: string | null;
}

export interface ClarificationRequest {
  question: string;
  options: ClarificationOption[];
  allow_free_text: boolean;
}

export interface ExecutionStats {
  execution_time_ms?: number | null;
  row_count?: number | null;
  column_count?: number | null;
  connector_id?: string | null;
  cache_hit: boolean;
  reused_from_library: boolean;
}

export interface ResponseAction {
  action_id: string;
  label: string;
  icon?: string | null;
  confirm: boolean;
}

export interface BeelineResponse {
  kind: ResponseKind;
  execution_id?: string | null;
  summary: string;
  confidence: ConfidenceBreakdown;
  visualization: VisualizationType;
  cards: KpiCard[];
  charts: ChartSpec[];
  table?: TableSpec | null;
  insights: string[];
  recommendations: string[];
  follow_up_questions: string[];
  clarification?: ClarificationRequest | null;
  sql?: string | null;
  sql_explanation?: SqlExplanation | null;
  cost_estimate?: CostEstimate | null;
  stats?: ExecutionStats | null;
  tables_used: string[];
  filters_used: string[];
  metrics_used: string[];
  warnings: string[];
  actions: ResponseAction[];
  metadata: Record<string, unknown>;
  error?: string | null;
}

export interface ChatSession {
  id: string;
  title: string;
  is_pinned: boolean;
  is_archived: boolean;
  is_shared: boolean;
  share_token?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'clarification';
  content?: string | null;
  response_payload?: BeelineResponse | null;
  execution_id?: string | null;
  created_at: string;
}

export interface ChatTurn {
  session_id: string;
  message_id: string;
  response: BeelineResponse;
}

export interface CatalogDatabase {
  id: string;
  name: string;
  connector_id: string;
  table_count: number;
  last_synced_at?: string | null;
}

export interface CatalogColumn {
  id: string;
  name: string;
  position: number;
  data_type: string;
  inferred_semantic_type?: string | null;
  description?: string | null;
  tags?: string[] | null;
  classification?: string | null;
  is_pii: boolean;
  is_partition: boolean;
  null_percentage?: number | null;
  distinct_count?: number | null;
  sample_values?: unknown[] | null;
  top_values?: { value: string; count: number }[] | null;
}

export interface CatalogTable {
  id: string;
  name: string;
  table_type: string;
  description?: string | null;
  owner?: string | null;
  steward?: string | null;
  tags?: string[] | null;
  classification?: string | null;
  row_count?: number | null;
  size_bytes?: number | null;
  storage_format?: string | null;
  partition_columns?: string[] | null;
  last_synced_at?: string | null;
  usage_count: number;
  database_name?: string;
  column_count: number;
  columns?: CatalogColumn[];
}

export interface GlossaryTerm {
  id?: string;
  term: string;
  definition: string;
  business_meaning?: string | null;
  examples: string[];
  owner?: string | null;
  tags: string[];
  synonyms: string[];
  status?: string;
  source?: string;
  created_at?: string;
}

export interface ApprovalItem {
  id: string;
  entity_type: string;
  entity_id: string;
  entity_label: string;
  field: string;
  current_value?: string | null;
  proposed_value: string;
  source: string;
  confidence?: number | null;
  rationale?: string | null;
  status: string;
  created_at: string;
}

export interface SavedQuery {
  id?: string;
  name: string;
  description?: string | null;
  sql: string;
  connector_id?: string | null;
  prompt?: string | null;
  tags: string[];
  is_bookmarked?: boolean;
  last_run_at?: string | null;
  run_count?: number;
  created_at?: string;
}

export interface DashboardWidget {
  id?: string;
  title: string;
  widget_type: string;
  size: string;
  position?: number;
  sql?: string | null;
  connector_id?: string | null;
  visualization?: Record<string, unknown> | null;
  snapshot?: SqlResult | null;
  source_execution_id?: string | null;
}

export interface Dashboard {
  id?: string;
  name: string;
  description?: string | null;
  refresh_interval_seconds?: number | null;
  is_shared?: boolean;
  share_token?: string | null;
  created_at?: string;
  updated_at?: string;
  widgets: DashboardWidget[];
}

export interface SqlResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  execution_time_ms: number;
  truncated: boolean;
  visualization: VisualizationType;
  charts: ChartSpec[];
  cards: KpiCard[];
  table?: TableSpec | null;
  sql: string;
}

export interface SyncRun {
  id: string;
  connector_id: string;
  mode: string;
  status: string;
  tables_synced: number;
  columns_synced: number;
  error?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface ExecutionLog {
  id: string;
  prompt: string;
  status: string;
  optimized_sql?: string | null;
  row_count?: number | null;
  execution_time_ms?: number | null;
  confidence?: ConfidenceBreakdown | null;
  warnings?: string[] | null;
  error?: string | null;
  llm_model?: string | null;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  user_id: string;
  action: string;
  entity_type?: string | null;
  entity_id?: string | null;
  detail?: Record<string, unknown> | null;
  severity: string;
  created_at: string;
}
