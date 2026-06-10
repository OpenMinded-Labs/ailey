import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { QRCodeSVG } from 'qrcode.react';

interface LanInfo {
  local_ip: string;
  frontend_port: number;
  hostname?: string;
  interfaces?: Record<string, string>;
}

export default function LanAccessCard() {
  const [qrVisible, setQrVisible] = useState(false);
  const [lanInfo, setLanInfo] = useState<LanInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [copySuccess, setCopySuccess] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Resolve API base (prefer explicit env var in production/dev)
  const RESOLVE_API_BASE = () => {
    if (typeof process !== 'undefined' && process.env && process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE as string;
    if (typeof window !== 'undefined') {
      const host = window.location.hostname;
      if (host && host !== '127.0.0.1' && host !== 'localhost' && host !== 'tauri.localhost') {
        return `http://${host}:5502`;
      }
      return 'http://127.0.0.1:5502';
    }
    return 'http://127.0.0.1:5502';
  };
  const API_BASE = RESOLVE_API_BASE();

  // Helper: wait
  const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

  // Perform health-check with retries, then call discovery
  const fetchLanInfo = async (retries = 3, backoff = 700) => {
    setLoading(true);
    setErrorMessage(null);
    setStatusMessage('Prüfe Backend-Status...');
    try {
      let healthy = false;
      for (let i = 0; i < retries; i++) {
        try {
          const h = await fetch(`${API_BASE || ''}/health`, { cache: 'no-store' });
          if (h.ok) {
            const ct = (h.headers.get('content-type') || '').toLowerCase();
            if (ct.includes('application/json')) {
              const hj = await h.json();
              console.debug('Health response', hj);
              healthy = true;
              break;
            } else {
              // Not JSON — treat as unhealthy for discovery path
              const txt = await h.text().catch(() => '');
              console.debug('Health non-json response', txt.slice(0,200));
            }
          }
        } catch (err) {
          console.debug('Health check failed (attempt)', i + 1, err);
        }
        await wait(backoff * (i + 1));
      }

      if (!healthy) {
        setErrorMessage('Backend nicht erreichbar (Health-Check fehlgeschlagen)');
        setStatusMessage(null);
        setLanInfo(null);
        return;
      }

  setStatusMessage('Backend erreichbar — lade LAN-Info...');
      const r = await fetch(`${API_BASE || ''}/api/network/discovery`, { cache: 'no-store', credentials: 'include' });
      if (!r.ok) {
        const txt = await r.text().catch(() => '');
        throw new Error(`Discovery fehlgeschlagen: ${r.status} ${txt}`);
      }
      const ct = (r.headers.get('content-type') || '').toLowerCase();
      if (!ct.includes('application/json')) {
        const txt = await r.text().catch(() => '');
        throw new Error(`Discovery returned non-json response: ${txt.slice(0,200)}`);
      }
      const j = await r.json().catch((e)=>{ throw new Error('Discovery JSON parse error: '+String(e)); });
      if (j && j.success) {
        setLanInfo(j as LanInfo);
        setStatusMessage('LAN-Info geladen');
      } else {
        setErrorMessage('Discovery returned error');
        console.warn('Discovery payload', j);
      }
    } catch (e) {
      console.error('fetchLanInfo error', e);
      setErrorMessage(String(e));
      setLanInfo(null);
    } finally {
      setLoading(false);
      // clear transient status after a moment
      setTimeout(() => setStatusMessage(null), 2000);
    }
  };

  const [joinUrl, setJoinUrl] = useState<string>('');
  const [joinToken, setJoinToken] = useState<string>('');
  const [manualHost, setManualHost] = useState<string>('');

  const showQr = async () => {
    setQrVisible(true);
    if (!lanInfo) await fetchLanInfo();
    try {
      setStatusMessage('Erzeuge Join-Token...');
      // Bevorzuge immer die LAN-IP aus Discovery, wenn vorhanden
      let frontend_for_token = '';
      if (manualHost && manualHost.trim() !== '') {
        frontend_for_token = manualHost.trim().replace(/\/$/, '');
      } else if (lanInfo && lanInfo.local_ip) {
        const port = (lanInfo as any).frontend_port || (lanInfo as any).api_port || 5502;
        const path = (lanInfo as any).frontend_path || '/app/';
        frontend_for_token = `http://${lanInfo.local_ip}:${port}${path}`.replace(/\/$/, '');
      } else if (frontendOriginForQr) {
        frontend_for_token = frontendOriginForQr;
      } else {
        frontend_for_token = 'http://127.0.0.1:5502/app';
      }
      // Include api_host/api_port so backend builds a join_url that points to the LAN IP
      const payload: any = { frontend_url: frontend_for_token };
      if (lanInfo && lanInfo.local_ip) {
        payload.api_host = lanInfo.local_ip;
        // prefer api_port from discovery, otherwise default to 5502
        // discovery may use key 'frontend_port' for frontend and 'api_port' for API
        // so attempt to read api_port if present
        // @ts-ignore
        payload.api_port = (lanInfo as any).api_port || 5502;
      }
      const g = await fetch(`${API_BASE || ''}/api/mobile/generate_join_token`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), credentials: 'include' });
      if (!g.ok) {
        const txt = await g.text().catch(()=>'');
        throw new Error(`Token creation failed: ${g.status} ${txt}`);
      }
      const gct = (g.headers.get('content-type') || '').toLowerCase();
      if (!gct.includes('application/json')) {
        const txt = await g.text().catch(()=>'');
        throw new Error('Unexpected non-json response from token endpoint: ' + txt.slice(0,200));
      }
      const gj = await g.json().catch((e:any)=>{ throw new Error('Token JSON parse error: '+String(e)); });
      if (gj && gj.success && gj.join_url) {
        setJoinUrl(gj.join_url);
        setJoinToken(gj.token || '');
        setStatusMessage('Join-Token bereit');
      } else {
        console.warn('generate_join_token failed', gj);
        setErrorMessage('Konnte Join-Token nicht erzeugen');
      }
    } catch (e) {
      console.error('join token error', e);
      setErrorMessage(String(e));
    } finally {
      setTimeout(() => setStatusMessage(null), 1600);
    }
  };

  // Auto-generate join token on mount for single-user/dev convenience
  useEffect(() => {
    // Only run in browser
    if (typeof window === 'undefined') return;
    // If we already have a token/URL, skip
    if (joinUrl || joinToken) return;
    // Fire-and-forget: show QR (this will fetch token)
    // eslint-disable-next-line @typescript-eslint/no-floating-promises
    showQr();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Prefer front-end landing page so QR scanners perform a full navigation
  // Resolve a LAN-friendly frontend origin for QR codes and token creation.
  const resolveFrontendOriginForQr = () => {
    if (manualHost && manualHost.trim() !== '') return manualHost.trim().replace(/\/$/, '');
    // Frontend is served by the API backend on /app/ — use the LAN IP with API port
    if (lanInfo && lanInfo.local_ip) {
      const port = (lanInfo as any).frontend_port || (lanInfo as any).api_port || 5502;
      const path = (lanInfo as any).frontend_path || '/app/';
      return `http://${lanInfo.local_ip}:${port}${path}`.replace(/\/$/, '');
    }
    return 'http://127.0.0.1:5502/app';
  };

  const frontendOriginForQr = resolveFrontendOriginForQr();
  const landingUrl = joinToken ? `${frontendOriginForQr.replace(/\/$/, '')}/join?token=${encodeURIComponent(joinToken)}` : '';
  // Prefer direct app URL (works without token), fallback chain for maximum robustness
  const directAppUrl = lanInfo && lanInfo.local_ip ? `http://${lanInfo.local_ip}:${(lanInfo as any).api_port || 5502}${(lanInfo as any).frontend_path || '/app/'}` : '';
  const remoteUrl = directAppUrl || landingUrl || joinUrl || frontendOriginForQr;

  return (
    <Card className="p-4 mb-4">
      <h3 className="text-lg font-bold mb-2">LAN Remote Access</h3>
      <div className="mb-2">
        <label className="text-sm text-zinc-600">Manuelle Host/IP (optional)</label>
        <input
          className="mt-1 block w-full rounded-md border px-2 py-1"
          placeholder="z. B. http://192.168.178.10:3000"
          value={manualHost}
          onChange={(e) => setManualHost(e.target.value)}
        />
        <div className="text-xs text-zinc-500 mt-1">Gib hier die LAN-IP deines Rechners ein, wenn dein Handy die automatische Adresse nicht erreicht.</div>
      </div>
      <Button onClick={showQr} disabled={loading}>
        {qrVisible ? 'QR-Code anzeigen' : 'LAN-Zugang QR-Code'}
      </Button>

      {statusMessage && <div className="mt-2 text-sm text-zinc-600">{statusMessage}</div>}
      {errorMessage && <div className="mt-2 text-sm text-red-500">{errorMessage}</div>}

      {qrVisible && remoteUrl && (
        <div className="mt-4 flex flex-col items-center">
          <a href={remoteUrl} target="_blank" rel="noopener noreferrer" aria-label="Open LAN URL">
            <QRCodeSVG value={remoteUrl} width={180} height={180} />
          </a>
          <div className="mt-2 text-sm text-zinc-600 break-all">{remoteUrl}</div>
          <div className="mt-3 flex gap-2">
            <Button
              onClick={() => {
                try {
                  navigator.clipboard.writeText(remoteUrl);
                  setCopySuccess('Kopiert!');
                  setTimeout(() => setCopySuccess(null), 2000);
                } catch (e) {
                  setCopySuccess('Fehler');
                }
              }}
            >
              Kopieren
            </Button>
            <Button
              onClick={() => {
                if (!remoteUrl) return;
                window.open(remoteUrl, '_blank', 'noopener');
              }}
            >
              Öffnen
            </Button>
          </div>
          {copySuccess && <div className="mt-2 text-sm text-zinc-500">{copySuccess}</div>}
        </div>
      )}

      {loading && <div className="mt-2 text-sm">Lade LAN-Info...</div>}
    </Card>
  );
}
