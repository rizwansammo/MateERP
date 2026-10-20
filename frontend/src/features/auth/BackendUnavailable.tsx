import { Wordmark } from '@/components/brand/Wordmark';
import { Icon } from '@/components/ui/Icon';

/** Shown when the session cannot be verified because the API is down. */
export function BackendUnavailable() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-bg px-4">
      <div className="text-[36px] text-tx">
        <Wordmark />
      </div>
      <div role="alert" className="flex max-w-[460px] flex-col gap-2 border border-bd bg-sf p-8">
        <Icon name="cloud_off" size={30} className="text-err" />
        <h1 className="m-0 text-[18px] font-semibold text-tx">MateERP server unavailable</h1>
        <p className="m-0 text-[13px] leading-[1.55] text-tx2">
          Your session could not be verified because the MateERP API is not responding. Start
          the local stack with <code className="font-mono text-[12px]">docker compose up -d</code>{' '}
          and reload this page.
        </p>
      </div>
    </div>
  );
}
