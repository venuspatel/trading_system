import React from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert } from 'react-native';
import { sendLocalNotification } from '../utils/notifications';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useApp } from '../context/AppContext';

const C = { bg:'#0a0a0a', surface:'#1a1a1a', border:'#2a2a2a', blue:'#378ADD', green:'#4ade80', red:'#f87171', amber:'#fbbf24', white:'#ffffff', muted:'#555555', dim:'#333333' };

const BROKER_ICONS = {
  alpaca_paper: '◈',
  ibkr:         '⬡',
  etrade:       '◆',
  robinhood:    '◎',
};

export default function AccountsScreen() {
  const { brokers, activeBrokerId, switchBroker, logout, agentUrl, saveAgentUrl } = useApp();

  function handleSwitch(broker) {
    if (!broker.connected) {
      Alert.alert(
        'Not connected',
        `${broker.name} integration is not built yet. It will be available after the paper trading gate passes.`,
        [{ text: 'OK' }]
      );
      return;
    }
    if (broker.id === activeBrokerId) return;
    Alert.alert(
      'Switch broker',
      `Switch active agent to ${broker.name}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Switch', onPress: () => switchBroker(broker.id) },
      ]
    );
  }

  function handleChangeTunnel() {
    Alert.alert(
      'Change tunnel URL',
      'To reconnect to a different tunnel, you need to re-enter the URL.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Change URL', onPress: () => saveAgentUrl('') },
      ]
    );
  }

  function handleLogout() {
    Alert.alert(
      'Lock app',
      'This will lock the app and require your PIN to re-enter.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Lock', style: 'destructive', onPress: logout },
      ]
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView style={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.pageTitle}>Accounts</Text>

        {/* Active broker */}
        <Text style={s.secLabel}>Active broker</Text>
        {brokers.filter(b => b.id === activeBrokerId).map(b => (
          <View key={b.id} style={[s.brokerCard, s.activeCard]}>
            <View style={[s.iconBox, { backgroundColor:'#0a2a1a' }]}>
              <Text style={[s.iconTxt, { color: C.green }]}>{BROKER_ICONS[b.id] || '◉'}</Text>
            </View>
            <View style={s.brokerInfo}>
              <Text style={s.brokerName}>{b.name}</Text>
              <Text style={s.brokerDetail}>{b.detail}</Text>
            </View>
            <View style={s.activeBadge}>
              <Text style={s.activeTxt}>Active</Text>
            </View>
          </View>
        ))}

        {/* Other brokers */}
        <Text style={s.secLabel}>Available brokers</Text>
        {brokers.filter(b => b.id !== activeBrokerId).map(b => (
          <TouchableOpacity key={b.id} style={s.brokerCard} onPress={() => handleSwitch(b)} activeOpacity={0.7}>
            <View style={[s.iconBox, { backgroundColor: b.connected ? '#0a2a1a' : C.dim }]}>
              <Text style={[s.iconTxt, { color: b.connected ? C.green : C.muted }]}>{BROKER_ICONS[b.id] || '◉'}</Text>
            </View>
            <View style={s.brokerInfo}>
              <Text style={s.brokerName}>{b.name}</Text>
              <Text style={s.brokerDetail}>{b.detail}</Text>
            </View>
            <View style={[s.statusPill, { borderColor: b.connected ? C.green : C.dim }]}>
              <Text style={[s.statusTxt, { color: b.connected ? C.green : C.muted }]}>
                {b.connected ? 'Ready' : 'Future'}
              </Text>
            </View>
          </TouchableOpacity>
        ))}

        {/* Connection info */}
        <Text style={s.secLabel}>Connection</Text>
        <View style={s.infoCard}>
          <View style={s.infoRow}>
            <Text style={s.infoLabel}>Tunnel URL</Text>
            <Text style={s.infoVal} numberOfLines={1}>{agentUrl || 'Not set'}</Text>
          </View>
          <View style={s.divider}/>
          <TouchableOpacity style={s.infoRow} onPress={handleChangeTunnel}>
            <Text style={s.infoLabel}>Change tunnel URL</Text>
            <Text style={[s.infoVal, { color: C.blue }]}>→</Text>
          </TouchableOpacity>
        </View>

        {/* App info */}
        <Text style={s.secLabel}>App</Text>
        <View style={s.infoCard}>
          <View style={s.infoRow}>
            <Text style={s.infoLabel}>Version</Text>
            <Text style={s.infoVal}>1.0.0</Text>
          </View>
          <View style={s.divider}/>
          <View style={s.infoRow}>
            <Text style={s.infoLabel}>Agent</Text>
            <Text style={s.infoVal}>V1 Profit Maximizer</Text>
          </View>
          <View style={s.divider}/>
          <View style={s.infoRow}>
            <Text style={s.infoLabel}>Mode</Text>
            <Text style={[s.infoVal, { color: C.amber }]}>Paper trading</Text>
          </View>
        </View>

        {/* Lock button */}
        <TouchableOpacity style={s.lockBtn} onPress={handleLogout} activeOpacity={0.8}>
          <Text style={s.lockTxt}>Lock app</Text>
        </TouchableOpacity>

        <Text style={s.hint}>IBKR and E*Trade integration available after paper trading gate passes</Text>

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:         { flex:1, backgroundColor:C.bg },
  scroll:       { flex:1, paddingHorizontal:16 },
  pageTitle:    { fontSize:22, fontWeight:'500', color:C.white, paddingTop:12, marginBottom:16 },
  secLabel:     { fontSize:10, fontWeight:'500', color:C.muted, letterSpacing:0.6, textTransform:'uppercase', marginBottom:8, marginTop:4 },
  brokerCard:   { flexDirection:'row', alignItems:'center', backgroundColor:C.surface, borderRadius:14, padding:14, marginBottom:8, borderWidth:0.5, borderColor:C.border, gap:12 },
  activeCard:   { borderColor:C.blue, borderWidth:1.5 },
  iconBox:      { width:40, height:40, borderRadius:12, alignItems:'center', justifyContent:'center', flexShrink:0 },
  iconTxt:      { fontSize:20 },
  brokerInfo:   { flex:1 },
  brokerName:   { fontSize:14, fontWeight:'500', color:C.white, marginBottom:2 },
  brokerDetail: { fontSize:11, color:C.muted },
  activeBadge:  { backgroundColor:'#0a2a1a', paddingVertical:4, paddingHorizontal:10, borderRadius:12 },
  activeTxt:    { fontSize:11, fontWeight:'500', color:C.green },
  statusPill:   { paddingVertical:4, paddingHorizontal:10, borderRadius:12, borderWidth:0.5 },
  statusTxt:    { fontSize:11, fontWeight:'500' },
  infoCard:     { backgroundColor:C.surface, borderRadius:14, borderWidth:0.5, borderColor:C.border, marginBottom:16, overflow:'hidden' },
  infoRow:      { flexDirection:'row', justifyContent:'space-between', alignItems:'center', padding:14 },
  infoLabel:    { fontSize:13, color:C.white },
  infoVal:      { fontSize:13, color:C.muted, flex:1, textAlign:'right' },
  divider:      { height:0.5, backgroundColor:C.border },
  lockBtn:      { backgroundColor:C.surface, borderRadius:12, padding:16, alignItems:'center', marginBottom:8, borderWidth:0.5, borderColor:C.red },
  lockTxt:      { color:C.red, fontSize:15, fontWeight:'500' },
  hint:         { fontSize:11, color:C.dim, textAlign:'center', marginBottom:32, paddingHorizontal:16 },
});
