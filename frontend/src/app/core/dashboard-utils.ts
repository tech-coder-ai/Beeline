import { BeelineResponse, SqlResult } from './models';

/** Build a dashboard widget snapshot from a chat response. */
export function buildWidgetSnapshot(response: BeelineResponse): SqlResult {
  const table = response.table ?? null;
  return {
    columns: table?.columns.map((c) => c.field) ?? [],
    rows: table?.rows.map((row) => table.columns.map((c) => row[c.field])) ?? [],
    row_count: table?.total_rows ?? response.stats?.row_count ?? 0,
    execution_time_ms: response.stats?.execution_time_ms ?? 0,
    truncated: table?.truncated ?? false,
    visualization: response.visualization,
    charts: response.charts ?? [],
    cards: response.cards ?? [],
    table,
    sql: response.sql ?? '',
  };
}

export function widgetTypeFor(response: BeelineResponse): string {
  if (response.charts?.length && response.table?.rows?.length) return 'chart';
  if (response.table?.rows?.length) return 'table';
  if (response.charts?.length) return 'chart';
  if (response.cards?.length) return 'kpi';
  return 'table';
}

export function widgetTitleFor(response: BeelineResponse): string {
  const refined = response.metadata?.['refined_prompt'];
  if (typeof refined === 'string' && refined.trim()) return refined.trim().slice(0, 80);
  if (response.summary) return response.summary.slice(0, 80);
  return 'Query result';
}
