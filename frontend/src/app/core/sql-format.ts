import { format } from 'sql-formatter';

/** Pretty-print SQL for display; returns the original string if formatting fails. */
export function formatSql(sql: string): string {
  const trimmed = sql.trim();
  if (!trimmed) return sql;
  try {
    return format(trimmed, {
      language: 'hive',
      tabWidth: 2,
      keywordCase: 'upper',
      linesBetweenQueries: 1,
    });
  } catch {
    try {
      return format(trimmed, {
        language: 'sql',
        tabWidth: 2,
        keywordCase: 'upper',
        linesBetweenQueries: 1,
      });
    } catch {
      return sql;
    }
  }
}
