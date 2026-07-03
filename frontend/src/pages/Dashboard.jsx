import React, { useEffect, useRef, useState } from 'react';
import SessionSidebar from '../components/SessionSidebar';
import IdeaInput from '../components/IdeaInput';
import ThemeToggle from '../components/ThemeToggle';
import DebateFeed from '../components/DebateFeed';
import { BLUEPRINT_SECTIONS, countGeneratedSections, mergeBlueprintSection } from '../utils/blueprintSections';
import {
  API_BACKEND_HINT,
  deleteSession as deleteSessionRequest,
  getSession,
  healthCheck,
  isSessionNotFoundError,
  listSessions,
  streamSimulation,
} from '../services/api';
import { AlertCircle, ArrowLeft, CheckCircle2, FileText, Menu, RefreshCw, Trash2, X } from 'lucide-react';
import {
  AnimatedContent,
  Aurora,
  Beams,
  ShapeGrid,
  StarBorder,
} from '../components/reactbits/VisualEffects';

const HIDDEN_EVENT_TYPES = new Set([
  'status',
  'artifact',
  'agent_typing',
  'section_updated',
  'section_update',
  'blueprint_update',
  'session_created',
  'session_loaded',
  'impact_assessment',
  'round_started',
  'debate_needs_more',
]);

const STREAM_FLUSH_INTERVAL_MS = 400;

const STRUCTURED_DISPLAY_EVENT_TYPES = new Set([
  'agent_selection',
  'coordinator_routing',
  'session_saved',
]);

const STARTUP_CATEGORIES = [
  'Startup Idea',
  'Mobile App',
  'AI Product',
  'E-commerce',
  'Healthcare',
  'Education',
  'FinTech',
  'Sustainability',
];

function isUserFacingEvent(event) {
  if (!event) return false;
  const content = typeof event.content === 'string' ? event.content.trim() : '';
  if (HIDDEN_EVENT_TYPES.has(event.type)) return false;
  if (event.type === 'agent_delta') return Boolean(content);
  if (event.type === 'phase' || event.type === 'round_consensus') return Boolean(content);
  if (/^Updated section\s+/i.test(content)) return false;
  if (/started (debate|round)|is preparing| joined$/i.test(content)) return false;
  if (event.role === 'system' || event.agent === 'System' || event.name === 'system') return false;
  if (event.type === 'info' && /^(Starting|Product Manager defining|Genesis is convening)/i.test(content)) {
    return false;
  }
  if (content) return true;
  if (STRUCTURED_DISPLAY_EVENT_TYPES.has(event.type)) return true;
  return typeof event.content === 'object' && event.content !== null;
}

function eventContentSignature(content) {
  if (content === undefined || content === null) return '';
  if (typeof content === 'string') return content;
  try {
    return JSON.stringify(content);
  } catch (error) {
    return String(content);
  }
}

function eventIdentity(event) {
  if (event?.type === 'user_input' && event?.client_message_id) {
    return `client:${event.client_message_id}`;
  }
  if (event?.id) return `id:${event.id}`;
  if (event?.sequence !== undefined && event?.sequence !== null) {
    return `sequence:${event.run_id || event.chat_id || 'run'}:${event.sequence}`;
  }
  if (event?.streamingKey) return `stream:${event.streamingKey}`;
  if (event?.type === 'user_input') {
    return `user:${eventContentSignature(event.content)}`;
  }
  return [
    'fallback',
    event?.type || 'event',
    event?.agent || '',
    event?.phase || '',
    event?.timestamp || '',
    eventContentSignature(event?.content),
  ].join(':');
}

function dedupeEvents(eventList) {
  const positions = new Map();
  const deduped = [];

  eventList.forEach((event) => {
    const key = eventIdentity(event);
    const position = positions.get(key);
    if (position === undefined) {
      positions.set(key, deduped.length);
      deduped.push(event);
      return;
    }
    deduped[position] = event;
  });

  return deduped;
}

