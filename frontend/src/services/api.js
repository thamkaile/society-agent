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

async function fetchWithTimeout(url, options = {}, timeoutMs = 7000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...options,
      signal: options.signal || controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function healthCheck() {
  const response = await fetchWithTimeout(apiUrl('/api/health'), {}, 4500);
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`);
  }
  return response.json();
}

export async function listSessions() {
  const response = await fetch(apiUrl('/api/sessions'));
  if (!response.ok) {
    throw new Error(`Failed to list sessions: ${response.status}`);
  }
  return response.json();
}

export async function getSession(chatId) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(chatId)}`));
  if (!response.ok) {
    throw new Error(`Failed to load session details: ${response.status}`);
  }
  return response.json();
}

export async function deleteSession(chatId) {
  const response = await fetch(apiUrl(`/api/sessions/${encodeURIComponent(chatId)}`), {
    method: 'DELETE',
  });
  if (!response.ok) {
    throw new Error(`Failed to delete session: ${response.status}`);
  }
  return response.json();
}

/**
 * Connects to the SSE chat stream using POST with fetch and ReadableStream reader.
 * Parses lines prefixed with "data: " and decodes them to JSON.
 */
export async function streamSimulation({ message, chatId, onEvent, onError, onDone }) {
  try {
    const response = await fetch(apiUrl('/api/chat/stream'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message, chat_id: chatId || null }),
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => '');
      throw new Error(`HTTP error! status: ${response.status}. Detail: ${errorText}`);
    }

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
    if (onError) onError(error);
  }
}
