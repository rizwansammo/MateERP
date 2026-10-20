import type { ReactNode } from 'react';

import { Icon } from './Icon';

interface EmptyStateProps {
  icon?: string;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ icon = 'inbox', title, children, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-5 py-10 text-center">
      <Icon name={icon} size={30} className="text-tx3" />
      <div className="text-[13.5px] font-semibold text-tx">{title}</div>
      {children && <div className="max-w-[420px] text-[12.5px] text-pretty text-tx3">{children}</div>}
      {action}
    </div>
  );
}
