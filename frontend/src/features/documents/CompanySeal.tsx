import { useId } from 'react';

import type { SealConfig } from '@/lib/api/types';

/**
 * Visual company stamp (circle or square), drawn as SVG so it stays sharp
 * in print. Geometry follows the approved prototype's stamp editor. This is
 * a visual seal only — not a certified digital signature.
 */
export function CompanySeal({ seal, size = 112 }: { seal: SealConfig; size?: number }) {
  const id = useId().replace(/:/g, '');
  const color = seal.color || '#1E4FD8';
  const font = 'var(--font-plex-sans), Arial, sans-serif';
  const top = (seal.top || '').slice(0, 30);
  const bottom = (seal.bottom || '').slice(0, 26);
  const center = (seal.center || '').slice(0, seal.shape === 'square' ? 10 : 9);

  return (
    <svg
      role="img"
      aria-label={`Company seal: ${[top, center, bottom].filter(Boolean).join(' · ')}`}
      viewBox="-180 -180 360 360"
      width={size}
      height={size}
      style={{ color }}
    >
      {seal.shape === 'square' ? (
        <g fill="currentColor" stroke="currentColor">
          <rect x={-164} y={-164} width={328} height={328} fill="none" strokeWidth={7} />
          <rect x={-150} y={-150} width={300} height={300} fill="none" strokeWidth={2} />
          <rect x={-120} y={-92} width={240} height={2} stroke="none" />
          <rect x={-120} y={90} width={240} height={2} stroke="none" />
          <g stroke="none" textAnchor="middle" dominantBaseline="middle" fontFamily={font}>
            <text y={-118} fontSize={22} fontWeight={700}>{top}</text>
            <text y={120} fontSize={22} fontWeight={700}>{bottom}</text>
            <text y={2} fontSize={50} fontWeight={800}>{center}</text>
          </g>
        </g>
      ) : (
        <g fill="currentColor" stroke="currentColor">
          <circle r={168} fill="none" strokeWidth={7} />
          <circle r={150} fill="none" strokeWidth={2} />
          <circle r={92} fill="none" strokeWidth={2} />
          <defs>
            <path id={`${id}-top`} d="M -121 0 A 121 121 0 0 1 121 0" />
            <path id={`${id}-bottom`} d="M -121 0 A 121 121 0 0 0 121 0" />
          </defs>
          <g stroke="none" fontFamily={font} fontWeight={700} fontSize={25} letterSpacing={3}>
            <text dominantBaseline="middle">
              <textPath href={`#${id}-top`} startOffset="50%" textAnchor="middle">{top}</textPath>
            </text>
            <text dominantBaseline="middle">
              <textPath href={`#${id}-bottom`} startOffset="50%" textAnchor="middle">{bottom}</textPath>
            </text>
          </g>
          <g stroke="none" textAnchor="middle" dominantBaseline="middle" fontFamily={font}>
            <text x={-121} y={1} fontSize={20} fontWeight={900}>★</text>
            <text x={121} y={1} fontSize={20} fontWeight={900}>★</text>
            <text y={2} fontSize={center.length > 6 ? 30 : 40} fontWeight={800}>{center}</text>
          </g>
        </g>
      )}
    </svg>
  );
}
