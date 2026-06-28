import React from 'react';

export function Aurora({ className = '' }) {
  return (
    <div className={`rb-aurora ${className}`} aria-hidden="true">
      <span className="rb-aurora-band rb-aurora-band-one" />
      <span className="rb-aurora-band rb-aurora-band-two" />
      <span className="rb-aurora-band rb-aurora-band-three" />
      <span className="rb-aurora-mesh" />
    </div>
  );
}

export function Beams({ className = '' }) {
  return <div className={`rb-beams ${className}`} aria-hidden="true" />;
}

export function GradientText({ as: Tag = 'span', children, className = '' }) {
  return <Tag className={`rb-gradient-text ${className}`}>{children}</Tag>;
}

export function AnimatedContent({ children, className = '', delay = 0 }) {
  return (
    <div className={`rb-animated-content ${className}`} style={{ '--rb-delay': `${delay}ms` }}>
      {children}
    </div>
  );
}

export function FadeContent({ children, className = '' }) {
  return <div className={`rb-fade-content ${className}`}>{children}</div>;
}

export function AnimatedList({ children, className = '' }) {
  return <div className={`rb-animated-list ${className}`}>{children}</div>;
}

export function SpotlightCard({ as: Tag = 'div', children, className = '' }) {
  return <Tag className={`rb-spotlight-card ${className}`}>{children}</Tag>;
}

export function StarBorder({ as: Tag = 'div', children, className = '' }) {
  return <Tag className={`rb-star-border ${className}`}>{children}</Tag>;
}
