import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  ApprovalItem,
  AuditLogEntry,
  BeelineResponse,
  CatalogDatabase,
  CatalogTable,
  ChatMessage,
  ChatSession,
  ChatTurn,
  Dashboard,
  DashboardWidget,
  ExecutionLog,
  GlossaryTerm,
  SavedQuery,
  SqlExplanation,
  SqlResult,
  SyncRun,
} from './models';

const API = '/api/v1';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  // ------------------------------------------------------------- chat
  sendMessage(body: {
    session_id?: string | null;
    message: string;
    clarification_answer?: string | null;
    execute_preview_id?: string | null;
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

  updateColumn(columnId: string, update: Record<string, unknown>): Observable<unknown> {
    return this.http.patch(`${API}/metadata/columns/${columnId}`, update);
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

  importPreview(file: File): Observable<Record<string, unknown>> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<Record<string, unknown>>(`${API}/metadata/import/preview`, form);
  }

  importCommit(file: File): Observable<Record<string, unknown>> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<Record<string, unknown>>(`${API}/metadata/import/commit`, form);
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

  // ------------------------------------------------------------- sql & queries
  executeSql(sql: string, limit?: number): Observable<SqlResult> {
    return this.http.post<SqlResult>(`${API}/sql/execute`, { sql, limit });
  }

  explainSql(sql: string): Observable<SqlExplanation> {
    return this.http.post<SqlExplanation>(`${API}/sql/explain`, { sql });
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

  triggerSync(mode: 'full' | 'incremental'): Observable<unknown> {
    return this.http.post(`${API}/admin/sync`, { mode });
  }

  listSyncRuns(): Observable<SyncRun[]> {
    return this.http.get<SyncRun[]>(`${API}/admin/sync/runs`);
  }

  triggerEnrichment(tableIds: string[] = []): Observable<unknown> {
    return this.http.post(`${API}/admin/enrich`, { table_ids: tableIds });
  }

  getConfig(): Observable<Record<string, unknown>> {
    return this.http.get<Record<string, unknown>>(`${API}/admin/config`);
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

  health(): Observable<Record<string, string>> {
    return this.http.get<Record<string, string>>(`${API}/health/deep`);
  }
}
