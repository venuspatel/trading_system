import * as SecureStore from 'expo-secure-store';
SecureStore.deleteItemAsync('agent_url').then(() => console.log('cleared'));
