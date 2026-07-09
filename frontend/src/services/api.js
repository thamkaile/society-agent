const configuredApiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const useDirectApiInDev = import.meta.env.VITE_USE_DIRECT_API === 'true';

export const API_BASE_URL =
  configuredApiBaseUrl && (!import.meta.env.DEV || useDirectApiInDev)
    ? configuredApiBaseUrl
    : '';

export const API_CONNECTION_LABEL = API_BASE_URL || '/api via Vite proxy';
export const API_BACKEND_HINT = configuredApiBaseUrl || 'http://127.0.0.1:8000';

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

export class ApiError extends Error {
  constructor(message, { status = 0, code = null, detail = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function parseErrorResponse(response, fallbackMessage) {
  let payload = null;
  let text = '';
  try {
    text = await response.text();
    payload = text ? JSON.parse(text) : null;
  } catch (error) {
    payload = null;
  }

  const detail = payload?.detail ?? text;
  const code = typeof detail === 'object' ? detail.code : null;
  const message = typeof detail === 'object'
    ? detail.message || fallbackMessage
    : detail || fallbackMessage;
  return new ApiError(message, {
    status: response.status,
    code,
    detail,
  });
}

async function requireOk(response, fallbackMessage) {
  if (!response.ok) {
    throw await parseErrorResponse(response, fallbackMessage);
  }
  return response;
}

export function isSessionNotFoundError(error) {
  return error?.code === 'SESSION_NOT_FOUND' || error?.status === 404;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 7000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      credentials: options.credentials || 'include',
      signal: options.signal || controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function healthCheck() {
  const response = await fetchWithTimeout(apiUrl('/api/health'), {}, 4500);
  return (await requireOk(response, `Health check failed: ${response.status}`)).json();
}

export async function listSessions() {
  const response = await fetch(apiUrl('/api/sessions'), { credentials: 'include' });
  return (await requireOk(response, `Failed to list sessions: ${response.status}`)).json();
}

export async function getCurrentSession() {
  const response = await fetch(apiUrl('/api/sessions/current'), { credentials: 'include' });
  return (await requireOk(response, `Failed to load current session: ${response.status}`)).json();
}

export async function getSession(chatId) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(chatId)}`), {
    credentials: 'include',
  });
  return (await requireOk(response, `Failed to load session details: ${response.status}`)).json();
}

export async function deleteSession(chatId) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(chatId)}`), {
    method: 'DELETE',
    credentials: 'include',
  });
  return (await requireOk(response, `Failed to delete session: ${response.status}`)).json();
}

export async function createChatRun({
  message,
  chatId,
  runId,
  clientMessageId,
}) {
  const response = await fetch(apiUrl('/api/chat/runs'), {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message,
      chat_id: chatId || null,
      run_id: runId || null,
      client_message_id: clientMessageId || null,
    }),
  });
  return (await requireOk(response, `Failed to create chat run: ${response.status}`)).json();
}

export async function getChatRun(runId) {
  const response = await fetch(apiUrl(`/api/chat/runs/${encodeURIComponent(runId)}`), {
    credentials: 'include',
  });
  return (await requireOk(response, `Failed to load chat run: ${response.status}`)).json();
}

export async function listRunEvents(runId, { afterSequence, lastEventId } = {}) {
  const params = new URLSearchParams();
  if (afterSequence !== undefined && afterSequence !== null) {
    params.set('after_sequence', String(afterSequence));
  }
  if (lastEventId) {
    params.set('last_event_id', lastEventId);
  }
  const query = params.toString();
  const response = await fetch(
    apiUrl(`/api/chat/runs/${encodeURIComponent(runId)}/events${query ? `?${query}` : ''}`),
    { credentials: 'include' }
  );
  const payload = await (await requireOk(response, `Failed to list run events: ${response.status}`)).json();
  return Array.isArray(payload.events) ? payload.events.map((item) => item.event || item) : [];
}

