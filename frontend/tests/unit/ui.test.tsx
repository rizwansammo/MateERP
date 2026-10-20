import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Wordmark } from '@/components/brand/Wordmark';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Field } from '@/components/ui/Field';
import { Input } from '@/components/ui/Input';
import { IconButton } from '@/components/ui/IconButton';

describe('Button', () => {
  it('renders variants and handles clicks', async () => {
    const onClick = vi.fn();
    render(
      <Button variant="primary" icon="add" onClick={onClick}>
        Create
      </Button>,
    );

    const button = screen.getByRole('button', { name: /create/i });
    expect(button).toHaveAttribute('data-variant', 'primary');
    expect(button).toHaveAttribute('type', 'button');
    await userEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('does not fire when disabled', async () => {
    const onClick = vi.fn();
    render(
      <Button disabled onClick={onClick}>
        Save
      </Button>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onClick).not.toHaveBeenCalled();
  });

  it('uses no rounded-corner utilities', () => {
    render(<Button>Sharp</Button>);
    expect(screen.getByRole('button').className).not.toMatch(/rounded/);
  });
});

describe('IconButton', () => {
  it('requires and exposes an accessible label', () => {
    render(<IconButton icon="notifications" label="Notifications" />);
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
  });
});

describe('Badge', () => {
  it('renders the tone and text', () => {
    render(<Badge tone="ok">Posted</Badge>);
    expect(screen.getByText('Posted')).toHaveAttribute('data-tone', 'ok');
  });
});

describe('Field', () => {
  it('associates the label and announces errors', () => {
    render(
      <Field label="Amount" htmlFor="amount" required error="Required">
        <Input id="amount" invalid />
      </Field>,
    );
    expect(screen.getByLabelText(/amount/i)).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
  });
});

describe('Wordmark', () => {
  it('reads as MateERP and keeps the M / ATE / ERP composition', () => {
    render(<Wordmark />);
    const mark = screen.getByRole('img', { name: 'MateERP' });
    const parts = Array.from(mark.children).map((el) => el.textContent);
    expect(parts).toEqual(['M', 'ATE', 'ERP']);
    expect(mark.children[1]?.className).toContain('text-[.667em]');
    expect(mark.children[2]?.className).toContain('text-brand');
  });
});
