import React, { createContext, useContext, useState, useEffect } from 'react';
import * as SecureStore from 'expo-secure-store';
import { registerForPushNotifications, sendLocalNotification } from '../utils/notifications';

const AppContext = createContext({});

const BROKERS = [
  { id: 'alpaca_paper', name: 'Alpaca Paper', detail: 'V1 Profit Maximizer · paper trading', apiUrl: null, connected: true, live: false },
  { id: 'ibkr', name: 'Interactive Brokers', detail: 'Professional · low commissions', apiUrl: null, connected: false, live: true },
  { id: 'etrade', name: 'E*Trade', detail: 'OAuth login · official API', apiUrl: null, connected: false, live: true },
  { id: 'robinhood', name: 'Robinhood', detail: 'Unofficial API · use with care', apiUrl: null, connected: false, live: true },
];

export function AppProvider({ children }) {
  const [isLoggedIn, setIsLoggedIn]         = useState(false);
  const [isLoading, setIsLoading]           = useState(true);
  const [brokers, setBrokers]               = useState(BROKERS);
  const [activeBrokerId, setActiveBrokerId] = useState('alpaca_paper');
  const [agentUrl, setAgentUrl]             = useState('');

  useEffect(() => { loadStoredSettings(); }, []);

  async function loadStoredSettings() {
    try {
      const url = await SecureStore.getItemAsync('agent_url');
      const pin = await SecureStore.getItemAsync('app_pin');
      if (url) setAgentUrl(url);
      // Never auto-login — always require PIN
    } catch (e) {
      console.log('SecureStore load error:', e);
    } finally {
      setIsLoading(false);
    }
  }

  async function saveAgentUrl(url) {
    await SecureStore.setItemAsync('agent_url', url);
    setAgentUrl(url);
  }

  async function registerPushToken() {
    try {
      const granted = await registerForPushNotifications();
      if (granted) {
        console.log('[Notifications] Permission granted — local notifications enabled');
      }
    } catch(e) {
      console.log('[Notifications] Setup failed:', e.message);
    }
  }

  async function login(pin) {
    const stored = await SecureStore.getItemAsync('app_pin');
    if (!stored) {
      await SecureStore.setItemAsync('app_pin', pin);
      setIsLoggedIn(true);
      registerPushToken();
      return true;
    }
    if (stored === pin) {
      setIsLoggedIn(true);
      registerPushToken();
      return true;
    }
    return false;
  }

  async function clearPin() {
    try {
      await SecureStore.deleteItemAsync('app_pin');
    } catch(e) {}
    setIsLoggedIn(false);
  }
  function logout() { setIsLoggedIn(false); }
  function switchBroker(id) { setActiveBrokerId(id); }

  const activeBroker = brokers.find(b => b.id === activeBrokerId);
  const apiBase = agentUrl || 'http://localhost:8000';

  return (
    <AppContext.Provider value={{ isLoggedIn, isLoading, login, logout, clearPin, brokers, activeBroker, activeBrokerId, switchBroker, agentUrl, saveAgentUrl, apiBase }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() { return useContext(AppContext); }

// Force re-setup if URL is localhost (not reachable from phone)
