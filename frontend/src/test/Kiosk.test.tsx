import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { LanguageProvider } from '@/i18n/LanguageContext';
import { translations } from '@/i18n/translations';
import { Kiosk } from '@/pages/Kiosk/Kiosk';
import { camerasApi } from '@/api/cameras';
import { eventsApi } from '@/api/events';
import { cvServiceApi } from '@/api/cvService';

// English strings are asserted against directly since LanguageProvider defaults
// to Spanish via localStorage; we force English for readable assertions.
const t = translations.en;

vi.mock('@/api/cameras', () => ({
  camerasApi: {
    getCameras: vi.fn().mockResolvedValue([{ id: 'cam-1', name: 'Camera 1' }]),
  },
}));

vi.mock('@/api/events', () => ({
  eventsApi: {
    getEvents: vi.fn().mockResolvedValue({ events: [] }),
  },
}));

vi.mock('@/api/cvService', () => ({
  cvServiceApi: {
    getStreamUrl: vi.fn((cameraId: string) => `/cv/stream/${cameraId}`),
    getWebSocketUrl: vi.fn(() => 'ws://test/cv/ws/camera/cam-1'),
  },
}));

// ---------------------------------------------------------------------------
// Mock WebSocket — captures instances so tests can drive onopen/onmessage
// manually, simulating the CV service pushing per-frame recognition events.
// ---------------------------------------------------------------------------

class MockWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.CONNECTING;
  onopen: ((ev?: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev?: unknown) => void) | null = null;
  onclose: ((ev?: unknown) => void) | null = null;
  binaryType = '';
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send() {
    // capture intervals aren't exercised — canvas.getContext is unavailable
    // in jsdom by default, so the capture loop no-ops before calling send.
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

function recognitionMessage(overrides: Partial<{
  member_id: string | null;
  member_name: string | null;
  confidence: number;
  access_granted: boolean;
  denial_reason: string | null;
  face_bbox: number[] | null;
  membership_end_date: string | null;
  days_remaining: number | null;
}> = {}) {
  return JSON.stringify({
    type: 'recognition',
    member_id: 'member-1',
    member_name: 'Jane Doe',
    confidence: 0.95,
    access_granted: true,
    denial_reason: null,
    face_bbox: null,
    membership_end_date: '2026-12-31',
    // Comfortably outside the expiring-soon window so the default granted
    // message lands on the plain welcome splash, not the amber warning.
    days_remaining: 40,
    ...overrides,
  });
}

function renderKiosk(cameraId = 'cam-1', extraParams = '') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <MemoryRouter initialEntries={[`/kiosk?cameraId=${cameraId}${extraParams}`]}>
          <Kiosk />
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>
  );
}

function openSettings() {
  const settingsButton = screen.getByTestId('SettingsIcon').closest('button')!;
  fireEvent.click(settingsButton);
}

/**
 * The kiosk claims the local camera on its own, so a test only has to wait
 * for the socket it opened and then drive it. No Settings trip required.
 */
async function awaitAutoStartedCamera() {
  await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(0));
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  act(() => {
    ws.readyState = MockWebSocket.OPEN;
    ws.onopen?.();
  });
  return ws;
}

function sendMessage(ws: MockWebSocket, payload: string) {
  act(() => {
    ws.onmessage?.({ data: payload });
  });
}

async function wait(ms: number) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms));
  });
}

