import React, { createElement, useEffect, useMemo, useRef, useState } from 'react';
import Threads from './Threads';
import ShapeGrid from './ShapeGrid';function usePrefersReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = () => setReducedMotion(query.matches);
    updatePreference();
    query.addEventListener('change', updatePreference);
    return () => query.removeEventListener('change', updatePreference);
  }, []);

  return reducedMotion;
}

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

export function SpotlightCard({ as: Tag = 'div', children, className = '', onPointerMove, ...props }) {
  const handlePointerMove = (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--spot-x', `${event.clientX - rect.left}px`);
    event.currentTarget.style.setProperty('--spot-y', `${event.clientY - rect.top}px`);
    onPointerMove?.(event);
  };

  return (
    <Tag className={`rb-spotlight-card ${className}`} onPointerMove={handlePointerMove} {...props}>
      {children}
    </Tag>
  );
}

export function StarBorder({ as: Tag = 'div', children, className = '' }) {
  return <Tag className={`rb-star-border ${className}`}>{children}</Tag>;
}

export function TextType({
  text,
  as = 'span',
  typingSpeed = 52,
  initialDelay = 0,
  pauseDuration = 1800,
  deletingSpeed = 28,
  loop = true,
  className = '',
  showCursor = true,
  cursorCharacter = '|',
  cursorClassName = '',
  textColors = [],
  startOnVisible = false,
  ...props
}) {
  const reducedMotion = usePrefersReducedMotion();
  const containerRef = useRef(null);
  const [isVisible, setIsVisible] = useState(!startOnVisible);
  const [displayedText, setDisplayedText] = useState('');
  const [currentTextIndex, setCurrentTextIndex] = useState(0);
  const [currentCharIndex, setCurrentCharIndex] = useState(0);
  const [isDeleting, setIsDeleting] = useState(false);
  const textArray = useMemo(() => (Array.isArray(text) ? text : [text]), [text]);
  const Component = as;

  useEffect(() => {
    if (!startOnVisible || !containerRef.current) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setIsVisible(true);
      },
      { threshold: 0.2 }
    );

    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [startOnVisible]);

  useEffect(() => {
    if (reducedMotion) {
      setDisplayedText(textArray[0] || '');
      return undefined;
    }

    if (!isVisible || textArray.length === 0) return undefined;

    const currentText = textArray[currentTextIndex] || '';
    let timeoutId;

    if (isDeleting) {
      if (displayedText.length === 0) {
        setIsDeleting(false);
        setCurrentTextIndex((index) => (index + 1) % textArray.length);
        setCurrentCharIndex(0);
      } else {
        timeoutId = window.setTimeout(() => {
          setDisplayedText((value) => value.slice(0, -1));
        }, deletingSpeed);
      }
    } else if (currentCharIndex < currentText.length) {
      timeoutId = window.setTimeout(() => {
        setDisplayedText((value) => value + currentText[currentCharIndex]);
        setCurrentCharIndex((index) => index + 1);
      }, currentCharIndex === 0 ? initialDelay : typingSpeed);
    } else if (loop || currentTextIndex < textArray.length - 1) {
      timeoutId = window.setTimeout(() => setIsDeleting(true), pauseDuration);
    }

    return () => window.clearTimeout(timeoutId);
  }, [
    currentCharIndex,
    currentTextIndex,
    deletingSpeed,
    displayedText,
    initialDelay,
    isDeleting,
    isVisible,
    loop,
    pauseDuration,
    reducedMotion,
    textArray,
    typingSpeed,
  ]);

  return createElement(
    Component,
    {
      ref: containerRef,
      className: `rb-text-type ${className}`,
      ...props,
    },
    <span className="rb-text-type-content" style={{ color: textColors[currentTextIndex % textColors.length] }}>
      {displayedText}
    </span>,
    showCursor && !reducedMotion ? (
      <span className={`rb-text-type-cursor ${cursorClassName}`} aria-hidden="true">
        {cursorCharacter}
      </span>
    ) : null
  );
}

export { Threads, ShapeGrid };

export function LogoLoop({
  logos,
  speed = 72,
  direction = 'left',
  logoHeight = 34,
  gap = 34,
  fadeOut = true,
  fadeOutColor = 'rgba(255, 253, 249, 0.96)',
  scaleOnHover = true,
  ariaLabel = 'Technology logos',
  className = '',
}) {
  const reducedMotion = usePrefersReducedMotion();
  const copies = reducedMotion ? [0] : [0, 1, 2];
  const duration = Math.max(18, Math.round((logos.length * gap * 1.8) / Math.max(speed, 1)));

  return (
    <div
      className={`rb-logo-loop ${fadeOut ? 'rb-logo-loop-fade' : ''} ${scaleOnHover ? 'rb-logo-loop-scale' : ''} ${
        reducedMotion ? 'rb-logo-loop-static' : ''
      } ${className}`}
      style={{
        '--rb-logo-height': `${logoHeight}px`,
        '--rb-logo-gap': `${gap}px`,
        '--rb-logo-duration': `${duration}s`,
        '--rb-logo-direction': direction === 'right' ? 'reverse' : 'normal',
        '--rb-logo-fade': fadeOutColor,
      }}
      role="region"
      aria-label={ariaLabel}
    >
      <div className="rb-logo-loop-track">
        {copies.map((copyIndex) => (
          <ul className="rb-logo-loop-list" key={copyIndex} aria-hidden={copyIndex > 0}>
            {logos.map((item) => (
              <li className="rb-logo-loop-item" key={`${copyIndex}-${item.title}`}>
                {item.href ? (
                  <a href={item.href} target="_blank" rel="noreferrer noopener" aria-label={item.title}>
                    {item.node}
                    <span>{item.title}</span>
                  </a>
                ) : (
                  <span className="rb-logo-loop-pill">
                    {item.node}
                    <span>{item.title}</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        ))}
      </div>
    </div>
  );
}

export function ScrollRevealText({ children, as = 'h2', className = '', textClassName = '' }) {
  const ref = useRef(null);
  const reducedMotion = usePrefersReducedMotion();
  const Component = as;
  const words = useMemo(() => String(children).split(/(\s+)/), [children]);

  useEffect(() => {
    if (!ref.current || reducedMotion) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          ref.current?.classList.add('is-visible');
          observer.disconnect();
        }
      },
      { threshold: 0.25 }
    );

    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [reducedMotion]);

  return (
    <Component ref={ref} className={`rb-scroll-reveal ${reducedMotion ? 'is-visible' : ''} ${className}`}>
      <span className={textClassName}>
        {words.map((word, index) =>
          /^\s+$/.test(word) ? (
            word
          ) : (
            <span className="rb-scroll-reveal-word" style={{ '--word-index': index }} key={`${word}-${index}`}>
              {word}
            </span>
          )
        )}
      </span>
    </Component>
  );
}


