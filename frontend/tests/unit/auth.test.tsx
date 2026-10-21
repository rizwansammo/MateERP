import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { LoginForm } from '@/features/auth/LoginForm';
import { validateNewPassword } from '@/features/auth/PasswordForm';
import { ModuleRoute } from '@/features/system/ModuleRoute';
import { Gate } from '@/features/settings/Gate';
import { SESSION_EXPIRED_EVENT, api } from '@/lib/api/client';
import { loginUrl, safeNext } from '@/lib/auth/redirect';

import { makeUser, mockApi, renderWithAuth, viewerUser } from './helpers';
import { nav } from './navigation-mock';

describe('safeNext (open-redirect protection)', () => {
  it.each([
    ['/settings/users', '/settings/users'],
    ['/sales/invoices?x=1', '/sales/invoices?x=1'],
    ['https://evil.example', '/dashboard'],
    ['//evil.example/path', '/dashboard'],
    ['/\\evil.example', '/dashboard'],
    ['javascript:alert(1)', '/dashboard'],
    ['/login?next=/x', '/dashboard'],
    [null, '/dashboard'],
  ])('%s → %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });

  it('builds login URLs that carry a safe destination', () => {
    expect(loginUrl('/settings/audit', 'expired')).toBe('/login?next=%2Fsettings%2Faudit&reason=expired');
    expect(loginUrl('//evil.example')).toBe('/login');
  });
});

describe('LoginForm', () => {
  it('validates required fields without calling the API', async () => {
    const calls = mockApi({});
    render(<LoginForm next={null} expired={false} />);
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Enter your username or email.')).toBeInTheDocument();
    expect(screen.getByText('Enter your password.')).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('shows the generic error and clears the password on failure', async () => {
    mockApi({
      'POST /auth/login/': [401, { error: { code: 'invalid_credentials', message: 'The username or password is incorrect.', details: null, request_id: 'r1' } }],
    });
    render(<LoginForm next={null} expired={false} />);
    await userEvent.type(screen.getByLabelText('Username or email'), 'alice');
    await userEvent.type(screen.getByLabelText('Password', { selector: 'input' }), 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByText('The username or password is incorrect.')).toBeInTheDocument();
    expect(screen.getByLabelText('Password', { selector: 'input' })).toHaveValue('');
  });

  it('signs in with CSRF and goes to the requested page', async () => {
    const calls = mockApi({ 'POST /auth/login/': makeUser() });
    render(<LoginForm next="/settings/users" expired={false} />);
    await userEvent.type(screen.getByLabelText('Username or email'), 'admin');
    await userEvent.type(screen.getByLabelText('Password', { selector: 'input' }), 'secret-passphrase');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/settings/users'));
    expect(nav.refresh).not.toHaveBeenCalled();
    const login = calls.find((c) => c.path === '/auth/login/')!;
    expect(login.headers['X-CSRFToken']).toBe('test-token');
    expect(login.body).toEqual({ identifier: 'admin', password: 'secret-passphrase', remember: false });
  });

  it('sends users with a temporary password to the password screen', async () => {
    mockApi({ 'POST /auth/login/': makeUser({ must_change_password: true }) });
    render(<LoginForm next="/settings/users" expired={false} />);
    await userEvent.type(screen.getByLabelText('Username or email'), 'new');
    await userEvent.type(screen.getByLabelText('Password', { selector: 'input' }), 'Temp-Password-1');
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/account/password'));
  });

  it('explains an expired session', () => {
    render(<LoginForm next={null} expired />);
    expect(screen.getByText(/session has ended/i)).toBeInTheDocument();
  });

  it('toggles password visibility', async () => {
    render(<LoginForm next={null} expired={false} />);
    const input = screen.getByLabelText('Password', { selector: 'input' });
    expect(input).toHaveAttribute('type', 'password');
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');
  });
});

describe('password rules', () => {
  it('checks length, numeric-only and confirmation', () => {
    expect(validateNewPassword('short', 'short').new_password).toMatch(/12 characters/);
    expect(validateNewPassword('123456789012', '123456789012').new_password).toMatch(/numeric/);
    expect(validateNewPassword('Long-enough-pass', 'different').confirm).toMatch(/match/);
    expect(validateNewPassword('Long-enough-pass', 'Long-enough-pass')).toEqual({});
  });
});

describe('session expiry', () => {
  it('redirects to login with reason=expired when the API returns 401', async () => {
    mockApi({ '/auth/me/': makeUser(), '/users/': [401, { error: { code: 'not_authenticated', message: 'x', details: null, request_id: null } }] });
    renderWithAuth(<div />);
    const handler = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, handler);
    await expect(api.get('/users/')).rejects.toThrow();
    expect(handler).toHaveBeenCalled();
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith(expect.stringContaining('/login?')));
    window.removeEventListener(SESSION_EXPIRED_EVENT, handler);
  });
});

describe('route protection in the UI', () => {
  it('Gate shows a restricted card without the permission', () => {
    mockApi({ '/auth/me/': viewerUser });
    renderWithAuth(<Gate anyOf={['users.manage']}><p>secret admin page</p></Gate>, viewerUser);
    expect(screen.getByText('Access restricted')).toBeInTheDocument();
    expect(screen.queryByText('secret admin page')).not.toBeInTheDocument();
  });

  it('a disabled optional module shows the disabled notice', async () => {
    mockApi({
      '/auth/me/': makeUser(),
      '/modules/': { optional: [{ key: 'inventory', label: 'Inventory', description: '', phase: 6, nav_id: 'inventory', enabled: false, implemented: false }], core: [] },
    });
    renderWithAuth(<ModuleRoute itemId="inventory" group="Operations" subSlug="items" />);
    expect(await screen.findByText(/is disabled/)).toBeInTheDocument();
  });

  it('does not mount working controls for a disabled module', async () => {
    mockApi({'/auth/me/':makeUser(),'/modules/':{optional:[{key:'inventory',enabled:false,implemented:true}],core:[]}});
    renderWithAuth(<ModuleRoute itemId="inventory" group="Operations" subSlug="items"><p>Stock controls</p></ModuleRoute>);
    expect(await screen.findByText(/is disabled/)).toBeVisible();
    expect(screen.queryByText('Stock controls')).not.toBeInTheDocument();
  });

  it('renders working child screens when the optional module is enabled', async () => {
    mockApi({'/auth/me/':makeUser(),'/modules/':{optional:[{key:'inventory',enabled:true,implemented:true}],core:[]}});
    renderWithAuth(<ModuleRoute itemId="inventory" group="Operations" subSlug="items"><p>Stock controls</p></ModuleRoute>);
    expect(await screen.findByText('Stock controls')).toBeVisible();
    expect(screen.queryByTestId('planned-notice')).not.toBeInTheDocument();
  });

  it('keeps working controls unavailable if module configuration cannot be loaded', async () => {
    mockApi({'/auth/me/':makeUser(),'/modules/':[503,{error:{code:'unavailable',message:'Try later',details:null,request_id:null}}]});
    renderWithAuth(<ModuleRoute itemId="inventory" group="Operations" subSlug="items"><p>Stock controls</p></ModuleRoute>);
    expect(await screen.findByText('Module settings unavailable')).toBeVisible();
    expect(screen.queryByText('Stock controls')).not.toBeInTheDocument();
  });

  it('planned modules stay honest when enabled', async () => {
    mockApi({ '/auth/me/': makeUser(), '/modules/': { optional: [], core: [] } });
    renderWithAuth(<ModuleRoute itemId="banking" group="Finance" subSlug="journals" />);
    expect(await screen.findByTestId('planned-notice')).toHaveTextContent('Phase 3');
  });
});
