import React from 'react';
import {
  Bot,
  Compass,
  Image,
  Loader2,
  Mic,
  Plus,
  RotateCcw,
  Send,
  Sparkles,
} from 'lucide-react';

const PROMPT_SUGGESTIONS = [
  'Create an investor-ready plan',
  'Pressure-test my MVP',
  'Research go-to-market risks',
];

export default function IdeaInput({
  idea,
  setIdea,
  onGenerate,
  onReset,
  streamActive,
  currentChatId,
  currentPhase,
  connectionState,
  apiLabel,
}) {
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!idea.trim() || streamActive) return;
    onGenerate();
  };

  const canSubmit = Boolean(idea.trim()) && !streamActive;

  return (
    <form className="composer-shell" onSubmit={handleSubmit}>
      <div className="composer-suggestions" aria-label="Prompt suggestions">
        {PROMPT_SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion}
            type="button"
            className="quick-chip"
            onClick={() => setIdea(suggestion)}
            disabled={streamActive}
          >
            <Sparkles size={14} />
            {suggestion}
          </button>
        ))}
      </div>

      <div className="composer-card">
        <button type="button" className="composer-icon-button" aria-label="Attach context" disabled={streamActive}>
          <Plus size={21} />
        </button>

        <label className="sr-only" htmlFor="idea-input">
          {currentChatId ? 'Refine this blueprint' : 'Ask Genesis anything'}
        </label>
        <textarea
          id="idea-input"
          className="composer-textarea"
          placeholder={
            currentChatId
              ? 'Ask Genesis to revisit pricing, compliance, risk, MVP scope...'
              : 'Ask Genesis to build, research, or refine a startup blueprint...'
          }
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          disabled={streamActive}
          rows={1}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (canSubmit) onGenerate();
            }
          }}
        />

        <div className="composer-tools" aria-label="Composer tools">
          <span className={`composer-status ${connectionState}`}>
            <Bot size={15} />
            {connectionState === 'connected'
              ? 'Genesis online'
              : connectionState === 'checking'
                ? 'Checking'
                : 'Offline'}
          </span>
          <button type="button" className="composer-tool" aria-label="Create an image" disabled>
            <Image size={18} />
          </button>
          <button type="button" className="composer-tool" aria-label="Research mode" disabled>
            <Compass size={18} />
          </button>
          <button type="button" className="composer-tool" aria-label="Voice input" disabled>
            <Mic size={18} />
          </button>
          <button
            type="submit"
            className="composer-send"
            disabled={!canSubmit}
            aria-label={streamActive ? 'Genesis is thinking' : 'Send prompt'}
          >
            {streamActive ? <Loader2 size={19} className="animate-spin" /> : <Send size={18} />}
          </button>
        </div>
      </div>

      <div className="composer-meta">
        <button type="button" className="reset-link" onClick={onReset} disabled={streamActive}>
          <RotateCcw size={14} />
          Reset
        </button>
        <span>
          {currentPhase ? (
            <>
              Current phase: <strong>{currentPhase}</strong>
            </>
          ) : (
            <>
              API: <code>{apiLabel}</code>
            </>
          )}
        </span>
      </div>
    </form>
  );
}
