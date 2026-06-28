import React from 'react';
import Dashboard from './src/pages/Dashboard';
import LandingPage from './src/pages/LandingPage';

export default function App() {
  const path = window.location.pathname;

  if (path === '/chat') {
    return <Dashboard />;
  }

  return <LandingPage />;
}
