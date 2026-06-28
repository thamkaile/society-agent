import React, { useState } from 'react';
import { FileText, Award, Layers, DollarSign, ListChecks, Map, AlertCircle } from 'lucide-react';

const TABS = [
  { id: 'overview', label: 'Overview', icon: Map },
  { id: 'business', label: 'Business Plan', icon: Award },
  { id: 'mvp', label: 'MVP Scope', icon: Layers },
  { id: 'technical', label: 'Technical', icon: FileText },
  { id: 'financial', label: 'Financials', icon: DollarSign },
  { id: 'actions', label: 'Action Items', icon: ListChecks }
];

function EmptySection({ children }) {
  return <p className="report-empty-copy">{children}</p>;
}

export default function ReportPanel({ sessionDetails }) {
  const [activeTab, setActiveTab] = useState('overview');

  if (!sessionDetails) {
    return (
      <div className="report-container">
        <div className="report-placeholder">
          <FileText size={48} className="text-muted" />
          <h3>Startup Blueprint</h3>
          <p>
            Select a saved session or generate a new boardroom run to view the
            final investor-ready output.
          </p>
        </div>
      </div>
    );
  }

  const { sections, user_idea, research_brief } = sessionDetails;

  const getSectionContent = (key) => {
    if (!sections || !sections[key]) return '';
    const section = sections[key];
    if (typeof section === 'object') {
      return section.content || section.text || JSON.stringify(section, null, 2);
    }
    return section;
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview': {
        let pmPlan = '';
        let researchSummary = '';
        let sources = [];

        if (research_brief) {
          pmPlan = research_brief.pm_research_plan || '';
          if (research_brief.research) {
            researchSummary = research_brief.research.research_summary || '';
            sources = research_brief.research.sources || [];
          } else if (typeof research_brief.research_brief === 'string') {
            try {
              const parsed = JSON.parse(research_brief.research_brief);
              researchSummary = parsed.research_summary || '';
              sources = parsed.sources || [];
            } catch (e) {}
          }
        }

        return (
          <div className="report-section">
            <h4>Blueprint Overview</h4>
            <div className="report-highlight">
              <strong>Core Startup Idea</strong>
              <p>"{user_idea}"</p>
            </div>

            {pmPlan && (
              <div className="report-brief-block">
                <h5>Product Manager Research Plan</h5>
                <div className="report-text">{pmPlan}</div>
              </div>
            )}

            {researchSummary && (
              <div className="report-brief-block success">
                <h5>Swarm Research Findings</h5>
                <div className="report-text">{researchSummary}</div>
              </div>
            )}

            {sources.length > 0 && (
              <div className="report-brief-block">
                <h5>Research Sources ({sources.length})</h5>
                <ul className="source-list">
                  {sources.map((url, i) => (
                    <li key={i}>
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        {url}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!pmPlan && !researchSummary && (
              <div className="report-placeholder compact">
                <AlertCircle size={24} />
                <p>No research data available for this session yet.</p>
              </div>
            )}
          </div>
        );
      }

      case 'business': {
        const bizContent = getSectionContent('business_plan');
        const pitchContent = getSectionContent('pitch_script');
        return (
          <div className="report-section">
            <h4>Business Strategy & Model</h4>
            {bizContent ? <div className="report-text">{bizContent}</div> : <EmptySection>No business plan generated yet.</EmptySection>}

            {pitchContent && (
              <div className="report-subsection">
                <h4>Elevator Pitch Script</h4>
                <div className="report-text quote">{pitchContent}</div>
              </div>
            )}
          </div>
        );
      }

      case 'mvp': {
        const mvpContent = getSectionContent('mvp_scope');
        return (
          <div className="report-section">
            <h4>MVP Feature Set & Bounds</h4>
            {mvpContent ? <div className="report-text">{mvpContent}</div> : <EmptySection>No MVP scope defined yet.</EmptySection>}
          </div>
        );
      }

      case 'technical': {
        const techContent = getSectionContent('technical_architecture');
        return (
          <div className="report-section">
            <h4>Technical Architecture & Stack</h4>
            {techContent ? <div className="report-text">{techContent}</div> : <EmptySection>No technical architecture specified yet.</EmptySection>}
          </div>
        );
      }

      case 'financial': {
        const finContent = getSectionContent('financial_projection');
        return (
          <div className="report-section">
            <h4>Financial Analysis & Unit Economics</h4>
            {finContent ? <div className="report-text">{finContent}</div> : <EmptySection>No financial projections calculated yet.</EmptySection>}
          </div>
        );
      }

      case 'actions': {
        const actionContent = getSectionContent('action_items');
        const uxContent = getSectionContent('ux_strategy');
        const marketContent = getSectionContent('marketing_strategy');

        return (
          <div className="report-section">
            <h4>Action Items & Next Steps</h4>
            {actionContent ? <div className="report-text">{actionContent}</div> : <EmptySection>No action items defined yet.</EmptySection>}

            {(uxContent || marketContent) && (
              <div className="report-subsection">
                <h4>Marketing & Product UX Strategy</h4>
                {uxContent && (
                  <div className="report-brief-block">
                    <h5>UX Design Priorities</h5>
                    <div className="report-text">{uxContent}</div>
                  </div>
                )}
                {marketContent && (
                  <div className="report-brief-block">
                    <h5>Go-To-Market Strategy</h5>
                    <div className="report-text">{marketContent}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      }

      default:
        return null;
    }
  };

  return (
    <div className="report-container">
      <div className="report-header">
        <div className="panel-title">
          <FileText size={18} />
          <h3>Blueprint Output</h3>
        </div>
        <div className="report-tabs" role="tablist" aria-label="Blueprint report sections">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                className={`report-tab ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => setActiveTab(tab.id)}
                type="button"
                role="tab"
                aria-selected={activeTab === tab.id}
              >
                <Icon size={14} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
      <div className="report-content">
        {renderTabContent()}
      </div>
    </div>
  );
}