function chatIdFromLocation() {
  const match = window.location.pathname.match(/^\/chat\/([^/]+)\/?$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function chatPath(chatId) {
  return chatId ? `/chat/${encodeURIComponent(chatId)}` : '/chat';
}

function newRequestId(prefix) {
  if (window.crypto?.randomUUID) return `${prefix}-${window.crypto.randomUUID()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function Dashboard({ initialChatId = null, theme = 'light', onToggleTheme }) {
  const [sessions, setSessions] = useState([]);
  const [currentChatId, setCurrentChatId] = useState(null);
  const [sessionDetails, setSessionDetails] = useState(null);

  const [idea, setIdea] = useState('');
  const [streamActive, setStreamActive] = useState(false);
  const [currentPhase, setCurrentPhase] = useState(null);
  const [activeAgent, setActiveAgent] = useState(null);
  const [events, setEvents] = useState([]);

  const [connectionState, setConnectionState] = useState('checking');
  const [connectionMessage, setConnectionMessage] = useState('');
  const [sessionPendingDelete, setSessionPendingDelete] = useState(null);
  const [toastMessage, setToastMessage] = useState('');
  const [isSessionDrawerOpen, setIsSessionDrawerOpen] = useState(false);
  const activeStreamRef = useRef(null);
  const activeRunRef = useRef(null);
  const currentChatIdRef = useRef(null);
  const streamingBuffersRef = useRef(new Map());
  const streamingFlushTimerRef = useRef(null);

  const visibleEvents = dedupeEvents(events.filter(isUserFacingEvent));
  const generatedSectionCount = countGeneratedSections(sessionDetails);
  const hasConversation = visibleEvents.length > 0 || Boolean(sessionDetails);

  useEffect(() => {
    initializeConnection();
  }, [initialChatId]);

  useEffect(() => {
    currentChatIdRef.current = currentChatId;
  }, [currentChatId]);

  useEffect(() => {
    if (!isSessionDrawerOpen) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isSessionDrawerOpen]);

  useEffect(() => {
    return () => {
      abortActiveStream();
      clearStreamingBuffers();
    };
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      const chatId = chatIdFromLocation();
      if (chatId) {
        handleSelectSession(chatId, { updateUrl: false });
        return;
      }
      clearConversationState({ updateUrl: false });
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [streamActive]);

  const initializeConnection = async () => {
    const connected = await checkHealth();
    if (connected) {
      await loadSessionsList();
      const urlChatId = initialChatId || chatIdFromLocation();
      if (urlChatId) {
        await handleSelectSession(urlChatId, { updateUrl: false });
      }
    }
  };

  const navigateChat = (chatId, { replace = false } = {}) => {
    const path = chatPath(chatId);
    if (window.location.pathname === path) return;
    window.history[replace ? 'replaceState' : 'pushState']({}, '', path);
  };

  const abortActiveStream = () => {
    if (activeStreamRef.current?.controller) {
      activeStreamRef.current.controller.abort();
    }
    clearStreamingBuffers();
    activeStreamRef.current = null;
    activeRunRef.current = null;
  };

  const clearConversationState = ({ updateUrl = true, replaceUrl = false } = {}) => {
    abortActiveStream();
    currentChatIdRef.current = null;
    setCurrentChatId(null);
    setSessionDetails(null);
    setIdea('');
    setEvents([]);
    setCurrentPhase(null);
    setActiveAgent(null);
    setStreamActive(false);
    if (updateUrl) {
      navigateChat(null, { replace: replaceUrl });
    }
  };

  const recoverFromMissingSession = async () => {
    clearConversationState({ updateUrl: true, replaceUrl: true });
    setConnectionState('connected');
    setConnectionMessage('');
    await loadSessionsList();
  };

  const checkHealth = async () => {
    setConnectionState('checking');
    try {
      await healthCheck();
      setConnectionState('connected');
      setConnectionMessage('');
      return true;
    } catch (e) {
      setConnectionState('offline');
      setConnectionMessage(
        `Backend is not reachable. Start it on ${API_BACKEND_HINT} or set VITE_USE_DIRECT_API=true with VITE_API_BASE_URL.`
      );
      return false;
    }
  };

  const loadSessionsList = async () => {
    try {
      const data = await listSessions();
      setSessions(data);
    } catch (error) {
      console.error('Failed to load sessions:', error);
      setConnectionState((state) => (state === 'connected' ? 'request-failed' : state));
      setConnectionMessage(`Saved sessions could not be loaded: ${error.message}`);
    }
  };

  const handleSelectSession = async (chatId, { updateUrl = true, replaceUrl = false } = {}) => {
    clearStreamingBuffers();
    if (streamActive) {
      abortActiveStream();
      setStreamActive(false);
    }
    try {
      const details = await getSession(chatId);
      currentChatIdRef.current = chatId;
      setCurrentChatId(chatId);
      setSessionDetails(details);
      setIdea('');
      if (updateUrl) {
        navigateChat(chatId, { replace: replaceUrl });
      }

      const hydratedEvents = dedupeEvents(hydrateSessionEvents(details).filter(isUserFacingEvent));
      setEvents(
        hydratedEvents.length > 0
          ? hydratedEvents
          : [
              {
                type: 'info',
                content: `Loaded blueprint session for: "${details.user_idea || details.title || chatId}"`,
                timestamp: details.updated_at,
              },
            ]
      );
      setCurrentPhase('Loaded');
      setActiveAgent(null);
      return true;
    } catch (error) {
      console.error('Error loading session details:', error);
      if (isSessionNotFoundError(error)) {
        await recoverFromMissingSession();
        return false;
      }
      setConnectionState('request-failed');
      setConnectionMessage(`Session details could not be loaded: ${error.message}`);
      setEvents((prev) => dedupeEvents([
        ...prev,
        {
          type: 'error',
          content: `Failed to load session details: ${error.message}`,
          timestamp: Date.now() / 1000,
        },
      ]));
      return false;
    }
  };

  const handleSelectSessionFromDrawer = async (chatId) => {
    const didLoad = await handleSelectSession(chatId);
    if (didLoad) {
      setIsSessionDrawerOpen(false);
    }
  };

  const handleRequestDeleteSession = (session) => {
    if (streamActive) return;
    setIsSessionDrawerOpen(false);
    setSessionPendingDelete(session);
  };

  const handleCancelDeleteSession = () => {
    setSessionPendingDelete(null);
  };

  const handleConfirmDeleteSession = async () => {
    if (!sessionPendingDelete || streamActive) return;
    const chatId = sessionPendingDelete.id || sessionPendingDelete.chat_id;
    try {
      await deleteSessionRequest(chatId);
      setSessions((prev) => prev.filter((session) => (session.id || session.chat_id) !== chatId));
      setSessionPendingDelete(null);
      setToastMessage('Session deleted');
      window.setTimeout(() => setToastMessage(''), 2400);
      if (currentChatId === chatId) {
        clearConversationState({ updateUrl: true, replaceUrl: true });
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
      setConnectionState('request-failed');
      setConnectionMessage(`Session could not be deleted: ${error.message}`);
      setSessionPendingDelete(null);
    }
  };

  const handleGenerate = async () => {
    if (!idea.trim() || streamActive) return;

    const promptMessage = idea.trim();
    const runId = newRequestId('run');
    const clientMessageId = newRequestId('message');
    const controller = new AbortController();
    const startingChatId = currentChatId;
    clearStreamingBuffers();
    activeStreamRef.current = {
      controller,
      runId,
      chatId: startingChatId,
      lastSequence: 0,
      lastEventId: null,
      retryCount: 0,
    };
    activeRunRef.current = runId;
    setStreamActive(true);
    setCurrentPhase('Initializing');
    setActiveAgent(null);
    setEvents([
      {
        type: 'user_input',
        agent: 'User',
        client_message_id: clientMessageId,
        content: promptMessage,
        timestamp: Date.now() / 1000,
      },
      {
        type: 'info',
        content: currentChatId
          ? 'Genesis is refining this startup plan.'
          : 'Genesis is starting a new startup simulation.',
        timestamp: Date.now() / 1000,
      },
    ]);
    setIdea('');

    await streamSimulation({
      message: promptMessage,
      chatId: startingChatId,
      runId,
      clientMessageId,
      signal: controller.signal,
      onCursor: ({ runId: cursorRunId, lastSequence, lastEventId, retryCount }) => {
        if (activeRunRef.current !== runId) return;
        activeStreamRef.current = {
          ...(activeStreamRef.current || {}),
          controller,
          runId: cursorRunId || runId,
          lastSequence,
          lastEventId,
          retryCount,
        };
      },
      onRetry: ({ retryCount }) => {
        if (activeRunRef.current !== runId) return;
        setCurrentPhase('Reconnecting');
        setEvents((prev) => dedupeEvents([
          ...prev,
          {
            id: `reconnect:${runId}:${retryCount}`,
            type: 'info',
            agent: 'Genesis',
            content: 'Connection dipped. Reconnecting to the live run...',
            timestamp: Date.now() / 1000,
          },
        ]));
      },
      onEvent: (event) => {
        if (activeRunRef.current !== runId) return;
        if (event.run_id && event.run_id !== runId) return;
        const activeChat = activeStreamRef.current?.chatId;
        if (activeChat && event.chat_id && event.chat_id !== activeChat) return;
        setConnectionState('connected');
        setConnectionMessage('');

        if (event.type === 'session_created' && event.chat_id) {
          activeStreamRef.current = {
            ...activeStreamRef.current,
            chatId: event.chat_id,
          };
          currentChatIdRef.current = event.chat_id;
          setCurrentChatId(event.chat_id);
          navigateChat(event.chat_id, { replace: true });
          loadSessionsList();
        }

        if (event.type === 'phase' && event.content) {
          setCurrentPhase(event.content);
        }

        if (event.agent) {
          setActiveAgent(event.agent);
        }

        if (event.type === 'section_updated' && event.section) {
          applyBlueprintSectionEvent(event);
        }

        if (event.type === 'agent_typing') {
          return;
        }

        if (event.type === 'agent_delta') {
          bufferStreamingAgentEvent(event);
          return;
        }

        if (event.type === 'agent_response') {
          flushStreamingBuffers();
          streamingBuffersRef.current.delete(streamingKey(event));
          setEvents((prev) => finalizeStreamingAgentEvent(prev, event));
          return;
        }

        setEvents((prev) => dedupeEvents([...prev, event]));

        if (event.type === 'session_saved' && event.chat_id) {
          fetchUpdatedSession(event.chat_id, { hydrateEvents: true });
        }
      },
      onError: async (err) => {
        if (activeRunRef.current !== runId) return;
        clearStreamingBuffers();
        if (isSessionNotFoundError(err)) {
          await recoverFromMissingSession();
          return;
        }
        setEvents((prev) => dedupeEvents([
          ...prev,
          {
            type: 'error',
            content: `Simulation failed: ${err.message}`,
            timestamp: Date.now() / 1000,
          },
        ]));
        setConnectionState('request-failed');
        setConnectionMessage(`The stream request failed: ${err.message}`);
        setStreamActive(false);
        setCurrentPhase('Failed');
        setActiveAgent(null);
        activeStreamRef.current = null;
        activeRunRef.current = null;
      },
      onDone: () => {
        if (activeRunRef.current !== runId) return;
        flushStreamingBuffers();
        clearStreamingBuffers();
        setStreamActive(false);
        setCurrentPhase('Complete');
        setActiveAgent(null);
        activeStreamRef.current = null;
        activeRunRef.current = null;
        loadSessionsList();
      },
    });
  };

  const fetchUpdatedSession = async (chatId, { hydrateEvents = false } = {}) => {
    try {
      const details = await getSession(chatId);
      if (currentChatIdRef.current !== chatId) return;
      setSessionDetails(details);
      if (hydrateEvents) {
        const hydratedEvents = dedupeEvents(hydrateSessionEvents(details).filter(isUserFacingEvent));
        if (hydratedEvents.length > 0) {
          setEvents(hydratedEvents);
        }
      }
    } catch (e) {
      console.error('Error fetching completed session details:', e);
      if (isSessionNotFoundError(e)) {
        recoverFromMissingSession();
      }
    }
  };

  const applyBlueprintSectionEvent = (event) => {
    setSessionDetails((prev) => {
      const chatId = event.chat_id || currentChatId || prev?.chat_id;
      if (!chatId) return prev;
      const sections = mergeBlueprintSection(
        prev?.sections || {},
        event.section,
        event.after || { content: event.content || '' }
      );
      return {
        ...(prev || {}),
        id: prev?.id || chatId,
        chat_id: chatId,
        title: prev?.title || idea || 'Live blueprint',
        user_idea: prev?.user_idea || idea,
        sections,
      };
    });
  };

  const streamingKey = (event) => `${event.agent || 'Agent'}:${event.round || 0}:${event.phase || 'debate'}`;

  const clearStreamingFlushTimer = () => {
    if (streamingFlushTimerRef.current) {
      window.clearTimeout(streamingFlushTimerRef.current);
      streamingFlushTimerRef.current = null;
    }
  };

  const clearStreamingBuffers = () => {
    clearStreamingFlushTimer();
    streamingBuffersRef.current.clear();
  };

  const scheduleStreamingFlush = () => {
    if (streamingFlushTimerRef.current) return;
    streamingFlushTimerRef.current = window.setTimeout(() => {
      streamingFlushTimerRef.current = null;
      flushStreamingBuffers();
    }, STREAM_FLUSH_INTERVAL_MS);
  };

  const bufferStreamingAgentEvent = (event) => {
    const content = typeof event.content === 'string' ? event.content : '';
    const delta = typeof event.delta === 'string' ? event.delta : '';
    if (!content.trim() && !delta.trim()) return;

    const key = streamingKey(event);
    const previous = streamingBuffersRef.current.get(key);
    const bufferedContent = content.trim() ? content : `${previous?.content || ''}${delta}`;
    if (!String(bufferedContent || '').trim()) return;

    streamingBuffersRef.current.set(key, {
      ...(previous || {}),
      ...event,
      id: event.id || previous?.id || `stream:${key}`,
      type: 'agent_delta',
      content: bufferedContent,
      streamingKey: key,
    });
    scheduleStreamingFlush();
  };

  const flushStreamingBuffers = () => {
    clearStreamingFlushTimer();
    const bufferedEvents = Array.from(streamingBuffersRef.current.values()).filter((event) =>
      String(event.content || '').trim()
    );
    if (bufferedEvents.length === 0) return;
    setEvents((prev) => {
      const next = [...prev];
      bufferedEvents.forEach((event) => {
        const index = next.findIndex((item) => item.streamingKey === event.streamingKey);
        if (index < 0) {
          next.push(event);
          return;
        }
        next[index] = { ...next[index], ...event };
      });
      return dedupeEvents(next);
    });
  };

  const finalizeStreamingAgentEvent = (prev, event) => {
    const key = streamingKey(event);
    const finalEvent = {
      ...event,
      id: event.id || `final:${key}`,
      streamingKey: key,
    };
    const index = prev.findIndex((item) => item.streamingKey === key);
    if (index < 0) return dedupeEvents([...prev, finalEvent]);
    const next = [...prev];
    next[index] = finalEvent;
    return dedupeEvents(next);
  };

  const handleReset = () => {
    clearConversationState({ updateUrl: true, replaceUrl: false });
  };

  const applyCategoryTemplate = (category) => {
    setIdea(`I want to build a ${category} for [target users] that solves [problem].`);
  };

  const hydrateSessionEvents = (details) => {
    const messages = Array.isArray(details.messages) ? details.messages : [];
    return messages.map((message) => {
      const persistedEvent = message.event || message.metadata_json || {};
      return {
        ...persistedEvent,
        id: persistedEvent.id || message.id,
        type: persistedEvent.type || (message.role === 'user' ? 'user_input' : 'agent_response'),
        agent: persistedEvent.agent || message.agent_name || (message.role === 'user' ? 'User' : undefined),
        phase: persistedEvent.phase || message.phase,
        content: persistedEvent.content !== undefined ? persistedEvent.content : message.content,
        timestamp: persistedEvent.timestamp || message.created_at,
      };
    });
  };

  const renderStatus = () => {
    if (connectionState === 'checking') {
      return (
        <span className="connection-pill checking">
          <RefreshCw size={14} className="animate-spin" /> Checking
        </span>
      );
    }
    return (
      <span className="connection-pill offline">
        <AlertCircle size={14} /> {connectionState === 'request-failed' ? 'Request Failed' : 'Backend Offline'}
      </span>
    );
  };

  return (
    <div className="genesis-app">
      <Aurora />
      <Beams />
      <div className="antigravity-overlay">
        <ShapeGrid
          direction="diagonal"
          speed={0.5}
          borderColor={theme === 'dark' ? 'rgba(139, 188, 255, 0.12)' : 'rgba(66, 133, 244, 0.15)'}
          fadeColor={theme === 'dark' ? 'rgba(16, 20, 26, 0.92)' : 'rgba(255, 255, 255, 1)'}
          hoverFillColor={theme === 'dark' ? 'rgba(139, 188, 255, 0.08)' : 'rgba(66, 133, 244, 0.08)'}
          squareSize={48}
          shape="circle"
          hoverTrailAmount={6}
        />
      </div>
      <SessionSidebar
        sessions={sessions}
        currentChatId={currentChatId}
        onSelectSession={handleSelectSessionFromDrawer}
        onDeleteSession={handleRequestDeleteSession}
        streamActive={streamActive}
        isMobileOpen={isSessionDrawerOpen}
        onClose={() => setIsSessionDrawerOpen(false)}
      />
      {isSessionDrawerOpen && (
        <button
          type="button"
          className="drawer-backdrop"
          onClick={() => setIsSessionDrawerOpen(false)}
          aria-label="Close saved sessions drawer"
        />
      )}

      <main className={`chat-shell ${hasConversation ? 'has-conversation' : 'is-empty'}`}>
        <header className="chat-topbar">
          <div className="chat-brand">
            <button
              type="button"
              className="sessions-menu-button"
              onClick={() => setIsSessionDrawerOpen(true)}
              aria-label="Open saved sessions"
              aria-expanded={isSessionDrawerOpen}
              aria-controls="saved-sessions-sidebar"
            >
              <Menu size={18} />
            </button>
            <a href="/" className="back-link cursor-target" aria-label="Back to Genesis landing">
              <ArrowLeft size={17} />
            </a>
            <h1>Genesis Studio</h1>
          </div>
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </header>

        {connectionState !== 'connected' && (
          <StarBorder className="connection-banner" role="status">
            <AlertCircle size={17} />
            <span>{connectionMessage || 'Checking the backend connection...'}</span>
            <button type="button" onClick={initializeConnection}>
              Retry
            </button>
          </StarBorder>
        )}

        <section className="chat-stage">
          {!hasConversation ? (
            <AnimatedContent className="empty-state">
              <p className="eyebrow-line">Start with a short idea.</p>
              <h2>Describe your idea in one sentence.</h2>
              <p className="empty-state-copy">
                Short prompts work best. Genesis can ask follow-up questions after the simulation starts.
              </p>
              <div className="empty-state-format" aria-label="Recommended prompt format">
                <p>Recommended format</p>
                <code>I want to build [product/service] for [target users] that solves [problem].</code>
              </div>
              <div className="empty-state-chips" aria-label="Quick start categories">
                {STARTUP_CATEGORIES.map((category) => (
                  <button
                    key={category}
                    type="button"
                    className="quick-chip"
                    onClick={() => applyCategoryTemplate(category)}
                    disabled={streamActive}
                  >
                    {category}
                  </button>
                ))}
              </div>
              <div className="empty-state-structured" aria-label="Compact structured format">
                <p>Or use this compact format</p>
                <code>Product:</code>
                <code>Target customer:</code>
                <code>Problem:</code>
                <code>Market: optional</code>
              </div>
              <div className="empty-state-examples" aria-label="Example prompts">
                <p>Examples</p>
                <ul>
                  <li>I want to build an AI logistics platform for small businesses that reduces delivery costs.</li>
                  <li>I want to create a meal planning app for university students that helps them eat on a budget.</li>
                  <li>I want to start a cybersecurity consultancy for SMEs in Malaysia.</li>
                  <li>I want to build a SaaS tool for HR teams that automates employee onboarding.</li>
                </ul>
              </div>
            </AnimatedContent>
          ) : (
            <div className="active-workspace">
              {currentChatId && (
                <div className="workspace-toolbar" aria-label="Workspace actions">
                  <a className="btn btn-secondary btn-small cursor-target" href={`/chat/${encodeURIComponent(currentChatId)}/blueprint`}>
                    <FileText size={16} />
                    View Blueprint
                    {generatedSectionCount > 0 && (
                      <span className="btn-count">
                        {generatedSectionCount}/{BLUEPRINT_SECTIONS.length}
                      </span>
                    )}
                  </a>
                </div>
              )}
              <DebateFeed events={visibleEvents} />
            </div>
          )}
        </section>

        <div className="composer-dock">
          <IdeaInput
            idea={idea}
            setIdea={setIdea}
            onGenerate={handleGenerate}
            onReset={handleReset}
            streamActive={streamActive}
            currentChatId={currentChatId}
            currentPhase={currentPhase}
          />
        </div>
      </main>

      {sessionPendingDelete && (
        <div className="dialog-backdrop" role="presentation">
          <section
            className="confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-session-title"
          >
            <button
              type="button"
              className="dialog-close"
              onClick={handleCancelDeleteSession}
              aria-label="Cancel deletion"
            >
              <X size={17} />
            </button>
            <div className="dialog-icon danger" aria-hidden="true">
              <Trash2 size={18} />
            </div>
            <h2 id="delete-session-title">Delete saved session?</h2>
            <p>
              This removes "{sessionPendingDelete.title || 'Untitled Session'}" from saved sessions and cannot be restored.
            </p>
            <div className="dialog-actions">
              <button type="button" className="dialog-secondary" onClick={handleCancelDeleteSession}>
                Cancel
              </button>
              <button type="button" className="dialog-danger" onClick={handleConfirmDeleteSession}>
                Delete
              </button>
            </div>
          </section>
        </div>
      )}

      {toastMessage && (
        <div className="toast" role="status" aria-live="polite">
          <CheckCircle2 size={16} />
          <span>{toastMessage}</span>
        </div>
      )}
    </div>
  );
}
