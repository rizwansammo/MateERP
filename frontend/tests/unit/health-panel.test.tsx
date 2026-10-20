import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { HealthPanel } from '@/features/system/HealthPanel';

const healthy = {
  status: 'ok',
  service: 'mateerp-backend',
  version: '0.1.0',
  environment: 'development',
  time: '2026-10-20T10:00:00+06:00',
  checks: { database: { status: 'ok', latency_ms: 2.5 } },
};

function mockFetch(status: number, body: unknown) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => new Response(JSON.stringify(body), { status }));
}

describe('HealthPanel', () => {
  it('shows a loading state, then live backend status', async () => {
    mockFetch(200, healthy);
    render(<HealthPanel />);

    expect(screen.getByText(/checking backend/i)).toBeInTheDocument();
    expect(await screen.findByText('Operational', { selector: 'span' })).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('PostgreSQL · 2.5 ms')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
  });

  it('shows a degraded state when the database is down', async () => {
    mockFetch(503, {
      ...healthy,
      status: 'unavailable',
      checks: { database: { status: 'unavailable', latency_ms: null } },
    });
    render(<HealthPanel />);

    expect(await screen.findByText('Unavailable')).toBeInTheDocument();
    expect(screen.getAllByText('Degraded').length).toBeGreaterThan(0);
  });

  it('explains when the backend is unreachable and can retry', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));
    render(<HealthPanel />);

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be reached/i);

    fetchMock.mockImplementation(async () => new Response(JSON.stringify(healthy), { status: 200 }));
    await userEvent.click(screen.getByRole('button', { name: /refresh/i }));
    expect(await screen.findByText('Connected')).toBeInTheDocument();
  });
});
