import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { AppProvider, useApp } from './context/AppContext';
import { useTradeNotifications } from './utils/useTradeNotifications';
import LoginScreen from './screens/LoginScreen';
import HomeScreen from './screens/HomeScreen';
import PositionsScreen from './screens/PositionsScreen';
import TradesScreen from './screens/TradesScreen';
import ConfigureScreen from './screens/ConfigureScreen';
import AlertsScreen from './screens/AlertsScreen';
import AccountsScreen from './screens/AccountsScreen';
import { Ionicons } from '@expo/vector-icons';
import SetupScreen from './screens/SetupScreen';

function Placeholder({ label }) {
  return (
    <View style={{ flex:1, backgroundColor:'#0a0a0a', alignItems:'center', justifyContent:'center' }}>
      <Text style={{ color:'#555', fontSize:14 }}>{label} — coming soon</Text>
    </View>
  );
}


const Tab = createBottomTabNavigator();

const TAB_ICONS = {
  Home:      ['home',          'home-outline'],
  Positions: ['bar-chart',     'bar-chart-outline'],
  Trades:    ['list',          'list-outline'],
  Configure: ['settings',      'settings-outline'],
  Alerts:    ['notifications', 'notifications-outline'],
  Accounts:  ['wallet',        'wallet-outline'],
};

function MainTabs() {
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: { backgroundColor:'#0d0d0d', borderTopColor:'#1e1e1e', borderTopWidth:0.5, height:60, paddingBottom:8 },
        tabBarActiveTintColor:   '#378ADD',
        tabBarInactiveTintColor: '#444',
        tabBarLabelStyle: { fontSize:10 },
        tabBarIcon: ({ focused, color, size }) => {
          const [active, inactive] = TAB_ICONS[route.name] || ['ellipse','ellipse-outline'];
          return <Ionicons name={focused ? active : inactive} size={22} color={color} />;
        },
      })}
    >
      <Tab.Screen name="Home"      component={HomeScreen} />
      <Tab.Screen name="Positions" component={PositionsScreen} />
      <Tab.Screen name="Trades"    component={TradesScreen} />
      <Tab.Screen name="Configure" component={ConfigureScreen} />
      <Tab.Screen name="Alerts"    component={AlertsScreen} />
      <Tab.Screen name="Accounts"  component={AccountsScreen} />
    </Tab.Navigator>
  );
}

function RootNavigator() {
  const { isLoggedIn, isLoading, agentUrl, apiBase } = useApp();
  useTradeNotifications(apiBase);
  const [showSetup, setShowSetup] = useState(false);
  useEffect(() => { setShowSetup(!agentUrl || agentUrl.includes('localhost')); }, [agentUrl]);
  if (isLoading) return <View style={{ flex:1, backgroundColor:'#0a0a0a', alignItems:'center', justifyContent:'center' }}><ActivityIndicator color="#378ADD" /></View>;
  if (!isLoggedIn) return <LoginScreen />;
  if (showSetup) return <NavigationContainer><SetupScreen onDone={() => setShowSetup(false)} /></NavigationContainer>;
  return <NavigationContainer><MainTabs /></NavigationContainer>;
}

export default function App() {
  return <GestureHandlerRootView style={{ flex:1 }}><SafeAreaProvider><AppProvider><RootNavigator /></AppProvider></SafeAreaProvider></GestureHandlerRootView>;
}
