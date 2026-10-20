import Link from 'next/link';

import { Icon } from './Icon';

interface RestrictedProps {
  title: string;
  children: React.ReactNode;
  action?: { label: string; href: string };
  icon?: string;
}

/** Access-restricted / unavailable card (prototype restricted panel). */
export function Restricted({ title, children, action, icon = 'lock' }: RestrictedProps) {
  return (
    <div className="mx-4 my-[12vh] flex max-w-[560px] flex-col items-start gap-2.5 border border-bd bg-sf p-8 sm:mx-auto">
      <Icon name={icon} size={30} className="text-warn" />
      <h1 className="m-0 text-[18px] font-semibold text-tx">{title}</h1>
      <div className="text-[13px] leading-[1.55] text-tx2">{children}</div>
      {action && (
        <Link
          href={action.href}
          className="mt-1.5 inline-flex h-[34px] items-center border border-bd2 bg-sf px-3.5 text-[12.5px] font-medium text-tx hover:bg-sf3 hover:text-tx hover:no-underline"
        >
          {action.label}
        </Link>
      )}
    </div>
  );
}
