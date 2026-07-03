import React, { useEffect, useState } from 'react';
import Dashboard from './src/pages/Dashboard';
import LandingPage from './src/pages/LandingPage';
import BlueprintPage from './src/pages/BlueprintPage';

function getInitialTheme() {
  try {
    const savedTheme = window.localStorage.getItem('genesis-theme');
    if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
  } catch (error) {
    // Storage may be unavailable in private contexts.
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export default function App() {
  const [theme, setTheme] = useState(getInitialTheme);
  const path = window.location.pathname;
  const blueprintMatch = path.match(/^\/chat\/([^/]+)\/blueprint\/?$/);
  const chatMatch = path.match(/^\/chat\/([^/]+)\/?$/);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    try {
      window.localStorage.setItem('genesis-theme', theme);
    } catch (error) {
      // Keep the in-memory theme even if persistence is unavailable.
    }
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme((currentTheme) => (currentTheme === 'dark' ? 'light' : 'dark'));
  };

  if (blueprintMatch) {
    return (
      <BlueprintPage
        chatId={decodeURIComponent(blueprintMatch[1])}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />
    );
  }

  if (path === '/chat') {
    return <Dashboard theme={theme} onToggleTheme={handleToggleTheme} />;
  }

  if (chatMatch) {
    return (
      <Dashboard
        initialChatId={decodeURIComponent(chatMatch[1])}
        theme={theme}
        onToggleTheme={handleToggleTheme}
      />
    );
  }

  return <LandingPage theme={theme} onToggleTheme={handleToggleTheme} />;
}
