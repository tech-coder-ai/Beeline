import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  ApprovalItem,
  AuditLogEntry,
  DataLensResponse,
  CatalogDatabase,
  CatalogRelationship,
  CatalogTable,
  ChatMessage,
  ChatSession,
  ChatTurn,
  Dashboard,
  DashboardWidget,
  ExecutionLog,
  BusinessTerm,
  BusinessRule,
  Abbreviation,
  GlossaryTerm,
  SavedQuery,
  SqlExplanation,
  SqlResult,
  SyncRun,
  SyncRunsPage,
} from './models';

const API = '/api/v1';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  // ------------------------------------------------------------- chat
  sendMessage(body: {
    session_id?: string | null;
    message: string;
    connector_id?: string | null;
    clarification_answer?: string | null;
    execute_preview_id?: string | null;
    execute_preview_sql?: string | null;
  }): Observable<ChatTurn> {
    return this.http.post<ChatTurn>(`${API}/chat`, body);
  }

  listSessions(includeArchived = false, search = ''): Observable<ChatSession[]> {
    const params: Record<string, string> = { include_archived: String(includeArchived) };
    if (search) params['search'] = search;
    return this.http.get<ChatSession[]>(`${API}/chat/sessions`, { params });
  }

  listMessages(sessionId: string): Observable<ChatMessage[]> {
    return this.http.get<ChatMessage[]>(`${API}/chat/sessions/${sessionId}/messages`);
  }

  updateSession(sessionId: string, update: Partial<ChatSession>): Observable<ChatSession> {
    return this.http.patch<ChatSession>(`${API}/chat/sessions/${sessionId}`, update);
  }

  deleteSession(sessionId: string): Observable<unknown> {
    return this.http.delete(`${API}/chat/sessions/${sessionId}`);
  }

  clearAllSessions(): Observable<{ sessions: number; messages: number }> {
    return this.http.delete<{ sessions: number; messages: number }>(`${API}/chat/sessions`, {
      params: { confirm: 'true' },
    });
  }

  // ------------------------------------------------------------- metadata
  listDatabases(): Observable<CatalogDatabase[]> {
    return this.http.get<CatalogDatabase[]>(`${API}/metadata/databases`);
  }

  listTables(databaseId?: string, search?: string): Observable<CatalogTable[]> {
    const params: Record<string, string> = {};
    if (databaseId) params['database_id'] = databaseId;
    if (search) params['search'] = search;
    return this.http.get<CatalogTable[]>(`${API}/metadata/tables`, { params });
  }

  getTable(tableId: string): Observable<CatalogTable> {
    return this.http.get<CatalogTable>(`${API}/metadata/tables/${tableId}`);
  }

  updateTable(tableId: string, update: Record<string, unknown>): Observable<unknown> {
    return this.http.patch(`${API}/metadata/tables/${tableId}`, update);
  }

  enrichTable(
    tableId: string,
    body: {
      description?: string | null;
      tags?: string[];
      glossary_hints?: { term: string; definition?: string | null }[];
      refresh_row_count?: boolean;
    } = {},
  ): Observable<{
    enriched: number;
    proposals: number;
    table_id: string;
    row_count?: number | null;
    note?: string;
    row_count_refresh?: Record<string, unknown>;
  }> {
    return this.http.post<{
      enriched: number;
      proposals: number;
      table_id: string;
      row_count?: number | null;
      note?: string;
      row_count_refresh?: Record<string, unknown>;
    }>(`${API}/metadata/tables/${tableId}/enrich`, body);
  }

  updateColumn(columnId: string, update: Record<string, unknown>): Observable<unknown> {
    return this.http.patch(`${API}/metadata/columns/${columnId}`, update);
  }

  listRelationships(tableId: string): Observable<CatalogRelationship[]> {
    return this.http.get<CatalogRelationship[]>(`${API}/metadata/relationships`, {
      params: { table_id: tableId },
    });
  }

  createRelationship(body: {
    from_table_id: string;
    to_table_id: string;
    from_columns: string[];
    to_columns: string[];
    relationship_type?: string;
    join_type?: string;
    description?: string | null;
  }): Observable<CatalogRelationship> {
    return this.http.post<CatalogRelationship>(`${API}/metadata/relationships`, body);
  }

  updateRelationship(
    relationshipId: string,
    body: Partial<{
      from_columns: string[];
      to_columns: string[];
      relationship_type: string;
      join_type: string;
      description: string | null;
      is_approved: boolean;
    }>,
  ): Observable<CatalogRelationship> {
    return this.http.patch<CatalogRelationship>(`${API}/metadata/relationships/${relationshipId}`, body);
  }

  deleteRelationship(relationshipId: string): Observable<{ deleted: string }> {
    return this.http.delete<{ deleted: string }>(`${API}/metadata/relationships/${relationshipId}`);
  }

  // ------------------------------------------------------------- approvals
  listApprovals(status = 'pending', entityType?: string): Observable<ApprovalItem[]> {
    const params: Record<string, string> = { status };
    if (entityType) params['entity_type'] = entityType;
    return this.http.get<ApprovalItem[]>(`${API}/metadata/approvals`, { params });
  }

  approvalCounts(): Observable<Record<string, number>> {
    return this.http.get<Record<string, number>>(`${API}/metadata/approvals/counts`);
  }

  decideApproval(
    id: string,
    action: 'approve' | 'reject' | 'edit',
    editedValue?: string,
  ): Observable<ApprovalItem> {
    return this.http.post<ApprovalItem>(`${API}/metadata/approvals/${id}`, {
      action,
      edited_value: editedValue ?? null,
    });
  }

  bulkDecide(ids: string[], action: 'approve' | 'reject'): Observable<unknown> {
    return this.http.post(`${API}/metadata/approvals/bulk/decide`, { ids, action });
  }

  importPreview(file: File, importType?: string): Observable<Record<string, unknown>> {
    const form = new FormData();
    form.append('file', file);
    const params: Record<string, string> = {};
    if (importType) params['import_type'] = importType;
    return this.http.post<Record<string, unknown>>(`${API}/metadata/import/preview`, form, { params });
  }

  importCommit(file: File, importType?: string): Observable<Record<string, unknown>> {
    const form = new FormData();
    form.append('file', file);
    const params: Record<string, string> = {};
    if (importType) params['import_type'] = importType;
    return this.http.post<Record<string, unknown>>(`${API}/metadata/import/commit`, form, { params });
  }

  // ------------------------------------------------------------- glossary
  listGlossary(search?: string): Observable<GlossaryTerm[]> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    return this.http.get<GlossaryTerm[]>(`${API}/glossary`, { params });
  }

  createTerm(term: GlossaryTerm): Observable<GlossaryTerm> {
    return this.http.post<GlossaryTerm>(`${API}/glossary`, term);
  }

  updateTerm(id: string, term: GlossaryTerm): Observable<GlossaryTerm> {
    return this.http.put<GlossaryTerm>(`${API}/glossary/${id}`, term);
  }

  deleteTerm(id: string): Observable<unknown> {
    return this.http.delete(`${API}/glossary/${id}`);
  }

  listBusinessTerms(search?: string, entity?: string): Observable<BusinessTerm[]> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    if (entity) params['entity'] = entity;
    return this.http.get<BusinessTerm[]>(`${API}/business-terms`, { params });
  }

  createBusinessTerm(term: BusinessTerm): Observable<BusinessTerm> {
    return this.http.post<BusinessTerm>(`${API}/business-terms`, term);
  }

  updateBusinessTerm(id: string, term: BusinessTerm): Observable<BusinessTerm> {
    return this.http.put<BusinessTerm>(`${API}/business-terms/${id}`, term);
  }

  deleteBusinessTerm(id: string): Observable<unknown> {
    return this.http.delete(`${API}/business-terms/${id}`);
  }

  listAbbreviations(search?: string): Observable<Abbreviation[]> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    return this.http.get<Abbreviation[]>(`${API}/abbreviations`, { params });
  }

  createAbbreviation(row: Abbreviation): Observable<Abbreviation> {
    return this.http.post<Abbreviation>(`${API}/abbreviations`, row);
  }

  updateAbbreviation(id: string, row: Abbreviation): Observable<Abbreviation> {
    return this.http.put<Abbreviation>(`${API}/abbreviations/${id}`, row);
  }

  deleteAbbreviation(id: string): Observable<unknown> {
    return this.http.delete(`${API}/abbreviations/${id}`);
  }

  listBusinessRules(search?: string, scope?: string): Observable<BusinessRule[]> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    if (scope) params['scope'] = scope;
    return this.http.get<BusinessRule[]>(`${API}/business-rules`, { params });
  }

  createBusinessRule(rule: BusinessRule): Observable<BusinessRule> {
    return this.http.post<BusinessRule>(`${API}/business-rules`, rule);
  }

  updateBusinessRule(id: string, rule: BusinessRule): Observable<BusinessRule> {
    return this.http.put<BusinessRule>(`${API}/business-rules/${id}`, rule);
  }

  deleteBusinessRule(id: string): Observable<unknown> {
    return this.http.delete(`${API}/business-rules/${id}`);
  }

  // ------------------------------------------------------------- sql & queries
  executeSql(sql: string, limit?: number): Observable<SqlResult> {
    return this.http.post<SqlResult>(`${API}/sql/execute`, { sql, limit });
  }

  explainSql(sql: string, connectorId?: string | null, question?: string | null): Observable<SqlExplanation> {
    return this.http.post<SqlExplanation>(`${API}/sql/explain`, {
      sql,
      connector_id: connectorId ?? null,
      question: question ?? null,
    });
  }

  listSavedQueries(): Observable<SavedQuery[]> {
    return this.http.get<SavedQuery[]>(`${API}/queries`);
  }

  saveQuery(query: SavedQuery): Observable<SavedQuery> {
    return this.http.post<SavedQuery>(`${API}/queries`, query);
  }

  runSavedQuery(id: string): Observable<SqlResult> {
    return this.http.post<SqlResult>(`${API}/queries/${id}/run`, {});
  }

  toggleBookmark(id: string): Observable<unknown> {
    return this.http.patch(`${API}/queries/${id}/bookmark`, {});
  }

  deleteQuery(id: string): Observable<unknown> {
    return this.http.delete(`${API}/queries/${id}`);
  }

  // ------------------------------------------------------------- dashboards
  listDashboards(): Observable<Dashboard[]> {
    return this.http.get<Dashboard[]>(`${API}/dashboards`);
  }

  createDashboard(dashboard: Partial<Dashboard>): Observable<Dashboard> {
    return this.http.post<Dashboard>(`${API}/dashboards`, dashboard);
  }

  getDashboard(id: string): Observable<Dashboard> {
    return this.http.get<Dashboard>(`${API}/dashboards/${id}`);
  }

  addWidget(dashboardId: string, widget: DashboardWidget): Observable<unknown> {
    return this.http.post(`${API}/dashboards/${dashboardId}/widgets`, widget);
  }

  removeWidget(dashboardId: string, widgetId: string): Observable<unknown> {
    return this.http.delete(`${API}/dashboards/${dashboardId}/widgets/${widgetId}`);
  }

  deleteDashboard(id: string): Observable<unknown> {
    return this.http.delete(`${API}/dashboards/${id}`);
  }

  // ------------------------------------------------------------- feedback
  submitFeedback(body: {
    execution_id?: string | null;
    message_id?: string | null;
    rating: 'up' | 'down';
    category?: string;
    comment?: string;
  }): Observable<unknown> {
    return this.http.post(`${API}/feedback`, body);
  }

  // ------------------------------------------------------------- admin
  getConnectors(): Observable<{
    default: string;
    available_types: string[];
    connectors: Record<string, unknown>[];
  }> {
    return this.http.get<{
      default: string;
      available_types: string[];
      connectors: Record<string, unknown>[];
    }>(`${API}/admin/connectors`);
  }

  testConnector(id: string): Observable<{ ok: boolean; message: string; latency_ms: number }> {
    return this.http.post<{ ok: boolean; message: string; latency_ms: number }>(
      `${API}/admin/connectors/${id}/test`,
      {},
    );
  }

  upsertConnector(body: Record<string, unknown>): Observable<{ id: string }> {
    return this.http.post<{ id: string }>(`${API}/admin/connectors`, body);
  }

  setDefaultConnector(id: string): Observable<{ default: string }> {
    return this.http.put<{ default: string }>(`${API}/admin/connectors/${id}/default`, {});
  }

  triggerSync(mode: 'full' | 'incremental', connectorId?: string): Observable<unknown> {
    return this.http.post(`${API}/admin/sync`, { mode, connector_id: connectorId ?? null });
  }

  listSyncRuns(options: { all?: boolean; limit?: number } = {}): Observable<SyncRunsPage> {
    const params: Record<string, string> = {};
    if (options.all) params['all'] = 'true';
    if (options.limit !== undefined) params['limit'] = String(options.limit);
    return this.http.get<SyncRunsPage>(`${API}/admin/sync/runs`, { params });
  }

  triggerEnrichment(tableIds: string[] = [], batchSize?: number): Observable<{ enriched: number; proposals: number; batch_size?: number }> {
    const body: { table_ids: string[]; batch_size?: number } = { table_ids: tableIds };
    if (batchSize !== undefined) body.batch_size = batchSize;
    return this.http.post<{ enriched: number; proposals: number; batch_size?: number }>(`${API}/admin/enrich`, body);
  }

  getConfig(): Observable<Record<string, unknown>> {
    return this.http.get<Record<string, unknown>>(`${API}/admin/config`);
  }

  getFeatureFlags(): Observable<Record<string, boolean>> {
    return this.http.get<Record<string, boolean>>(`${API}/admin/feature-flags`);
  }

  updateConfig(key: string, value: unknown): Observable<unknown> {
    return this.http.put(`${API}/admin/config`, { key, value });
  }

  auditLogs(action?: string): Observable<AuditLogEntry[]> {
    const params: Record<string, string> = {};
    if (action) params['action'] = action;
    return this.http.get<AuditLogEntry[]>(`${API}/admin/logs/audit`, { params });
  }

  executionLogs(search?: string): Observable<ExecutionLog[]> {
    const params: Record<string, string> = {};
    if (search) params['search'] = search;
    return this.http.get<ExecutionLog[]>(`${API}/admin/logs/executions`, { params });
  }

  usageAnalytics(): Observable<Record<string, unknown>> {
    return this.http.get<Record<string, unknown>>(`${API}/admin/analytics/usage`);
  }

  clearLogsAndAnalytics(includeSyncRuns = false): Observable<{ deleted: Record<string, number> }> {
    const params: Record<string, string> = { confirm: 'true' };
    if (includeSyncRuns) params['include_sync_runs'] = 'true';
    return this.http.delete<{ deleted: Record<string, number> }>(`${API}/admin/logs`, { params });
  }

  clearExecutionLogs(): Observable<{ deleted: Record<string, number> }> {
    return this.http.delete<{ deleted: Record<string, number> }>(
      `${API}/admin/logs/executions`,
      { params: { confirm: 'true' } },
    );
  }

  clearAuditLogs(): Observable<{ deleted: Record<string, number> }> {
    return this.http.delete<{ deleted: Record<string, number> }>(
      `${API}/admin/logs/audit`,
      { params: { confirm: 'true' } },
    );
  }

  health(): Observable<Record<string, string>> {
    return this.http.get<Record<string, string>>(`${API}/health/deep`);
  }
}
