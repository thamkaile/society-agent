import React, { useEffect, useState } from 'react';
import SessionSidebar from '../components/SessionSidebar';
import IdeaInput from '../components/IdeaInput';
import AgentStatus from '../components/AgentStatus';
import DebateFeed from '../components/DebateFeed';
import ReportPanel from '../components/ReportPanel';
import {
  API_BACKEND_HINT,
  API_CONNECTION_LABEL,
  deleteSession as deleteSessionRequest,
  getSession,
  healthCheck,
  listSessions,
  streamSimulation,
} from '../services/api';
import { AlertCircle, ArrowLeft, CheckCircle2, RefreshCw, Sparkles, Trash2, X } from 'lucide-react';
import { AnimatedContent, Aurora, Beams, GradientText, StarBorder } from '../components/reactbits/VisualEffects';

export default function Dashboard() {
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

  const hasConversation = events.length > 0 || Boolean(sessionDetails);

  useEffect(() => {
    initializeConnection();
  }, []);

  const initializeConnection = async () => {
    const connected = await checkHealth();
    if (connected) {
      await loadSessionsList();
    }
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

  const handleSelectSession = async (chatId) => {
    if (streamActive) return;
    try {
      setCurrentChatId(chatId);
      const details = await getSession(chatId);
      setSessionDetails(details);
      setIdea('');

      const hydratedEvents = hydrateSessionEvents(details);
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
    } catch (error) {
      console.error('Error loading session details:', error);
      setConnectionState('request-failed');
      setConnectionMessage(`Session details could not be loaded: ${error.message}`);
      setEvents((prev) => [
        ...prev,
        {
          type: 'error',
          content: `Failed to load session details: ${error.message}`,
          timestamp: Date.now() / 1000,
        },
      ]);
    }
  };

  const handleRequestDeleteSession = (session) => {
    if (streamActive) return;
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
        setCurrentChatId(null);
        setSessionDetails(null);
        setIdea('');
        setEvents([]);
        setCurrentPhase(null);
        setActiveAgent(null);
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
    setStreamActive(true);
    setCurrentPhase('Initializing');
    setActiveAgent(null);
    setEvents([
      {
        type: 'user_input',
        agent: 'User',
        content: promptMessage,
        timestamp: Date.now() / 1000,
      },
      {
        type: 'info',
        content: currentChatId
          ? 'Genesis is refining this blueprint with the executive team.'
          : 'Genesis is convening a fresh boardroom for this startup idea.',
        timestamp: Date.now() / 1000,
      },
    ]);
    setIdea('');

    await streamSimulation({
      message: promptMessage,
      chatId: currentChatId,
      onEvent: (event) => {
        if (event.type === 'session_created' && event.chat_id) {
          setCurrentChatId(event.chat_id);
          loadSessionsList();
        }

        if (event.type === 'phase' && event.content) {
          setCurrentPhase(event.content);
        }

        if (event.agent) {
          setActiveAgent(event.agent);
        }

        setEvents((prev) => [...prev, event]);

        if (event.type === 'session_saved' && event.chat_id) {
          fetchUpdatedSession(event.chat_id);
        }
      },
      onError: (err) => {
        setEvents((prev) => [
          ...prev,
          {
            type: 'error',
            content: `Simulation failed: ${err.message}`,
            timestamp: Date.now() / 1000,
          },
        ]);
        setConnectionState('request-failed');
        setConnectionMessage(`The stream request failed: ${err.message}`);
        setStreamActive(false);
        setCurrentPhase('Failed');
        setActiveAgent(null);
      },
      onDone: () => {
        setStreamActive(false);
        setCurrentPhase('Complete');
        setActiveAgent(null);
        loadSessionsList();
      },
    });
  };

  const fetchUpdatedSession = async (chatId) => {
    try {
      const details = await getSession(chatId);
      setSessionDetails(details);
    } catch (e) {
      console.error('Error fetching completed session details:', e);
    }
  };

  const handleReset = () => {
    if (streamActive) return;
    setCurrentChatId(null);
    setSessionDetails(null);
    setIdea('');
    setEvents([]);
    setCurrentPhase(null);
    setActiveAgent(null);
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
    if (connectionState === 'connected') {
      return (
        <span className="connection-pill connected">
          <CheckCircle2 size={14} /> Connected
        </span>
      );
    }
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
      <SessionSidebar
        sessions={sessions}
        currentChatId={currentChatId}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleRequestDeleteSession}
        streamActive={streamActive}
      />

      <main className={`chat-shell ${hasConversation ? 'has-conversation' : 'is-empty'}`}>
        <header className="chat-topbar">
          <div className="chat-brand">
            <a href="/" className="back-link" aria-label="Back to Genesis landing">
              <ArrowLeft size={17} />
            </a>
            <div>
              <span>
                <Sparkles size={14} />
                Genesis Boardroom
              </span>
              <h1>Startup Blueprint Studio</h1>
            </div>
          </div>
          <div className="connection-cluster">
            {renderStatus()}
            <code>{API_CONNECTION_LABEL}</code>
          </div>
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
              <p className="eyebrow-line">Gemini-inspired startup intelligence</p>
              <GradientText as="h2">Ready when you are.</GradientText>
              <p>
                Bring a raw startup idea and Genesis will convene research, product, finance, technical,
                market, risk, and MVP voices into one decision-ready blueprint.
              </p>
            </AnimatedContent>
          ) : (
            <div className="active-workspace">
              <DebateFeed events={events} />
              <aside className="insight-stack" aria-label="Blueprint context">
                <details className="insight-section" open>
                  <summary>Executive team</summary>
                  <AgentStatus activeAgent={activeAgent} streamActive={streamActive} />
                </details>
                <details className="insight-section report-section-shell" open={Boolean(sessionDetails)}>
                  <summary>Blueprint output</summary>
                  <ReportPanel sessionDetails={sessionDetails} />
                </details>
              </aside>
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
            connectionState={connectionState}
            apiLabel={API_CONNECTION_LABEL}
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
