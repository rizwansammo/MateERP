'use client';

/* eslint-disable @next/next/no-img-element -- private, auth-gated files */
import { useState } from 'react';
import { createPortal } from 'react-dom';

import { Icon } from '@/components/ui/Icon';
import { formatDate } from '@/lib/format';
import { useDialogBehaviour } from '@/components/ui/Overlay';

import { ViewerToolbar, ZoomControl } from '@/features/documents/DocumentStage';

import { KIND_LABEL } from './shared';
import type { DocumentKind } from './types';

export interface PrivateDocumentView {
  title: string; content_type: string; url: string; download_url: string; document_date: string;
  kind?: DocumentKind; label?: string; generated?: boolean; restricted?: boolean; customer_name?: string | null; vendor_name?: string | null;
}

/** Dark document viewer (prototype DocViewer chrome) for stored PDFs and images. */
export function FileViewer({ doc, onClose }: { doc: PrivateDocumentView; onClose: () => void }) {
  const [zoom, setZoom] = useState(1);
  const panel = useDialogBehaviour(true, onClose);
  const pdf = doc.content_type === 'application/pdf';
  const party = doc.customer_name ?? doc.vendor_name ?? '';
  return createPortal(
    <div ref={panel} role="dialog" aria-modal="true" aria-label={doc.title} className="fixed inset-0 z-[70] flex flex-col bg-[#0A0E13] text-[#E6EDF5]">
      <ViewerToolbar
        icon={pdf ? 'picture_as_pdf' : 'image'}
        title={doc.title}
        subtitle={`${doc.label ?? (doc.kind ? KIND_LABEL[doc.kind] : 'Private evidence')} · ${party} · ${formatDate(doc.document_date)}${doc.generated ? ' · system-generated, immutable' : ''}${doc.restricted ? ' · restricted banking evidence' : ''}`}
        onClose={onClose}
      >
        <ZoomControl zoom={zoom} onZoom={setZoom} />
        <button type="button" aria-label="Toggle fullscreen" className="flex size-[30px] items-center justify-center border border-[#2A3644] text-white" onClick={() => { if (document.fullscreenElement) void document.exitFullscreen(); else void panel.current?.requestFullscreen(); }}><Icon name="fullscreen" size={18} /></button>
        <a
          href={doc.download_url}
          className="flex h-[30px] items-center gap-[5px] border border-brand bg-brand px-3 text-[12px] font-semibold text-brand-ink hover:no-underline"
        >
          <Icon name="download" size={17} /> Download {pdf && doc.generated ? 'PDF' : 'original'}
        </a>
      </ViewerToolbar>
      <div className="flex min-h-0 flex-1 justify-center overflow-auto bg-[#151B23] p-7 max-sm:p-3">
        {pdf ? (
          <iframe key={zoom} src={`${doc.url}#zoom=${Math.round(zoom * 100)}`} title={doc.title} className="h-full w-full max-w-[1100px] border-0 bg-white" />
        ) : (
          <img src={doc.url} alt={doc.title} className="h-fit max-w-none flex-none bg-white shadow-[0_10px_40px_rgba(0,0,0,.5)]" style={{ width: `${Math.round(900 * zoom)}px` }} />
        )}
      </div>
    </div>,
    document.body,
  );
}
