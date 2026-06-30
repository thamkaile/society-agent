import React, { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import {
  ArrowRight,
  BrainCircuit,
  Check,
  CircleDollarSign,
  Cloud,
  Code2,
  Database,
  FileText,
  GitBranch,
  Globe2,
  Layers3,
  Network,
  Radio,
  Search,
  ShieldCheck,
  Sparkles,
  UsersRound,
} from 'lucide-react';
import {
  SiFastapi,
  SiGit,
  SiGithub,
  SiRailway,
  SiReact,
  SiSqlalchemy,
  SiSqlite,
  SiTailwindcss,
  SiTypescript,
  SiVercel,
} from 'react-icons/si';
import {
  AnimatedContent,
  Aurora,
  Beams,
  GradientText,
  LogoLoop,
  ScrollRevealText,
  SpotlightCard,
  StarBorder,
  TextType,
  Threads,
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

const systemFlow = [
  'User',
  'React / Next.js Frontend',
  'FastAPI Backend',
  'DynamicStreamingEngine',
  ['Idea Understanding', 'Session Loading'],
  'Root Coordinator',
  'Research Planning',
  'Research Agent',
  'Specialist Selection',
  'Sequential Round-table Debate',
  'Consensus Generation',
  'Blueprint Generation',
  'SQLite Persistence',
  'Streaming to Frontend',
];

function TechMark({ label, children }) {
  return (
    <span className="tech-mark" aria-hidden="true" title={label}>
      {children}
    </span>
  );
}

const architectureTech = [
  { title: 'React', node: <SiReact />, href: 'https://react.dev', tone: 'cyan' },
  { title: 'TypeScript', node: <SiTypescript />, href: 'https://www.typescriptlang.org', tone: 'blue' },
  { title: 'Tailwind CSS', node: <SiTailwindcss />, href: 'https://tailwindcss.com', tone: 'cyan' },
  { title: 'FastAPI', node: <SiFastapi />, href: 'https://fastapi.tiangolo.com', tone: 'green' },
  { title: 'CAMEL-AI', node: <TechMark label="CAMEL-AI">CA</TechMark>, href: 'https://www.camel-ai.org', tone: 'amber' },
  { title: 'OpenRouter', node: <TechMark label="OpenRouter">OR</TechMark>, href: 'https://openrouter.ai', tone: 'violet' },
  { title: 'Qwen', node: <TechMark label="Qwen">QW</TechMark>, href: 'https://qwenlm.github.io', tone: 'blue' },
  { title: 'SQLite', node: <SiSqlite />, href: 'https://www.sqlite.org', tone: 'blue' },
  { title: 'SQLAlchemy', node: <SiSqlalchemy />, href: 'https://www.sqlalchemy.org', tone: 'red' },
  { title: 'Tavily Search API', node: <Search />, href: 'https://tavily.com', tone: 'green' },
  { title: 'Server-Sent Events (SSE)', node: <Radio />, tone: 'rose' },
  { title: 'REST API', node: <Globe2 />, tone: 'violet' },
  { title: 'Git', node: <SiGit />, href: 'https://git-scm.com', tone: 'red' },
  { title: 'GitHub', node: <SiGithub />, href: 'https://github.com', tone: 'ink' },
  { title: 'Railway', node: <SiRailway />, href: 'https://railway.app', tone: 'violet' },
  { title: 'Vercel', node: <SiVercel />, href: 'https://vercel.com', tone: 'ink' },
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

function FlowNode({ item, index }) {
  const isBranch = Array.isArray(item);
  return (
    <div className={isBranch ? 'flow-row branch-row' : 'flow-row'}>
      {isBranch ? (
        <div className="flow-branch" aria-label="Parallel DynamicStreamingEngine work">
          {item.map((branch) => (
            <SpotlightCard as="article" className="flow-node branch-node" key={branch}>
              <span>{branch}</span>
            </SpotlightCard>
          ))}
        </div>
      ) : (
        <SpotlightCard as="article" className={`flow-node ${index === 0 ? 'flow-node-start' : ''}`}>
          <small>{String(index + 1).padStart(2, '0')}</small>
          <span>{item}</span>
        </SpotlightCard>
      )}
      {index < systemFlow.length - 1 && <span className="flow-connector" aria-hidden="true" />}
    </div>
  );
}

function TechIconCard({ tech }) {
  return (
    <SpotlightCard as="article" className={`tech-card ${tech.tone}`}>
      <div className="tech-icon" aria-hidden="true">
        {tech.node}
      </div>
      <span>{tech.title}</span>
    </SpotlightCard>
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

      gsap.utils.toArray('.reveal, .flow-row, .tech-card').forEach((element) => {
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
      <div className="antigravity-overlay">
        <Threads
          color={[0.26, 0.52, 0.96]}
          amplitude={0.8}
          distance={0.4}
          enableMouseInteraction
          lineCount={20}
        />
      </div>

      <header className="landing-nav">
        <div className="landing-nav-inner">
          <GenesisLogo />
          <nav className="landing-nav-links" aria-label="Primary navigation">
            <a href="#proof">Proof</a>
            <a href="#process">Process</a>
            <a href="#flow">Flow</a>
            <a href="#stack">Stack</a>
            <a href="#deliverables">Deliverables</a>
            <a className="btn btn-primary btn-small cursor-target" href="/chat">
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
              <TextType
                as="p"
                className="hero-typed hero-reveal"
                text={[
                  'Researches market signals.',
                  'Debates tradeoffs with specialist agents.',
                  'Streams the blueprint as it forms.',
                  'Saves session memory for the next decision.',
                ]}
                typingSpeed={42}
                deletingSpeed={22}
                pauseDuration={1450}
                startOnVisible
                textColors={['#2357b5', '#0b6d40', '#7a4fd8', '#9a6b00']}
              />
              <div className="hero-actions hero-reveal">
                <a className="btn btn-primary cursor-target" href="/chat">
                  Open Genesis
                  <ArrowRight size={16} />
                </a>
                <a className="btn btn-secondary cursor-target" href="#process">
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
              <ScrollRevealText as="h2">From instinct to evidence to a decision you can act on.</ScrollRevealText>
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

        <section id="flow" className="landing-section flow-section">
          <div className="section-shell">
            <div className="section-heading reveal">
              <p className="eyebrow-line">System Flow</p>
              <h2>The full path from prompt to streamed blueprint.</h2>
              <p>
                The experience stays legible from the first user idea through backend orchestration,
                specialist debate, persistence, and live frontend streaming.
              </p>
            </div>
            <div className="system-flow" aria-label="Genesis system architecture flow">
              {systemFlow.map((item, index) => (
                <FlowNode item={item} index={index} key={Array.isArray(item) ? item.join('-') : item} />
              ))}
            </div>
          </div>
        </section>

        <section id="stack" className="landing-section tech-section">
          <div className="section-shell">
            <div className="section-heading reveal">
              <p className="eyebrow-line">Architecture Technologies</p>
              <h2>The stack behind the boardroom.</h2>
              <p>
                Frontend, orchestration, model routing, persistence, research, streaming, and deployment
                tools share the same blueprint pipeline.
              </p>
            </div>
            <StarBorder className="tech-loop-frame reveal">
              <LogoLoop
                logos={architectureTech}
                speed={92}
                logoHeight={34}
                gap={30}
                fadeOutColor="rgba(255, 253, 249, 0.96)"
                ariaLabel="Genesis architecture technology stack"
              />
            </StarBorder>
            <div className="tech-grid reveal">
              {architectureTech.map((tech) => (
                <TechIconCard tech={tech} key={tech.title} />
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
            <a className="btn btn-primary cursor-target" href="/chat">
              Open Studio
              <UsersRound size={16} />
            </a>
          </div>
        </section>
      </main>
    </div>
  );
}
