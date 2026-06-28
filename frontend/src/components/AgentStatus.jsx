import React from 'react';
import { UsersRound } from 'lucide-react';
import { SpotlightCard } from './reactbits/VisualEffects';

const KNOWN_AGENTS = [
  { name: 'Root Coordinator', label: 'Root', tone: 'blue' },
  { name: 'Product Manager', label: 'Product', tone: 'green' },
  { name: 'Technical Lead', label: 'Tech', tone: 'violet' },
  { name: 'Business Analyst', label: 'Business', tone: 'amber' },
  { name: 'Finance Analyst', label: 'Finance', tone: 'rose' },
  { name: 'UX Researcher', label: 'UX', tone: 'cyan' },
  { name: 'Marketing Strategist', label: 'Market', tone: 'pink' },
  { name: 'Risk & Compliance', label: 'Risk', tone: 'orange' },
  { name: 'MVP Scope Guard', label: 'MVP', tone: 'lime' },
  { name: 'Report Generator', label: 'Report', tone: 'indigo' },
];

export default function AgentStatus({ activeAgent, streamActive }) {
  const getInitials = (name) =>
    name
      .split(' ')
      .map((part) => part[0])
      .join('')
      .substring(0, 2);

  return (
    <section className="agent-panel" aria-label="AI executive team status">
      <div className="side-panel-heading">
        <UsersRound size={17} />
        <div>
          <span>Executive Team</span>
          <strong>{streamActive ? 'Reasoning live' : 'Ready'}</strong>
        </div>
      </div>

      <div className="agent-grid">
        {KNOWN_AGENTS.map((agent) => {
          const isCurrentActive = activeAgent === agent.name;
          return (
            <SpotlightCard
              key={agent.name}
              className={`agent-card ${agent.tone} ${isCurrentActive && streamActive ? 'active' : ''}`}
            >
              <div className="agent-card-avatar">{getInitials(agent.name)}</div>
              <div className="agent-card-copy">
                <span title={agent.name}>{agent.label}</span>
                <small>{isCurrentActive && streamActive ? 'Thinking' : 'Ready'}</small>
              </div>
            </SpotlightCard>
          );
        })}
      </div>
    </section>
  );
}