beforeEach(() => {
  // The kiosk persists its camera choice, so state must not leak between
  // tests — otherwise one test's remembered camera silently drives the next.
  localStorage.clear();
  localStorage.setItem('lang', 'en');
  MockWebSocket.instances = [];
  (global as any).WebSocket = MockWebSocket;

  Object.defineProperty(global.navigator, 'mediaDevices', {
    value: {
      getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }),
    },
    writable: true,
    configurable: true,
  });

  window.HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  window.HTMLMediaElement.prototype.pause = vi.fn();

  vi.mocked(camerasApi.getCameras).mockResolvedValue([{ id: 'cam-1', name: 'Camera 1' } as any]);
  vi.mocked(eventsApi.getEvents).mockResolvedValue({ events: [] } as any);
  vi.mocked(cvServiceApi.getWebSocketUrl).mockReturnValue('ws://test/cv/ws/camera/cam-1');
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('Kiosk unattended startup', () => {
  it('claims the local camera on load without a trip through Settings', async () => {
    renderKiosk();

    // No Settings panel is opened and no toggle is clicked — an unattended
    // kiosk has nobody to do that for it.
    await waitFor(() => expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled());
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    expect(cvServiceApi.getWebSocketUrl).toHaveBeenCalledWith('cam-1');
  });

  it('adopts the first configured camera when the URL names none', async () => {
    vi.mocked(camerasApi.getCameras).mockResolvedValue([
      { id: 'entrance-cam', name: 'Entrance' },
      { id: 'back-cam', name: 'Back Door' },
    ] as any);

    renderKiosk('');

    await waitFor(() =>
      expect(cvServiceApi.getWebSocketUrl).toHaveBeenCalledWith('entrance-cam')
    );
  });

  it('restores the last camera used on this kiosk across a reload', async () => {
    localStorage.setItem('kiosk.cameraId', 'back-cam');
    vi.mocked(camerasApi.getCameras).mockResolvedValue([
      { id: 'entrance-cam', name: 'Entrance' },
      { id: 'back-cam', name: 'Back Door' },
    ] as any);

    renderKiosk('');

    // Must prefer the remembered camera over merely the first in the list.
    await waitFor(() =>
      expect(cvServiceApi.getWebSocketUrl).toHaveBeenCalledWith('back-cam')
    );
    expect(cvServiceApi.getWebSocketUrl).not.toHaveBeenCalledWith('entrance-cam');
  });

  it('falls back to the first configured camera when the remembered camera was deleted', async () => {
    localStorage.setItem('kiosk.cameraId', 'deleted-cam');
    vi.mocked(camerasApi.getCameras).mockResolvedValue([
      { id: 'entrance-cam', name: 'Entrance' },
      { id: 'back-cam', name: 'Back Door' },
    ] as any);

    renderKiosk('');

    await waitFor(() =>
      expect(cvServiceApi.getWebSocketUrl).toHaveBeenCalledWith('entrance-cam')
    );
    expect(localStorage.getItem('kiosk.cameraId')).toBe('entrance-cam');
  });
});