function parseSseLine(line, onEvent) {
  const trimmed = line.trim();
  if (!trimmed.startsWith('data:')) return null;

  const jsonStr = trimmed.substring(5).trim();
  if (!jsonStr) return null;

  try {
    const event = JSON.parse(jsonStr);
    onEvent(event);
    return event;
  } catch (err) {
    console.error('SSE JSON parsing error: ', err, 'Raw text: ', jsonStr);
    return null;
  }
}

export async function streamRunEvents({
  runId,
  afterSequence,
  lastEventId,
  signal,
  onEvent,
}) {
  const params = new URLSearchParams();
  if (afterSequence !== undefined && afterSequence !== null) {
    params.set('after_sequence', String(afterSequence));
  }
  if (lastEventId) {
    params.set('last_event_id', lastEventId);
  }

  const query = params.toString();
  const response = await fetch(
    apiUrl(`/api/chat/runs/${encodeURIComponent(runId)}/stream${query ? `?${query}` : ''}`),
    {
      method: 'GET',
      credentials: 'include',
      signal,
      headers: {
        Accept: 'text/event-stream',
      },
    }
  );

  await requireOk(response, `Failed to stream run events: ${response.status}`);

  if (!response.body) {
    throw new Error('Response body is empty (no readable stream)');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let lastEvent = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      lastEvent = parseSseLine(line, onEvent) || lastEvent;
    }
  }

  if (buffer.trim()) {
    lastEvent = parseSseLine(buffer, onEvent) || lastEvent;
  }

  return lastEvent;
}

function waitForRetry(ms, signal) {
  if (signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    const timeoutId = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timeoutId);
        resolve();
      },
      { once: true }
    );
  });
}

/**
 * Creates a chat run and streams its events. If a mobile browser drops the
 * connection mid-run, reconnect from the last received sequence.
 */
export async function streamSimulation({
  message,
  chatId,
  runId,
  clientMessageId,
  signal,
  onEvent,
  onError,
  onDone,
  onCursor,
  onRetry,
  maxRetries = 3,
}) {
  let effectiveRunId = runId;
  let lastSequence = 0;
  let lastEventId = null;
  let retryCount = 0;

  try {
    const run = await createChatRun({
      message,
      chatId,
      runId,
      clientMessageId,
    });
    effectiveRunId = run.run_id || run.id || effectiveRunId;
    onCursor?.({ runId: effectiveRunId, lastSequence, lastEventId, retryCount });

    while (!signal?.aborted) {
      try {
        await streamRunEvents({
          runId: effectiveRunId,
          afterSequence: lastSequence || null,
          lastEventId,
          signal,
          onEvent: (event) => {
            if (event?.sequence !== undefined && event?.sequence !== null) {
              lastSequence = Math.max(lastSequence, Number(event.sequence) || 0);
            }
            if (event?.id) {
              lastEventId = event.id;
            }
            retryCount = 0;
            onCursor?.({ runId: effectiveRunId, lastSequence, lastEventId, retryCount });
            onEvent(event);
          },
        });

        const runState = await getChatRun(effectiveRunId);
        if (runState.status === 'failed') {
          throw new ApiError(runState.error || 'Chat run failed', {
            status: 0,
            code: 'RUN_FAILED',
            detail: runState,
          });
        }
        if (runState.status === 'completed') {
          onDone?.();
          return;
        }

        throw new ApiError('Stream ended before the run completed', {
          status: 0,
          code: 'STREAM_INTERRUPTED',
          detail: runState,
        });
      } catch (error) {
        if (error?.name === 'AbortError' || signal?.aborted) return;
        if (isSessionNotFoundError(error) || error?.code === 'RUN_FAILED') {
          onError?.(error);
          return;
        }

        if (retryCount >= maxRetries) {
          onError?.(error);
          return;
        }

        retryCount += 1;
        onCursor?.({ runId: effectiveRunId, lastSequence, lastEventId, retryCount });
        onRetry?.({ error, retryCount, runId: effectiveRunId, lastSequence, lastEventId });
        await waitForRetry(Math.min(800 * 2 ** (retryCount - 1), 3200), signal);
      }
    }
  } catch (error) {
    if (error?.name === 'AbortError') return;
    onError?.(error);
  }
}
