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
    getStreamUrl: vi.fn(() => '/cv/stream/cam-1'),
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
    ...overrides,
  });
}

function renderKiosk() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <LanguageProvider>
        <MemoryRouter initialEntries={['/kiosk?cameraId=cam-1']}>
          <Kiosk />
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>
  );
}

async function enableUsbMode() {
  const settingsButton = screen.getByTestId('SettingsIcon').closest('button')!;
  fireEvent.click(settingsButton);

  const usbToggle = await screen.findByText(t.kiosk.usbCameraMode);
  fireEvent.click(usbToggle);

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
  vi.restoreAllMocks();
});

describe('Kiosk recognition state machine (USB mode)', () => {
  it('reveals the granted result even when the same person keeps sending frames faster than the verifying beat', async () => {
    renderKiosk();
    const ws = await enableUsbMode();

    // First frame for this person: enters the 500ms "verifying" beat.
    sendMessage(ws, recognitionMessage({ member_id: 'member-1', access_granted: true }));
    await screen.findByText(t.kiosk.verifying);

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
    const ws = await enableUsbMode();

    sendMessage(ws, recognitionMessage({ member_id: 'member-1', access_granted: true }));
    await waitFor(() => expect(screen.getByText(t.kiosk.welcomeBack)).toBeInTheDocument(), {
      timeout: 2000,
    });

    // Staff toggles USB mode off — this stops the camera/websocket.
    const usbToggleOff = screen.getByText(t.kiosk.usbCameraMode);
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
    const ws = await enableUsbMode();

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
    const ws = await enableUsbMode();

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
});
