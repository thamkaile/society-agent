import React from 'react';
import { MessageSquare, PanelLeft, Sparkles, Trash2, X } from 'lucide-react';

export default function SessionSidebar({
  sessions,
  currentChatId,
  onSelectSession,
  onDeleteSession,
  streamActive = false,
  isMobileOpen = false,
  onClose,
}) {
  const formatDate = (timestamp) => {
    if (!timestamp) return '';
    try {
      const date = new Date(timestamp * 1000);
      return date.toLocaleString(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (e) {
      return '';
    }
  };

  return (
    <aside
      id="saved-sessions-sidebar"
      className={`sidebar ${isMobileOpen ? 'mobile-open' : ''}`}
      aria-label="Saved Genesis sessions"
    >
      <div className="sidebar-header">
        <div className="genesis-logo-mark sidebar-mark">G</div>
        <div>
          <h2>Genesis</h2>
          <p>Saved sessions</p>
        </div>
        <PanelLeft size={18} className="sidebar-header-icon" aria-hidden="true" />
        <button
          type="button"
          className="sidebar-close"
          onClick={onClose}
          aria-label="Close saved sessions"
        >
          <X size={18} />
        </button>
      </div>
      <div className="sidebar-list">
        {sessions.length === 0 ? (
          <div className="empty-sidebar">
            <Sparkles size={18} />
            <span>No saved blueprints yet</span>
          </div>
        ) : (
          sessions.map((session) => {
            const sessionId = session.id || session.chat_id;
            return (
            <div
              key={sessionId}
              className={`sidebar-item ${currentChatId === sessionId ? 'active' : ''}`}
            >
              <button
                type="button"
                className="sidebar-item-main"
                onClick={() => onSelectSession(sessionId)}
                disabled={streamActive}
              >
                <div className="sidebar-item-inner">
                  <MessageSquare size={16} />
                  <div className="sidebar-item-copy">
                    <div className="session-title" title={session.title || 'Untitled Session'}>
                      {session.title || 'Untitled Session'}
                    </div>
                    <div className="session-date">
                      {formatDate(session.updated_at)}
                    </div>
                  </div>
                </div>
              </button>
              <button
                type="button"
                className="sidebar-delete"
                onClick={() => onDeleteSession?.(session)}
                disabled={streamActive}
                aria-label={`Delete ${session.title || 'Untitled Session'}`}
                title="Delete session"
              >
                <Trash2 size={15} />
              </button>
            </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
