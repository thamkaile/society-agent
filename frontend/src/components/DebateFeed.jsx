import React, { useEffect, useRef, useState } from 'react';
import { Activity, Bot, CheckCircle2, Route, Sparkles, UserRound } from 'lucide-react';
import { AnimatedList, SpotlightCard } from './reactbits/VisualEffects';

const MOBILE_LONG_MESSAGE_LIMIT = 1100;
const MOBILE_QUERY = '(max-width: 640px)';

export default function DebateFeed({ events }) {
  const listRef = useRef(null);
  const feedEndRef = useRef(null);
  const shouldStickToBottomRef = useRef(true);
  const [isMobile, setIsMobile] = useState(false);
  const [expandedMessages, setExpandedMessages] = useState(() => new Set());

  useEffect(() => {
    const query = window.matchMedia(MOBILE_QUERY);
    const updateIsMobile = () => setIsMobile(query.matches);
    updateIsMobile();
    query.addEventListener('change', updateIsMobile);
    return () => query.removeEventListener('change', updateIsMobile);
  }, []);

  useEffect(() => {
    if (shouldStickToBottomRef.current) {
      feedEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [events]);

  const handleListScroll = (event) => {
    const node = event.currentTarget;
    const distanceFromBottom = node.scrollHeight - node.scrollTop - node.clientHeight;
    shouldStickToBottomRef.current = distanceFromBottom < 120;
  };

  const getMessageKind = (event) => {
    if (event.type === 'user_input') return 'user';
    if (event.type === 'agent_selection') return 'agent-selection';
    if (event.type === 'coordinator_routing') return 'routing';
    if (event.type === 'phase') return 'phase';
    if (event.type === 'error') return 'error';
    if (event.type === 'session_saved' || event.type === 'summarizer') return 'complete';
    if (event.type === 'agent_typing' || event.type === 'agent_delta') return 'assistant streaming';
    return 'assistant';
  };

  const initialsFor = (name) =>
    String(name || 'AI')
      .replace('/', ' ')
      .split(' ')
      .filter(Boolean)
      .map((part) => part[0])
      .join('')
      .substring(0, 2)
      .toUpperCase() || 'AI';

  const getIdentity = (event) => {
    if (event.type === 'user_input') {
      return { name: 'You', role: '', avatar: 'U' };
    }
    if (event.type === 'coordinator_routing') {
      const selected = event.selected_agent_identity || {};
      return {
        name: selected.name || event.coordinator_selected_agent || 'Selected specialist',
        role: selected.role || selected.description || 'Specialist agent',
        avatar: selected.avatar || initialsFor(selected.name || event.coordinator_selected_agent),
      };
    }
    if (event.type === 'agent_selection') {
      return { name: 'System', role: 'Routing summary', avatar: 'AI' };
    }
    const identity = event.agent_identity || {};
    const name = identity.name || event.agent || (event.type === 'session_saved' ? 'Report Generator' : 'Genesis');
    return {
      name,
      role: identity.role || identity.description || (event.agent ? 'Specialist agent' : 'Workspace assistant'),
      avatar: identity.avatar || initialsFor(name),
    };
  };

  const getTitle = (event) => {
    if (event.type === 'phase') return event.content || 'Phase update';
    if (event.type === 'session_saved') return 'Blueprint saved';
    return getIdentity(event).name;
  };

  const normalizedAgentNames = (event) => {
    const coreAgents = Array.isArray(event.core_agents) ? event.core_agents : [];
    const standbyAgents = Array.isArray(event.standby_specialists) ? event.standby_specialists : [];
    const names = [
      ...coreAgents,
      ...standbyAgents.map((specialist) => specialist?.role || specialist?.name || specialist?.id),
    ];
    const seen = new Set();
    return names
      .map((name) => String(name || '').trim())
      .filter((name) => {
        const key = name.toLowerCase();
        if (!name || seen.has(key)) return false;
        seen.add(key);
        return true;
      });
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const value = typeof timestamp === 'number' ? timestamp * 1000 : timestamp;
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const messageKeyFor = (event, idx) => event.id || event.streamingKey || `${event.type}-${idx}`;

  const renderTextContent = (text, event, messageKey, kind) => {
    const value = String(text || '');
    const canCollapse =
      isMobile &&
      kind !== 'user' &&
      kind !== 'phase' &&
      kind !== 'routing' &&
      kind !== 'agent-selection' &&
      value.length > MOBILE_LONG_MESSAGE_LIMIT;

    if (!canCollapse) return value;

    const expanded = expandedMessages.has(messageKey);
    const visibleText = expanded ? value : `${value.slice(0, MOBILE_LONG_MESSAGE_LIMIT).trimEnd()}...`;
    const label = expanded ? 'Show less' : 'Show more';

    return (
      <div className="long-message">
        <span>{visibleText}</span>
        <button
          type="button"
          className="long-message-toggle"
          onClick={() => {
            setExpandedMessages((current) => {
              const next = new Set(current);
              if (next.has(messageKey)) {
                next.delete(messageKey);
              } else {
                next.add(messageKey);
              }
              return next;
            });
          }}
          aria-expanded={expanded}
          aria-label={`${label} message from ${getIdentity(event).name}`}
        >
          {label}
        </button>
      </div>
    );
  };

  const renderContent = (event, messageKey, kind) => {
    if (event.type === 'phase') return 'Genesis is moving the boardroom into the next step.';
    if (event.type === 'coordinator_routing') {
      const selected = getIdentity(event);
      return (
        <div className="routing-card-content">
          <span>Coordinator selected</span>
          <strong>{selected.name}</strong>
          {event.reason && <p>{event.reason}</p>}
        </div>
      );
    }
    if (event.type === 'agent_selection') {
      const agentNames = normalizedAgentNames(event);
      const standbyCount = Array.isArray(event.standby_specialists) ? event.standby_specialists.length : 0;
      return (
        <div className="agent-selection-summary">
          <span className="agent-selection-label">Specialists selected for this response:</span>
          {agentNames.length > 0 && (
            <div className="agent-selection-chips" aria-label="Selected agents">
              {agentNames.map((name) => (
                <span key={name} className="agent-selection-chip">
                  {name}
                </span>
              ))}
            </div>
          )}
          {standbyCount === 0 && (
            <p className="agent-selection-note">No extra standby specialists selected.</p>
          )}
        </div>
      );
    }
    if (event.type === 'agent_typing') {
      return (
        <span className="typing-indicator" aria-label={`${event.agent || 'Agent'} is typing`}>
          <span />
          <span />
          <span />
        </span>
      );
    }
    if (typeof event.content === 'object') {
      return renderTextContent(JSON.stringify(event.content, null, 2), event, messageKey, kind);
    }
    return renderTextContent(event.content, event, messageKey, kind);
  };

  return (
    <section className="conversation-panel" aria-label="Live Genesis conversation">
      <div className="conversation-header">
        <div>
          <span className="panel-eyebrow">
            <Sparkles size={14} />
            Live Boardroom
          </span>
          <h2>Round-table debate</h2>
        </div>
        <span className="update-pill">
          <Activity size={14} className={events.length > 0 ? 'animate-pulse' : ''} />
          {events.length} updates
        </span>
      </div>

      <AnimatedList
        className="conversation-list"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        ref={listRef}
        onScroll={handleListScroll}
      >
        {events.map((event, idx) => {
          const messageKey = messageKeyFor(event, idx);
          const kind = getMessageKind(event);
          const identity = getIdentity(event);
          const Icon = kind === 'user' ? UserRound : kind === 'complete' ? CheckCircle2 : kind === 'routing' || kind === 'agent-selection' ? Route : Bot;
          return (
            <article
              key={messageKey}
              className={`chat-message ${kind}`}
              style={{ '--message-index': idx }}
            >
              <div className="chat-avatar" aria-hidden="true">
                {kind === 'assistant' || kind === 'streaming' || kind === 'routing' ? (
                  <span>{identity.avatar}</span>
                ) : (
                  <Icon size={17} />
                )}
              </div>
              <SpotlightCard className="chat-bubble">
                <div className="chat-message-header">
                  <div className="chat-message-identity">
                    <strong>{getTitle(event)}</strong>
                    {identity.role && kind !== 'user' && <small>{identity.role}</small>}
                  </div>
                  {event.timestamp && <time>{formatTime(event.timestamp)}</time>}
                </div>
                <div className="chat-message-content">{renderContent(event, messageKey, kind)}</div>
              </SpotlightCard>
            </article>
          );
        })}
        <div ref={feedEndRef} />
      </AnimatedList>
    </section>
  );
}
