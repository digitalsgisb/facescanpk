import { useEffect, useRef, useState } from 'react';
import { createUpdateGuard, startAutoUpdates } from './autoUpdate.js';

export default function useAutoUpdates({ activate, blocked }) {
  const state = useRef({ activate, blocked }); state.current = { activate, blocked };
  const [pending, setPending] = useState(false);
  useEffect(() => {
    if (!import.meta.env.PROD) return;
    const guard = createUpdateGuard();
    const updater = startAutoUpdates({ version: __APP_BUILD_ID__, guard, activate: () => state.current.activate(), blocked: () => state.current.blocked, onState: setPending });
    return () => { updater.stop(); guard.stop(); };
  }, []);
  return pending;
}
