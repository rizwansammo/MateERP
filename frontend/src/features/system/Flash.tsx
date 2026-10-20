'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect } from 'react';

import { toast } from '@/components/ui/Toast';

const MESSAGES: Record<string, string> = {
  changed: 'Password changed. Other devices have been signed out.',
};

/** One-shot confirmation after a redirect (e.g. ?password=changed). */
export function Flash() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const key = params.get('password');
  useEffect(() => {
    if (key && MESSAGES[key]) {
      toast(MESSAGES[key]!);
      router.replace(pathname);
    }
  }, [key, pathname, router]);
  return null;
}
