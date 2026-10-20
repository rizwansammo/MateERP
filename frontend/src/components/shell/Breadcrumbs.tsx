'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Fragment } from 'react';

import { Icon } from '@/components/ui/Icon';
import { cn } from '@/lib/cn';
import { itemHref, resolveRoute, subHref } from '@/lib/navigation';

interface Crumb {
  label: string;
  href?: string;
}

const STATIC_PAGES: Record<string, string> = {
  '/design-system': 'Design System',
  '/account/profile': 'My Profile',
};

export function buildCrumbs(pathname: string): Crumb[] {
  const crumbs: Crumb[] = [{ label: 'Home', href: '/dashboard' }];
  const staticPage = STATIC_PAGES[pathname];
  if (staticPage) return [...crumbs, { label: staticPage }];

  const route = resolveRoute(pathname);
  if (!route) return crumbs;
  crumbs.push({ label: route.group.label });
  crumbs.push({ label: route.item.label, href: itemHref(route.item) });
  if (route.sub) crumbs.push({ label: route.sub.label, href: subHref(route.item, route.sub) });
  route.rest.forEach((segment) => crumbs.push({ label: segment }));
  return crumbs;
}

export function Breadcrumbs() {
  const crumbs = buildCrumbs(usePathname());

  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
      {crumbs.map((crumb, index) => {
        const last = index === crumbs.length - 1;
        const className = cn(
          'max-w-[220px] truncate whitespace-nowrap text-[12.5px] leading-[normal] hover:no-underline',
          last ? 'font-semibold text-tx' : 'font-normal text-tx3',
          last ? 'min-w-0 max-md:max-w-none' : 'shrink-0 max-sm:hidden',
        );
        return (
          <Fragment key={`${crumb.label}-${index}`}>
            {index > 0 && (
              <Icon name="chevron_right" size={15} className="text-tx3 max-sm:hidden" />
            )}
            {crumb.href && !last ? (
              <Link href={crumb.href} className={cn(className, 'hover:text-tx')}>
                {crumb.label}
              </Link>
            ) : (
              <span aria-current={last ? 'page' : undefined} className={className}>
                {crumb.label}
              </span>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
