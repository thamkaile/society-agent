import React from 'react';
import Dashboard from './src/pages/Dashboard';
import LandingPage from './src/pages/LandingPage';
import BlueprintPage from './src/pages/BlueprintPage';

export default function App() {
  const path = window.location.pathname;
  const blueprintMatch = path.match(/^\/chat\/([^/]+)\/blueprint\/?$/);
  const chatMatch = path.match(/^\/chat\/([^/]+)\/?$/);

  if (blueprintMatch) {
    return <BlueprintPage chatId={decodeURIComponent(blueprintMatch[1])} />;
  }

  if (path === '/chat') {
    return <Dashboard />;
  }

  if (chatMatch) {
    return <Dashboard initialChatId={decodeURIComponent(chatMatch[1])} />;
  }

  return <LandingPage />;
}
