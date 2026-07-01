import React, { useEffect, useRef } from 'react';
import { Activity, Bot, CheckCircle2, Route, Sparkles, UserRound } from 'lucide-react';
import { AnimatedList, SpotlightCard } from './reactbits/VisualEffects';

export default function DebateFeed({ events }) {
  const feedEndRef = useRef(null);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const getMessageKind = (event) => {
    if (event.type === 'user_input') return 'user';
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

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const value = typeof timestamp === 'number' ? timestamp * 1000 : timestamp;
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const renderContent = (event) => {
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
    if (event.type === 'agent_typing') {
      return (
        <span className="typing-indicator" aria-label={`${event.agent || 'Agent'} is typing`}>
          <span />
          <span />
          <span />
        </span>
      );
    }
    if (typeof event.content === 'object') return JSON.stringify(event.content, null, 2);
    return event.content;
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

      <AnimatedList className="conversation-list" role="log" aria-live="polite" aria-relevant="additions text">
        {events.map((event, idx) => {
          const kind = getMessageKind(event);
          const identity = getIdentity(event);
          const Icon = kind === 'user' ? UserRound : kind === 'complete' ? CheckCircle2 : kind === 'routing' ? Route : Bot;
          return (
            <article
              key={event.id || `${event.type}-${idx}`}
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
                <div className="chat-message-content">{renderContent(event)}</div>
              </SpotlightCard>
            </article>
          );
        })}
        <div ref={feedEndRef} />
      </AnimatedList>
    </section>
  );
}
