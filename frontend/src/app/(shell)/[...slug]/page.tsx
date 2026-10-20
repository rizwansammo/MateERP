import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';

import { PlannedModule } from '@/features/system/PlannedModule';
import { NAVIGATION, itemHref, resolveRoute } from '@/lib/navigation';

interface Props {
  params: Promise<{ slug: string[] }>;
}

/** Pre-render every module section in the navigation tree. */
export function generateStaticParams() {
  return NAVIGATION.flatMap((group) =>
    group.items
      .filter((item) => item.id !== 'dashboard')
      .flatMap((item) =>
        item.subs?.length
          ? item.subs.map((s) => ({ slug: [item.id, ...s.slug.split('/')] }))
          : [{ slug: [item.id] }],
      ),
  );
}

function resolve(slug: string[]) {
  const route = resolveRoute(`/${slug.join('/')}`);
  // No module has pages below its sub-sections yet.
  if (!route || route.rest.length > 0) return null;
  return route;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const route = resolve((await params).slug);
  if (!route) return {};
  return { title: route.sub ? `${route.sub.label} · ${route.item.label}` : route.item.label };
}

export default async function ModulePage({ params }: Props) {
  const { slug } = await params;
  const route = resolve(slug);
  if (!route) notFound();

  // A bare module URL opens its first section, as in the prototype.
  if (slug.length === 1 && route.item.subs?.length) redirect(itemHref(route.item));

  return <PlannedModule item={route.item} group={route.group.label} current={route.sub} />;
}
