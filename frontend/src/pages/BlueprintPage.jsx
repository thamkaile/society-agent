import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  BadgeCheck,
  BarChart3,
  CheckCircle2,
  Clipboard,
  DollarSign,
  FileText,
  Layers,
  Loader2,
  MousePointer2,
  Rocket,
  Route,
  Scale,
  SearchCheck,
  ShieldCheck,
  Sparkles,
  Target,
  Wand2,
} from 'lucide-react';
import { API_CONNECTION_LABEL, getSession, isSessionNotFoundError } from '../services/api';
import {
  BLUEPRINT_SECTIONS,
  countGeneratedSections,
  getSection,
  getSectionContent,
} from '../utils/blueprintSections';
import { Aurora, Beams } from '../components/reactbits/VisualEffects';
import ThemeToggle from '../components/ThemeToggle';

const SECTION_ICONS = {
  executive_summary: BadgeCheck,
  problem_statement: Target,
  market_analysis: BarChart3,
  market_validation: SearchCheck,
  product_mvp: Layers,
  technical_architecture: FileText,
  financial_plan: DollarSign,
  marketing_strategy: Rocket,
  legal_compliance: Scale,
  risk_assessment: ShieldCheck,
  implementation_roadmap: Route,
  final_recommendation: Wand2,
};

export default function BlueprintPage({ chatId, theme = 'light', onToggleTheme }) {
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
        if (isSessionNotFoundError(error)) {
          window.history.replaceState({}, '', '/chat');
        }
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
      const value = getSection(sessionDetails, section.id);
      const metadata = value?.metadata || {};
      const content = value?.content || 'Not generated yet.';
      return [
        `# ${section.label}`,
        `Validated By: ${metadata.validated_by || value?.owner || section.owner}`,
        `Launch Confidence: ${metadata.launch_confidence ?? 0}%`,
        `Research Coverage: ${metadata.research_coverage || '0 / 0 Objectives'}`,
        `Consensus Level: ${metadata.consensus_level || 'Weak'}`,
        '',
        content,
      ].join('\n');
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
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
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
              const value = getSection(sessionDetails, section.id);
              const content = value?.content || '';
              const metadata = value?.metadata || {};
              const confidence = Number(metadata.launch_confidence || 0);
              return (
                <section id={section.id} key={section.id} className="blueprint-section-card">
                  <div className="blueprint-section-heading">
                    <div className="blueprint-section-title">
                      <span className="blueprint-section-icon" aria-hidden="true">
                        <Icon size={19} />
                      </span>
                      <div>
                        <p>{value?.owner || section.owner}</p>
                        <h2>{section.label}</h2>
                      </div>
                    </div>
                    <div className="confidence-meter" aria-label={`Launch confidence ${confidence}%`}>
                      <strong>{confidence}%</strong>
                      <span>Launch Confidence</span>
                    </div>
                  </div>
                  <div className="blueprint-metadata-row" aria-label={`${section.label} validation metadata`}>
                    <span>
                      <BadgeCheck size={14} />
                      Validated By {metadata.validated_by || value?.owner || section.owner}
                    </span>
                    <span>
                      <SearchCheck size={14} />
                      {metadata.research_coverage || '0 / 0 Objectives'}
                    </span>
                    <span className={`consensus-${String(metadata.consensus_level || 'Weak').toLowerCase()}`}>
                      <BarChart3 size={14} />
                      Consensus {metadata.consensus_level || 'Weak'}
                    </span>
                  </div>
                  {content ? (
                    <BlueprintSectionBody sectionValue={value} />
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

function BlueprintSectionBody({ sectionValue }) {
  const body = sectionValue?.body || {};
  const hasStructuredBody = Object.keys(body).length > 0;
  if (!hasStructuredBody) {
    return <div className="blueprint-section-content">{sectionValue?.content}</div>;
  }

  const rows = [
    ['Objective', body.objective],
    ['Key Findings', body.key_findings],
    ['Supporting Evidence', body.supporting_evidence],
    ['Risks', body.risks],
    ['Mitigation Strategy', body.mitigation_strategy],
    ['Recommendation', body.recommendation],
    ['Confidence Explanation', body.confidence_explanation],
  ];

  return (
    <div className="blueprint-section-content structured">
      {rows.map(([label, value]) => (
        <section key={label} className="blueprint-body-block">
          <h3>{label}</h3>
          {Array.isArray(value) ? (
            <ul>
              {value.map((item, index) => (
                <li key={`${label}-${index}`}>{item}</li>
              ))}
            </ul>
          ) : (
            <p>{value || 'Not specified.'}</p>
          )}
        </section>
      ))}
    </div>
  );
}
