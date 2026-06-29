import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clipboard,
  DollarSign,
  FileText,
  Layers,
  Loader2,
  MousePointer2,
  Rocket,
  ShieldCheck,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { API_CONNECTION_LABEL, getSession } from '../services/api';
import {
  BLUEPRINT_SECTIONS,
  countGeneratedSections,
  getSectionContent,
} from '../utils/blueprintSections';
import { Aurora, Beams } from '../components/reactbits/VisualEffects';

const SECTION_ICONS = {
  mvp_scope: Layers,
  business_plan: Wand2,
  technical_architecture: FileText,
  ux_strategy: MousePointer2,
  go_to_market: Rocket,
  risk_assessment: ShieldCheck,
  financial_plan: DollarSign,
};

export default function BlueprintPage({ chatId }) {
  const [sessionDetails, setSessionDetails] = useState(null);
  const [loadState, setLoadState] = useState('loading');
  const [message, setMessage] = useState('');
  const [activeSection, setActiveSection] = useState(BLUEPRINT_SECTIONS[0].id);
  const [copyState, setCopyState] = useState('');

  useEffect(() => {
    let ignore = false;

    async function loadBlueprint() {
      setLoadState('loading');
      try {
        const details = await getSession(chatId);
        if (ignore) return;
        setSessionDetails(details);
        setLoadState('ready');
      } catch (error) {
        if (ignore) return;
        setMessage(error.message);
        setLoadState('error');
      }
    }

    loadBlueprint();

    return () => {
      ignore = true;
    };
  }, [chatId]);

  const generatedCount = useMemo(
    () => countGeneratedSections(sessionDetails),
    [sessionDetails]
  );

  const copyBlueprint = async () => {
    if (!sessionDetails) return;
    const text = BLUEPRINT_SECTIONS.map((section) => {
      const content = getSectionContent(sessionDetails, section.id) || 'Not generated yet.';
      return `# ${section.label}\n${content}`;
    }).join('\n\n');

    try {
      await navigator.clipboard.writeText(text);
      setCopyState('Copied blueprint');
      window.setTimeout(() => setCopyState(''), 2200);
    } catch (error) {
      setCopyState('Copy failed');
      window.setTimeout(() => setCopyState(''), 2200);
    }
  };

  return (
    <div className="blueprint-page">
      <Aurora />
      <Beams />

      <header className="blueprint-topbar">
        <a className="back-link" href={`/chat/${encodeURIComponent(chatId)}`} aria-label="Return to chat">
          <ArrowLeft size={17} />
        </a>
        <div className="blueprint-title-group">
          <span>
            <Sparkles size={14} />
            Startup Blueprint
          </span>
          <h1>{sessionDetails?.title || sessionDetails?.user_idea || 'Blueprint Preview'}</h1>
        </div>
        <div className="blueprint-actions">
          <span className="connection-pill connected">
            <CheckCircle2 size={14} />
            {generatedCount}/{BLUEPRINT_SECTIONS.length} sections
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={copyBlueprint}
            disabled={!sessionDetails}
          >
            <Clipboard size={16} />
            Copy
          </button>
        </div>
      </header>

      {loadState === 'loading' && (
        <main className="blueprint-loading" role="status">
          <Loader2 size={24} className="animate-spin" />
          <span>Loading blueprint from {API_CONNECTION_LABEL}</span>
        </main>
      )}

      {loadState === 'error' && (
        <main className="blueprint-loading error" role="alert">
          <AlertCircle size={24} />
          <span>{message || 'Blueprint could not be loaded.'}</span>
          <a className="btn btn-secondary btn-small" href="/chat">
            Return to chat
          </a>
        </main>
      )}

      {loadState === 'ready' && (
        <main className="blueprint-layout">
          <nav className="blueprint-nav" aria-label="Blueprint sections">
            {BLUEPRINT_SECTIONS.map((section) => {
              const Icon = SECTION_ICONS[section.id] || FileText;
              const hasContent = Boolean(getSectionContent(sessionDetails, section.id));
              return (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className={`blueprint-nav-item ${activeSection === section.id ? 'active' : ''}`}
                  onClick={() => setActiveSection(section.id)}
                >
                  <Icon size={16} />
                  <span>{section.label}</span>
                  {hasContent ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                </a>
              );
            })}
          </nav>

          <article className="blueprint-document" aria-label="Generated blueprint document">
            <section className="blueprint-summary-band">
              <p className="eyebrow-line">Report-ready blueprint</p>
              <h2>{sessionDetails?.user_idea || sessionDetails?.title || 'Startup idea'}</h2>
              <p>
                Hybrid multi-agent architecture with hierarchical coordination, optional parallel evidence gathering,
                and sequential round-table debate.
              </p>
            </section>

            {BLUEPRINT_SECTIONS.map((section) => {
              const Icon = SECTION_ICONS[section.id] || FileText;
              const content = getSectionContent(sessionDetails, section.id);
              return (
                <section id={section.id} key={section.id} className="blueprint-section-card">
                  <div className="blueprint-section-heading">
                    <Icon size={19} />
                    <h2>{section.label}</h2>
                  </div>
                  {content ? (
                    <div className="blueprint-section-content">{content}</div>
                  ) : (
                    <p className="blueprint-empty">Not generated yet.</p>
                  )}
                </section>
              );
            })}
          </article>
        </main>
      )}

      {copyState && (
        <div className="toast" role="status" aria-live="polite">
          {copyState === 'Copied blueprint' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{copyState}</span>
        </div>
      )}
    </div>
  );
}
