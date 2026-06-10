"use client";
import React, { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';

const RESOLVE_API_BASE = () => {
  // 1) explicit env var (useful when developer sets a LAN-accessible backend)
  if (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_AILEY_API) return process.env.NEXT_PUBLIC_AILEY_API.replace(/\/$/, '');
  // 2) If the landing page was opened from a LAN hostname, use that host with API port 5502
  if (typeof window !== 'undefined') {
    const host = window.location.hostname;
    if (host && host !== '127.0.0.1' && host !== 'localhost') {
      return `http://${host}:5502`;
    }
    // otherwise, when dev, keep localhost
    return 'http://127.0.0.1:5502';
  }
  return 'http://127.0.0.1:5502';
};
const API_BASE = RESOLVE_API_BASE();

function JoinInner(){

  const search = useSearchParams();
  const token = search?.get('token');
  const [status, setStatus] = useState('Bereite Verbindung vor...');

  useEffect(() => {
    if (!token) {
      setStatus('Kein Token angegeben');
      return;
    }
    // Versuche die aktuelle LAN-Frontend-URL zu rekonstruieren
    let frontendUrl = '';
    if (typeof window !== 'undefined') {
      const host = window.location.hostname;
      const port = window.location.port || '3000';
      if (host && host !== '127.0.0.1' && host !== 'localhost') {
        frontendUrl = `http://${host}:${port}`;
      } else {
        frontendUrl = window.location.origin;
      }
    }
    // Baue Backend-Join-URL mit next-Parameter
    const joinUrl = `${API_BASE.replace(/\/$/, '')}/mobile/join/${encodeURIComponent(token)}?next=${encodeURIComponent(frontendUrl)}`;
    setStatus('Weiterleiten...');
    const t = setTimeout(() => {
      window.location.href = joinUrl;
    }, 250);
    return () => clearTimeout(t);
  }, [token]);

  return (
    <div style={{minHeight:'60vh',display:'flex',alignItems:'center',justifyContent:'center',flexDirection:'column',padding:20}}>
      <h2 style={{marginBottom:8}}>Verbindung herstellen</h2>
      <div style={{color:'#666'}}>{status}</div>
      <div style={{marginTop:12,fontSize:12,color:'#999'}}>Wenn die Weiterleitung nicht funktioniert, öffne die URL manuell oder versuche es erneut.</div>
    </div>
  );
}

export default function JoinPage(){
  return (
    <Suspense fallback={<div style={{minHeight:'60vh',display:'flex',alignItems:'center',justifyContent:'center'}}>Laden…</div>}>
      <JoinInner/>
    </Suspense>
  );
}
