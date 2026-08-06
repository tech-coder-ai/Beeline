/** Normalize Angular HttpClient failures into user-facing and technical messages. */
export interface ParsedHttpError {
  summary: string;
  detail: string;
  code?: string;
  status?: number;
}

export function parseHttpError(err: unknown): ParsedHttpError {
  const http = err as {
    error?: unknown;
    status?: number;
    statusText?: string;
    message?: string;
  };

  const status = http.status;
  const body = http.error;
  let message = '';
  let code: string | undefined;

  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const record = body as Record<string, unknown>;
    code = record['code'] != null ? String(record['code']) : undefined;
    if (record['message'] != null) {
      message = String(record['message']);
    } else if (record['error'] != null && typeof record['error'] === 'string') {
      message = String(record['error']);
    } else if (record['detail'] != null) {
      message =
        typeof record['detail'] === 'string'
          ? record['detail']
          : JSON.stringify(record['detail'], null, 2);
    }
  } else if (typeof body === 'string' && body.trim()) {
    message = body.trim();
  }

  if (!message && http.message) {
    message = http.message;
  }

  let summary = message.trim();
  if (!summary) {
    if (status === 0 || status == null) {
      summary = 'Could not reach the server. Confirm the backend is running and reachable.';
    } else {
      summary = `Request failed (${status}${http.statusText ? ` ${http.statusText}` : ''}).`;
    }
  }

  if (status === 404 && summary.toLowerCase().includes('pending preview')) {
    summary =
      'This preview was already executed or is no longer pending. Check later messages in the thread or ask your question again.';
  } else if (status === 502 || code === 'connector_error') {
    summary = message || 'The analytics database connection or query failed.';
  } else if (status === 503 || code === 'llm_unavailable') {
    summary = message || 'The AI service is temporarily unavailable.';
  }

  const detailParts = [
    status != null ? `HTTP ${status}${http.statusText ? ` ${http.statusText}` : ''}` : null,
    code ? `Code: ${code}` : null,
    message || null,
    body && typeof body === 'object' ? JSON.stringify(body, null, 2) : null,
  ].filter((part): part is string => !!part && part.trim().length > 0);

  return {
    summary,
    detail: detailParts.join('\n\n'),
    code,
    status,
  };
}