describe('Kiosk result splash', () => {
  it('keeps the camera hero and idle status visible before recognition', async () => {
    renderKiosk();
    await awaitAutoStartedCamera();

    expect(screen.getByTestId('camera-hero')).toBeVisible();
    expect(screen.getByTestId('status-dock')).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent(t.kiosk.readyTitle);
    expect(screen.getByRole('status')).toHaveTextContent(t.kiosk.faceCamera);
  });

  it('shows a full-screen welcome splash naming the member on a grant', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(ws, recognitionMessage({ access_granted: true, days_remaining: 40 }));

    const splash = await screen.findByTestId('result-splash', undefined, { timeout: 2000 });
    expect(splash).toHaveAttribute('data-state', 'granted');
    expect(splash).toHaveTextContent(t.kiosk.welcomeBack);
    expect(splash).toHaveTextContent('Jane Doe');
    // No expiring-soon warning when the membership has plenty of runway.
    expect(splash).not.toHaveTextContent(t.kiosk.membershipExpiringSoon);
    expect(screen.queryByTestId('status-dock')).not.toBeInTheDocument();
  });

  it('warns with the remaining-day count when the membership is about to lapse', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(ws, recognitionMessage({ access_granted: true, days_remaining: 3 }));

    const splash = await screen.findByTestId('result-splash', undefined, { timeout: 2000 });
    // Access is still GRANTED — this is a warning, not a refusal.
    expect(splash).toHaveAttribute('data-state', 'granted_expiring');
    expect(splash).toHaveTextContent(t.kiosk.welcomeBack);
    expect(splash).toHaveTextContent(`${t.kiosk.membershipExpiringSoon}: 3 ${t.kiosk.daysUnit}`);
  });

  it('uses the singular day unit on the final day', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(ws, recognitionMessage({ access_granted: true, days_remaining: 1 }));

    const splash = await screen.findByTestId('result-splash', undefined, { timeout: 2000 });
    expect(splash).toHaveTextContent(`${t.kiosk.membershipExpiringSoon}: 1 ${t.kiosk.dayUnit}`);
  });

  it('warns on the last valid day, when zero days remain', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(ws, recognitionMessage({ access_granted: true, days_remaining: 0 }));

    const splash = await screen.findByTestId('result-splash', undefined, { timeout: 2000 });
    expect(splash).toHaveAttribute('data-state', 'granted_expiring');
    expect(splash).toHaveTextContent(t.kiosk.membershipExpiringSoon);
  });

  it('never names an unrecognized person on the splash', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    // member_not_found can carry a stale cached real name from the CV
    // service's template cache — the splash must not disclose it.
    sendMessage(
      ws,
      recognitionMessage({
        member_id: 'stale-member',
        member_name: 'Real Cached Name',
        access_granted: false,
        denial_reason: 'member_not_found',
        days_remaining: null,
      })
    );

    const splash = await screen.findByTestId('result-splash', undefined, { timeout: 2000 });
    expect(splash).toHaveAttribute('data-state', 'unknown_denied');
    expect(splash).toHaveTextContent(t.kiosk.unknownTitle);
    expect(splash).not.toHaveTextContent('Real Cached Name');
  });

  it('names the member and the reason for a genuine membership denial', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(
      ws,
      recognitionMessage({
        member_id: 'member-2',
        member_name: 'Known Member',
        access_granted: false,
        denial_reason: 'expired_membership',
        days_remaining: null,
      })
    );

    const splash = await screen.findByTestId('result-splash', undefined, { timeout: 2000 });
    expect(splash).toHaveAttribute('data-state', 'membership_denied');
    expect(splash).toHaveTextContent('Known Member');
    expect(splash).toHaveTextContent(t.kiosk.reasonExpiredMembership);
  });

  it.each([
    ['granted', { access_granted: true, days_remaining: 40 }],
    ['granted_expiring', { access_granted: true, days_remaining: 0 }],
    ['membership_denied', { access_granted: false, denial_reason: 'expired_membership', days_remaining: null }],
    ['unknown_denied', { access_granted: false, denial_reason: 'unknown_face', days_remaining: null }],
  ])('returns the %s terminal state to idle within three seconds', async (state, overrides) => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();
    vi.useFakeTimers();

    sendMessage(ws, recognitionMessage(overrides));
    await act(async () => vi.advanceTimersByTimeAsync(500));
    expect(screen.getByTestId('result-splash')).toHaveAttribute('data-state', state);

    // Continuous duplicate frames must not move the fixed reset deadline.
    sendMessage(ws, recognitionMessage(overrides));
    await act(async () => vi.advanceTimersByTimeAsync(3000));

    expect(screen.queryByTestId('result-splash')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(t.kiosk.readyTitle);
    vi.useRealTimers();
  });
});

