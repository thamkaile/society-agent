import React from 'react';
import {
  Bot,
  Loader2,
  RotateCcw,
  Send,
} from 'lucide-react';

export default function IdeaInput({
  idea,
  setIdea,
  onGenerate,
  onReset,
  streamActive,
  currentChatId,
  currentPhase,
}) {
  const handleSubmit = (e) => {
    e.preventDefault();
    if (!idea.trim() || streamActive) return;
    onGenerate();
  };

  const isNewChat = !currentChatId;
  const canSubmit = Boolean(idea.trim()) && !streamActive;

  return (
    <form className="composer-shell" onSubmit={handleSubmit}>
      <div className="composer-card">
        <label className="sr-only" htmlFor="idea-input">
          {currentChatId ? 'Refine this blueprint' : 'Describe your startup idea'}
        </label>
        <textarea
          id="idea-input"
          className="composer-textarea"
          placeholder={
            currentChatId
              ? 'Ask Genesis to revisit pricing, compliance, risk, MVP scope...'
              : 'Describe your idea in one sentence.'
          }
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          disabled={streamActive}
          rows={2}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              if (canSubmit) onGenerate();
            }
          }}
        />

        <div className="composer-tools" aria-label="Composer tools">
          <span className="composer-status">
            <Bot size={15} />
            {currentChatId ? 'Refine' : 'New simulation'}
          </span>
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
          Clear
        </button>
        <span>
          {streamActive && currentPhase ? (
            <>
              Current phase: <strong>{currentPhase}</strong>
            </>
          ) : isNewChat ? 'Keep the first message short.' : 'Short follow-ups work best.'}
        </span>
      </div>
    </form>
  );
}
