import React, { useRef } from 'react';
import { Moon, Sun } from 'lucide-react';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';

gsap.registerPlugin(useGSAP);

export default function ThemeToggle({ theme, onToggle }) {
  const scopeRef = useRef(null);
  const thumbRef = useRef(null);
  const sunRef = useRef(null);
  const moonRef = useRef(null);

  useGSAP(() => {
    const isDark = theme === 'dark';

    gsap.to(thumbRef.current, {
      x: isDark ? 28 : 0,
      duration: 0.42,
      ease: 'power3.out',
    });

    gsap.to(sunRef.current, {
      opacity: isDark ? 0.36 : 1,
      rotate: isDark ? -70 : 0,
      scale: isDark ? 0.8 : 1,
      duration: 0.34,
      ease: 'power2.out',
    });

    gsap.to(moonRef.current, {
      opacity: isDark ? 1 : 0.36,
      rotate: isDark ? 0 : 70,
      scale: isDark ? 1 : 0.8,
      duration: 0.34,
      ease: 'power2.out',
    });
  }, { scope: scopeRef, dependencies: [theme], revertOnUpdate: true });

  return (
    <button
      ref={scopeRef}
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      <span className="theme-toggle-track">
        <span ref={thumbRef} className="theme-toggle-thumb" aria-hidden="true" />
        <span ref={sunRef} className="theme-toggle-icon theme-toggle-icon-sun" aria-hidden="true">
          <Sun size={14} />
        </span>
        <span ref={moonRef} className="theme-toggle-icon theme-toggle-icon-moon" aria-hidden="true">
          <Moon size={14} />
        </span>
      </span>
      <span className="theme-toggle-label">{theme === 'dark' ? 'Dark' : 'Light'}</span>
    </button>
  );
}
