'use client';

import { type DragEvent, useId, useRef, useState } from 'react';

import { cn } from '@/lib/cn';

import { Icon } from './Icon';

export const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
export const MAX_IMAGE_BYTES = 2 * 1024 * 1024;

/** Client-side pre-check for convenience; the server validates the real content. */
export function checkImage(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type)) return 'Choose a PNG, JPEG or WEBP image.';
  if (file.size > MAX_IMAGE_BYTES) return 'Images must be 2 MB or smaller.';
  return null;
}

interface FileDropProps {
  label: string;
  hint?: string;
  onFile: (file: File) => void;
  disabled?: boolean;
  busy?: boolean;
}

/** Dashed drop zone (prototype file field). Accepts one image. */
export function FileDrop({ label, hint = 'PNG, JPEG or WEBP · up to 2 MB', onFile, disabled, busy }: FileDropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const id = useId();
  const [over, setOver] = useState(false);

  const take = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onFile(file);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    if (!disabled) take(event.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cn(
        'flex items-center gap-3 border border-dashed p-4',
        over ? 'border-ac bg-infos' : 'border-bd2 bg-sf2',
        disabled && 'opacity-60',
      )}
    >
      <Icon name={busy ? 'progress_activity' : 'upload_file'} size={26} className={cn('text-ac', busy && 'animate-spin')} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <label htmlFor={id} className="cursor-pointer text-[13px] font-medium text-tx">
          {busy ? 'Uploading…' : label}
        </label>
        <span className="text-[11.5px] text-tx3">Drop a file here or click to browse · {hint}</span>
      </div>
      <input
        ref={inputRef}
        id={id}
        type="file"
        accept={IMAGE_TYPES.join(',')}
        disabled={disabled || busy}
        className="sr-only"
        onChange={(e) => {
          take(e.target.files);
          e.target.value = '';
        }}
      />
      <button
        type="button"
        disabled={disabled || busy}
        onClick={() => inputRef.current?.click()}
        className="h-[30px] border border-bd2 bg-sf px-2.5 text-[12px] font-medium text-tx hover:bg-sf3 disabled:opacity-55"
      >
        Browse
      </button>
    </div>
  );
}
