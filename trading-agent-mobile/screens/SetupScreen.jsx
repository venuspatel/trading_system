import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', white:'#ffffff', muted:'#555555', green:'#4ade80', red:'#f87171' };

const TUNNEL = 'https://definition-impacts-slots-discounts.trycloudflare.com';

export default function SetupScreen({ onDone }) {
  const { saveAgentUrl } = useApp();
  const [url, setUrl]     = useState(TUNNEL);
  const [testing, setTest] = useState(false);
  const [status, setStatus] = useState('');

  async function testAndSave() {
    const clean = (url || TUNNEL).trim().replace(/\/$/, '');
    setTest(true);
    setStatus('Testing connection...');
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 10000);
      const res = await fetch(`${clean}/api/state`, {
        method: 'GET',
        headers: { 'Accept': 'application/json' },
        signal: controller.signal,
      });
      clearTimeout(timer);
      if (res.ok) {
        setStatus('Connected!');
        await saveAgentUrl(clean);
        setTimeout(onDone, 800);
      } else {
        setStatus(`Error: server returned ${res.status}`);
      }
    } catch (e) {
      setStatus(`Failed: ${e.message}`);
    } finally {
      setTest(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.container}>
        <View style={s.logoBox}><Text style={s.logoIcon}>↗</Text></View>
        <Text style={s.title}>Connect to agent</Text>
        <Text style={s.sub}>Tunnel URL is pre-filled — just tap Connect</Text>

        <TextInput
          style={s.input}
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />

        {status !== '' && (
          <Text style={[s.statusTxt, { color: status.includes('Connected') ? C.green : status.includes('Testing') ? C.muted : C.red }]}>
            {status}
          </Text>
        )}

        <TouchableOpacity style={s.btn} onPress={testAndSave} disabled={testing} activeOpacity={0.8}>
          {testing
            ? <ActivityIndicator color={C.white} />
            : <Text style={s.btnTxt}>Connect to agent</Text>
          }
        </TouchableOpacity>

        <TouchableOpacity style={s.skipBtn} onPress={() => { saveAgentUrl(url.trim()); onDone(); }}>
          <Text style={s.skipTxt}>Skip test and connect anyway</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:      { flex:1, backgroundColor:C.bg },
  container: { flex:1, padding:24, justifyContent:'center' },
  logoBox:   { width:56, height:56, borderRadius:16, backgroundColor:C.surface, borderWidth:0.5, borderColor:C.border, alignItems:'center', justifyContent:'center', marginBottom:16, alignSelf:'center' },
  logoIcon:  { fontSize:24, color:C.blue },
  title:     { fontSize:22, fontWeight:'500', color:C.white, textAlign:'center', marginBottom:6 },
  sub:       { fontSize:13, color:C.muted, textAlign:'center', marginBottom:24 },
  input:     { backgroundColor:C.surface, borderRadius:12, borderWidth:0.5, borderColor:C.border, padding:14, color:C.white, fontSize:12, marginBottom:16 },
  statusTxt: { fontSize:12, textAlign:'center', marginBottom:12 },
  btn:       { backgroundColor:C.blue, borderRadius:12, padding:16, alignItems:'center', marginBottom:12 },
  btnTxt:    { color:C.white, fontSize:15, fontWeight:'500' },
  skipBtn:   { padding:12, alignItems:'center' },
  skipTxt:   { color:C.muted, fontSize:13 },
});
