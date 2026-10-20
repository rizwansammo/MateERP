import Link from 'next/link';

import { Wordmark } from '@/components/brand/Wordmark';

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 bg-bg px-4 text-center">
      <div className="text-[40px] text-tx">
        <Wordmark />
      </div>
      <div className="flex max-w-[460px] flex-col gap-2 border border-bd bg-sf p-8">
        <div className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-tx3">Error 404</div>
        <h1 className="m-0 text-[18px] font-semibold text-tx">Page not found</h1>
        <p className="m-0 text-[13px] leading-[1.55] text-tx2">
          The page you requested does not exist in this MateERP installation.
        </p>
        <Link href="/dashboard" className="mt-2 text-[12.5px] font-medium">
          Go to the dashboard
        </Link>
      </div>
    </div>
  );
}