describe('Kiosk recognition state machine (USB mode)', () => {
  it('loads UUID camera streams through the same-origin CV proxy path', async () => {
    const cameraId = 'ad0bcb04-14eb-4f78-80fa-59374b768b8c';
    vi.mocked(camerasApi.getCameras).mockResolvedValue([{ id: cameraId, name: 'Entrance' }] as any);

    // ?mode=remote opts out of the local-camera default and back into the
    // server-side RTSP stream.
    renderKiosk(cameraId, '&mode=remote');

    const stream = await screen.findByAltText(t.kiosk.liveCameraAlt);
    expect(stream).toHaveAttribute('src', `/cv/stream/${cameraId}`);
    expect(cvServiceApi.getStreamUrl).toHaveBeenCalledWith(cameraId);
  });

  it('shows one dominant camera error and reports the system unavailable', async () => {
    renderKiosk('cam-1', '&mode=remote');

    const stream = await screen.findByAltText(t.kiosk.liveCameraAlt);
    fireEvent.error(stream);

    expect(screen.getAllByText(t.kiosk.cameraReconnecting)).toHaveLength(1);
    expect(screen.getByRole('button', { name: t.kiosk.retry })).toBeInTheDocument();
    expect(screen.getByTestId('system-status')).toHaveTextContent(t.kiosk.systemUnavailable);
    expect(screen.queryByTestId('status-dock')).not.toBeInTheDocument();
  });

  it('reveals the granted result even when the same person keeps sending frames faster than the verifying beat', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    // First frame for this person: enters the 500ms "verifying" beat.
    sendMessage(ws, recognitionMessage({ member_id: 'member-1', access_granted: true }));
    await screen.findByText(t.kiosk.verifyingTitle);

    // A second frame for the SAME person/outcome arrives ~200ms later — well
    // before the 500ms verifying timer would fire. This mirrors the CV
    // service's real per-frame push cadence while someone stands in frame.
    await wait(200);
    sendMessage(ws, recognitionMessage({ member_id: 'member-1', access_granted: true }));

    // The granted result MUST still reveal itself — the repeated frame must
    // not cancel the reveal forever.
    await waitFor(
      () => expect(screen.getByText(t.kiosk.welcomeBack)).toBeInTheDocument(),
      { timeout: 2000 }
    );
    expect(screen.getByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText(/Membership valid until/)).toBeInTheDocument();
  });

  it('resets to idle when the USB camera is stopped and restarted (no permanent freeze)', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(ws, recognitionMessage({ member_id: 'member-1', access_granted: true }));
    await waitFor(() => expect(screen.getByText(t.kiosk.welcomeBack)).toBeInTheDocument(), {
      timeout: 2000,
    });

    // Staff toggles USB mode off — this stops the camera/websocket.
    openSettings();
    const usbToggleOff = await screen.findByText(t.kiosk.usbCameraMode);
    fireEvent.click(usbToggleOff);

    // The stale "granted" overlay must clear — the kiosk must return to idle,
    // not freeze showing the previous person's result forever.
    await waitFor(() => {
      expect(screen.queryByText(t.kiosk.welcomeBack)).not.toBeInTheDocument();
      expect(screen.getByText(t.kiosk.faceCamera)).toBeInTheDocument();
    });
  });

  it('shows a manual retry control (not a false "automatic" promise) when the USB connection errors', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    act(() => {
      ws.onerror?.();
    });

    const retryButton = await screen.findByRole('button', { name: t.kiosk.retry });
    expect(retryButton).toBeInTheDocument();
    expect(screen.queryByText(/automatically/i)).not.toBeInTheDocument();

    const priorInstanceCount = MockWebSocket.instances.length;
    fireEvent.click(retryButton);

    await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(priorInstanceCount));
  });

  it('keeps the retry overlay visible and suppresses the scan guide after the real onerror-then-onclose sequence', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    // Real browsers fire onclose immediately after onerror for a failed/dropped
    // connection. The previous test only simulated onerror alone, which hid this
    // bug: connectionStatus flips from 'error' to 'disconnected' the instant
    // onclose runs, and the retry overlay was gated on 'error' only.
    act(() => {
      ws.onerror?.();
      ws.onclose?.();
    });

    const retryButton = await screen.findByRole('button', { name: t.kiosk.retry });
    expect(retryButton).toBeInTheDocument();

    // The decorative scan-guide ring must not reappear over a dead feed —
    // it would make the kiosk look like it's actively scanning.
    expect(screen.queryByTestId('scan-guide')).not.toBeInTheDocument();
  });

  it('guards against a second startUsbCamera invocation while a previous one is still pending getUserMedia', async () => {
    vi.mocked(camerasApi.getCameras).mockResolvedValue([
      { id: 'cam-1', name: 'Camera 1' },
      { id: 'cam-2', name: 'Camera 2' },
    ] as any);

    let resolveFirstStream: (v: any) => void = () => {};
    const firstStreamPromise = new Promise((resolve) => {
      resolveFirstStream = resolve;
    });
    const getUserMediaMock = vi
      .fn()
      .mockImplementationOnce(() => firstStreamPromise)
      .mockImplementation(() => Promise.resolve({ getTracks: () => [] }));

    Object.defineProperty(global.navigator, 'mediaDevices', {
      value: { getUserMedia: getUserMediaMock },
      writable: true,
      configurable: true,
    });

    renderKiosk();

    // The kiosk's own auto-start leaves startUsbCamera('cam-1') stuck
    // awaiting getUserMedia.
    await waitFor(() => expect(getUserMediaMock).toHaveBeenCalledTimes(1));

    // Switch cameras WHILE the first call is still pending — this re-triggers
    // the effect that calls startUsbCamera('cam-2') before the first call has
    // finished, which is exactly the race that can leak a stream/WS/interval.
    openSettings();
    fireEvent.mouseDown(await screen.findByRole('combobox'));
    const cam2Option = await screen.findByRole('option', { name: 'Camera 2' });
    fireEvent.click(cam2Option);

    // Give any (buggy) synchronous/microtask work a chance to run.
    await wait(10);

    // The in-flight guard must make the second call a no-op: getUserMedia is
    // NOT invoked again while the first call hasn't resolved yet.
    expect(getUserMediaMock).toHaveBeenCalledTimes(1);

    // Let the first call finish so the test doesn't leave dangling timers.
    await act(async () => {
      resolveFirstStream({ getTracks: () => [] });
    });
  });

  it('masks the member name on the bounding-box label for unknown-classified denials (member_not_found)', async () => {
    const fillTextSpy = vi.fn();
    const fakeCtx = {
      clearRect: vi.fn(),
      strokeRect: vi.fn(),
      fillRect: vi.fn(),
      fillText: fillTextSpy,
      measureText: vi.fn(() => ({ width: 100 })),
      strokeStyle: '',
      fillStyle: '',
      font: '',
      lineWidth: 0,
    };
    HTMLCanvasElement.prototype.getContext = vi.fn(() => fakeCtx) as any;

    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(
      ws,
      recognitionMessage({
        member_id: 'stale-member',
        member_name: 'Real Cached Name',
        access_granted: false,
        denial_reason: 'member_not_found',
        face_bbox: [10, 10, 50, 50],
      })
    );

    await waitFor(() => expect(fillTextSpy).toHaveBeenCalled());
    const labelsDrawn = fillTextSpy.mock.calls.map((call) => call[0]);
    expect(labelsDrawn.some((label) => label.includes('Real Cached Name'))).toBe(false);

    fillTextSpy.mockClear();

    // Triangulation: a real membership-category denial must still show the name.
    sendMessage(
      ws,
      recognitionMessage({
        member_id: 'member-2',
        member_name: 'Known Member',
        access_granted: false,
        denial_reason: 'expired_membership',
        face_bbox: [10, 10, 50, 50],
      })
    );

    await waitFor(() => expect(fillTextSpy).toHaveBeenCalled());
    const labelsDrawn2 = fillTextSpy.mock.calls.map((call) => call[0]);
    expect(labelsDrawn2.some((label) => label.includes('Known Member'))).toBe(true);
  });

  it('masks the member name in the recent check-ins chip strip for unknown-classified denials (member_not_found)', async () => {
    renderKiosk();
    const ws = await awaitAutoStartedCamera();

    sendMessage(
      ws,
      recognitionMessage({
        member_id: 'stale-member',
        member_name: 'Real Cached Name',
        access_granted: false,
        denial_reason: 'member_not_found',
        face_bbox: null,
      })
    );

    await waitFor(() => expect(screen.queryByText(/Real Cached Name/)).not.toBeInTheDocument());

    // Triangulation: a real membership-category denial must still show the name.
    sendMessage(
      ws,
      recognitionMessage({
        member_id: 'member-2',
        member_name: 'Known Member',
        access_granted: false,
        denial_reason: 'expired_membership',
        face_bbox: null,
      })
    );

    await waitFor(() => expect(screen.getByText(/Known Member/)).toBeInTheDocument());
  });
});
