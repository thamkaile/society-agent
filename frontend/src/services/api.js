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

/**
 * Connects to the SSE chat stream using POST with fetch and ReadableStream reader.
 * Parses lines prefixed with "data: " and decodes them to JSON.
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
}) {
  try {
    const response = await fetch(apiUrl('/api/chat/stream'), {
      method: 'POST',
      credentials: 'include',
      signal,
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

    await requireOk(response, `HTTP error! status: ${response.status}`);

    if (!response.body) {
      throw new Error('Response body is empty (no readable stream)');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      
      // The last element may be a partial line, keep it in the buffer
      buffer = lines.pop();

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data:')) {
          const jsonStr = trimmed.substring(5).trim();
          if (jsonStr) {
            try {
              const event = JSON.parse(jsonStr);
              onEvent(event);
            } catch (err) {
              console.error('SSE JSON parsing error: ', err, 'Raw text: ', jsonStr);
            }
          }
        }
      }
    }

    // Parse any trailing line in buffer
    if (buffer.trim()) {
      const trimmed = buffer.trim();
      if (trimmed.startsWith('data:')) {
        const jsonStr = trimmed.substring(5).trim();
        if (jsonStr) {
          try {
            const event = JSON.parse(jsonStr);
            onEvent(event);
          } catch (err) {
            console.error('Trailing SSE JSON parsing error: ', err);
          }
        }
      }
    }

    if (onDone) onDone();
  } catch (error) {
    if (error?.name === 'AbortError') return;
    if (onError) onError(error);
  }
}
