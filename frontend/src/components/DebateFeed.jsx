import React, { useEffect, useRef } from 'react';
import { Activity, Bot, CheckCircle2, Sparkles, UserRound } from 'lucide-react';
import { AnimatedList, SpotlightCard } from './reactbits/VisualEffects';

export default function DebateFeed({ events }) {
  const feedEndRef = useRef(null);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [events]);

  const getMessageKind = (event) => {
    if (event.type === 'user_input') return 'user';
    if (event.type === 'phase') return 'phase';
    if (event.type === 'error') return 'error';
    if (event.type === 'session_saved' || event.type === 'summarizer') return 'complete';
    return 'assistant';
  };

  const getTitle = (event) => {
    if (event.type === 'user_input') return 'You';
    if (event.type === 'phase') return event.content || 'Phase update';
    if (event.agent) return event.agent;
    if (event.type === 'session_saved') return 'Blueprint saved';
    return 'Genesis';
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const value = typeof timestamp === 'number' ? timestamp * 1000 : timestamp;
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const renderContent = (event) => {
    if (event.type === 'phase') return 'Genesis is moving the boardroom into the next step.';
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
          const Icon = kind === 'user' ? UserRound : kind === 'complete' ? CheckCircle2 : Bot;
          return (
            <article
              key={event.id || `${event.type}-${idx}`}
              className={`chat-message ${kind}`}
              style={{ '--message-index': idx }}
            >
              <div className="chat-avatar" aria-hidden="true">
                <Icon size={17} />
              </div>
              <SpotlightCard className="chat-bubble">
                <div className="chat-message-header">
                  <strong>{getTitle(event)}</strong>
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
