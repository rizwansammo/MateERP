import type { Metadata } from 'next';
import { notFound, redirect } from 'next/navigation';

import { ModuleRoute } from '@/features/system/ModuleRoute';
import { itemHref, resolveRoute } from '@/lib/navigation';

interface Props {
  params: Promise<{ slug: string[] }>;
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

  return <ModuleRoute itemId={route.item.id} group={route.group.label} subSlug={route.sub?.slug ?? null} />;
}
