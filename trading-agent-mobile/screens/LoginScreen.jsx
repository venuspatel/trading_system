import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Alert, Vibration
} from 'react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as SecureStore from 'expo-secure-store';
import { useApp } from '../context/AppContext';

const C = {
  bg:       '#0a0a0a',
  surface:  '#1a1a1a',
  border:   '#2a2a2a',
  blue:     '#378ADD',
  white:    '#ffffff',
  muted:    '#555555',
  danger:   '#ef4444',
};

export default function LoginScreen() {
  const { login, clearPin } = useApp();
  const [pin, setPin]             = useState('');
  const [shake, setShake]         = useState(false);
  const [hasBiometric, setBiometric] = useState(false);
  const [isFirstLaunch, setFirstLaunch] = useState(false);

  const PIN_LENGTH = 4;

  useEffect(() => {
    checkBiometric();
    checkFirstLaunch();
  }, []);

  async function checkBiometric() {
    const compatible = await LocalAuthentication.hasHardwareAsync();
    const enrolled   = await LocalAuthentication.isEnrolledAsync();
    setBiometric(compatible && enrolled);
  }

  async function checkFirstLaunch() {
    try {
      const stored = await SecureStore.getItemAsync('app_pin');
      setFirstLaunch(!stored);
    } catch(e) {
      setFirstLaunch(true);
    }
  }

  async function handleBiometric() {
    const result = await LocalAuthentication.authenticateAsync({
      promptMessage: 'Unlock TradeAgent',
      fallbackLabel: 'Use PIN',
    });
    if (result.success) login('__biometric__');
  }

  async function pressKey(key) {
    if (pin.length >= PIN_LENGTH) return;
    const newPin = pin + key;
    setPin(newPin);
    if (newPin.length === PIN_LENGTH) {
      await submitPin(newPin);
    }
  }

  async function submitPin(p) {
    const success = await login(p);
    if (!success) {
      Vibration.vibrate(400);
      setShake(true);
      setTimeout(() => { setShake(false); setPin(''); }, 600);
    }
  }

  function deleteKey() {
    setPin(prev => prev.slice(0, -1));
  }

  const KEYS = ['1','2','3','4','5','6','7','8','9','','0','del'];

  return (
    <View style={s.container}>
      <View style={s.logoWrap}>
        <View style={s.logoBox}>
          <Text style={s.logoIcon}>↗</Text>
        </View>
        <Text style={s.appName}>TradeAgent</Text>
        <Text style={s.appSub}>
          {isFirstLaunch ? 'Set a PIN to secure your account' : 'Enter PIN to continue'}
        </Text>
      </View>

      {/* PIN dots */}
      <View style={[s.dotsRow, shake && s.shake]}>
        {Array.from({ length: PIN_LENGTH }).map((_, i) => (
          <View key={i} style={[s.dot, i < pin.length && s.dotFilled]} />
        ))}
      </View>

      {/* Numpad */}
      <View style={s.numpad}>
        {KEYS.map((k, i) => {
          if (k === '') return <View key={i} style={s.keyEmpty} />;
          if (k === 'del') return (
            <TouchableOpacity key={i} style={s.key} onPress={deleteKey} activeOpacity={0.7}>
              <Text style={s.keyText}>⌫</Text>
            </TouchableOpacity>
          );
          return (
            <TouchableOpacity key={i} style={s.key} onPress={() => pressKey(k)} activeOpacity={0.7}>
              <Text style={s.keyText}>{k}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Biometric */}
      <TouchableOpacity onPress={async () => { await clearPin(); setFirstLaunch(true); setPin(''); }} style={{ padding:16, marginTop:8 }}>
        <Text style={{ fontSize:11, color:'#333', textAlign:'center' }}>Reset PIN</Text>
      </TouchableOpacity>

      {hasBiometric && (
        <TouchableOpacity style={s.bioBtn} onPress={handleBiometric} activeOpacity={0.7}>
          <Text style={s.bioText}>Use Face ID / Touch ID</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  container:  { flex:1, backgroundColor:C.bg, alignItems:'center', justifyContent:'center', paddingHorizontal:32 },
  logoWrap:   { alignItems:'center', marginBottom:40 },
  logoBox:    { width:64, height:64, borderRadius:18, backgroundColor:C.surface, borderWidth:0.5, borderColor:C.border, alignItems:'center', justifyContent:'center', marginBottom:14 },
  logoIcon:   { fontSize:28, color:C.blue },
  appName:    { fontSize:22, fontWeight:'500', color:C.white, marginBottom:6 },
  appSub:     { fontSize:13, color:C.muted },
  dotsRow:    { flexDirection:'row', gap:16, marginBottom:36 },
  dot:        { width:13, height:13, borderRadius:7, backgroundColor:C.surface, borderWidth:0.5, borderColor:C.border },
  dotFilled:  { backgroundColor:C.blue, borderColor:C.blue },
  shake:      { transform:[{ translateX: 8 }] },
  numpad:     { width:'100%', flexDirection:'row', flexWrap:'wrap', gap:12, marginBottom:28 },
  key:        { width:'30%', height:56, backgroundColor:C.surface, borderRadius:14, borderWidth:0.5, borderColor:C.border, alignItems:'center', justifyContent:'center' },
  keyEmpty:   { width:'30%', height:56 },
  keyText:    { fontSize:20, fontWeight:'500', color:C.white },
  bioBtn:     { paddingVertical:12, paddingHorizontal:24, backgroundColor:C.surface, borderRadius:24, borderWidth:0.5, borderColor:C.border },
  bioText:    { fontSize:13, color:C.muted },
});
