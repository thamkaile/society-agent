import React, { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  ArrowRight,
  BrainCircuit,
  Check,
  CircleDollarSign,
  FileText,
  Layers3,
  Network,
  Search,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from 'lucide-react';
import {
  AnimatedContent,
  Aurora,
  Beams,
  GradientText,
  SpotlightCard,
  StarBorder,
} from '../components/reactbits/VisualEffects';

gsap.registerPlugin(ScrollTrigger);

const proofMetrics = [
  ['10', 'specialist agents'],
  ['6', 'blueprint sections'],
  ['Live', 'debate stream'],
  ['Saved', 'session memory'],
];

const previewMessages = [
  ['Research', 'The market is promising, but the wedge needs sharper evidence.'],
  ['Product', 'Start with one painful workflow and defer the nice-to-have suite.'],
  ['Finance', 'Unit economics work only if acquisition stays inside the pilot channel.'],
  ['Consensus', 'Launch the narrow MVP, measure paid conversion, then expand.'],
];

const deliverables = [
  ['Market research', Search],
  ['Business model', CircleDollarSign],
  ['Technical architecture', Network],
  ['MVP roadmap', Layers3],
  ['Risk assessment', ShieldCheck],
  ['Investor pitch', FileText],
];

function GenesisLogo() {
  return (
    <a href="/" className="genesis-logo" aria-label="Genesis home">
      <span className="genesis-logo-mark">G</span>
      <span>Genesis</span>
    </a>
  );
}

function ProductPreview() {
  return (
    <StarBorder className="product-preview" aria-label="Genesis product preview">
      <div className="preview-toolbar">
        <div>
          <span>Live Boardroom</span>
          <strong>Startup Blueprint Studio</strong>
        </div>
        <span className="preview-status">
          <span />
          Reasoning
        </span>
      </div>
      <div className="preview-grid">
        <div className="preview-feed">
          {previewMessages.map(([role, message], index) => (
            <article className={role === 'Consensus' ? 'preview-message consensus' : 'preview-message'} key={role}>
              <span>{role}</span>
              <p>{message}</p>
              <small>0{index + 1}:2{index}</small>
            </article>
          ))}
        </div>
        <div className="preview-report">
          <div className="preview-report-header">
            <FileText size={16} />
            <span>Blueprint Output</span>
          </div>
          <div className="preview-score">
            <strong>87%</strong>
            <span>Launch confidence</span>
          </div>
          {['Niche wedge selected', 'MVP scope contained', 'Supplier risk flagged'].map((item) => (
            <div className="preview-check" key={item}>
              <Check size={14} />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </div>
    </StarBorder>
  );
}

function useLandingMotion() {
  const rootRef = useRef(null);

  useEffect(() => {
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        '.hero-reveal',
        { autoAlpha: 0, y: reduceMotion ? 0 : 20 },
        {
          autoAlpha: 1,
          y: 0,
          duration: reduceMotion ? 0 : 0.64,
          stagger: reduceMotion ? 0 : 0.07,
          ease: 'power3.out',
        }
      );

      gsap.utils.toArray('.reveal').forEach((element) => {
        gsap.fromTo(
          element,
          { autoAlpha: 0, y: reduceMotion ? 0 : 24 },
          {
            autoAlpha: 1,
            y: 0,
            duration: reduceMotion ? 0 : 0.56,
            ease: 'power3.out',
            scrollTrigger: {
              trigger: element,
              start: 'top 86%',
              toggleActions: 'play none none none',
            },
          }
        );
      });
    }, rootRef);

    return () => ctx.revert();
  }, []);

  return rootRef;
}

export default function LandingPage() {
  const rootRef = useLandingMotion();

  return (
    <div ref={rootRef} className="landing-page">
      <Aurora />
      <Beams />

      <header className="landing-nav">
        <div className="landing-nav-inner">
          <GenesisLogo />
          <nav className="landing-nav-links" aria-label="Primary navigation">
            <a href="#proof">Proof</a>
            <a href="#process">Process</a>
            <a href="#deliverables">Deliverables</a>
            <a className="btn btn-primary btn-small" href="/chat">
              Open Studio
            </a>
          </nav>
        </div>
      </header>

      <main>
        <section className="landing-hero" id="top">
          <div className="section-shell hero-grid">
            <AnimatedContent className="hero-copy">
              <p className="eyebrow-line hero-reveal">
                <Sparkles size={15} />
                AI Startup Boardroom
              </p>
              <GradientText as="h1" className="hero-title hero-reveal">
                Genesis
              </GradientText>
              <p className="hero-subtitle hero-reveal">
                Turn raw startup ideas into investor-ready blueprints through a live executive team
                that researches, debates, narrows, and packages the decision.
              </p>
              <div className="hero-actions hero-reveal">
                <a className="btn btn-primary" href="/chat">
                  Open Genesis
                  <ArrowRight size={16} />
                </a>
                <a className="btn btn-secondary" href="#process">
                  View process
                </a>
              </div>
            </AnimatedContent>

            <ProductPreview />
          </div>
        </section>

        <section id="proof" className="landing-section proof-band">
          <div className="section-shell proof-grid reveal">
            {proofMetrics.map(([value, label]) => (
              <SpotlightCard as="article" className="proof-card" key={label}>
                <strong>{value}</strong>
                <span>{label}</span>
              </SpotlightCard>
            ))}
          </div>
        </section>

        <section id="process" className="landing-section">
          <div className="section-shell split-section">
            <div className="section-heading reveal">
              <p className="eyebrow-line">Workflow</p>
              <h2>From instinct to evidence to a decision you can act on.</h2>
              <p>
                Genesis keeps the work legible: the prompt, research evidence, agent debate, final
                tradeoffs, and blueprint sections stay connected.
              </p>
            </div>
            <div className="process-list reveal">
              {[
                ['Capture idea', 'Start with the market, user, constraint, or product seed.'],
                ['Research market', 'Gather external signals and pressure-test assumptions.'],
                ['Debate tradeoffs', 'Let specialist agents challenge the plan from their lens.'],
                ['Package blueprint', 'Resolve into business, MVP, technical, financial, and action sections.'],
              ].map(([title, body], index) => (
                <SpotlightCard as="article" className="process-step" key={title}>
                  <span>{index + 1}</span>
                  <div>
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </div>
                </SpotlightCard>
              ))}
            </div>
          </div>
        </section>

        <section id="deliverables" className="landing-section">
          <div className="section-shell">
            <div className="section-heading reveal">
              <p className="eyebrow-line">Deliverables</p>
              <h2>A founder-ready package from every run.</h2>
            </div>
            <div className="deliverable-grid reveal">
              {deliverables.map(([item, Icon]) => (
                <SpotlightCard as="article" className="deliverable-card" key={item}>
                  <Icon size={19} />
                  <span>{item}</span>
                </SpotlightCard>
              ))}
            </div>
          </div>
        </section>

        <section className="landing-section final-cta">
          <div className="section-shell reveal">
            <BrainCircuit size={34} />
            <h2>Bring one idea. Leave with a sharper company.</h2>
            <p>Genesis is built for founders who want pressure-tested thinking, not another blank page.</p>
            <a className="btn btn-primary" href="/chat">
              Open Studio
              <UsersRound size={16} />
            </a>
          </div>
        </section>
      </main>
    </div>
  );
}
