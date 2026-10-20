/** Render a document number format, mirroring apps.company.services.render_number. */
export function renderNumber(format: string, on: Date, sequence: number): string {
  return format.replace(/\{(YYYY|YY|MM|#{3,8})\}/g, (_, token: string) => {
    if (token === 'YYYY') return String(on.getFullYear()).padStart(4, '0');
    if (token === 'YY') return String(on.getFullYear() % 100).padStart(2, '0');
    if (token === 'MM') return String(on.getMonth() + 1).padStart(2, '0');
    return String(sequence).padStart(token.length, '0');
  });
}

export function isValidNumberFormat(format: string): string | null {
  const fmt = format.trim().toUpperCase();
  if (fmt.length < 3 || fmt.length > 40) return 'Use 3–40 characters.';
  if (!/^(?:[A-Z0-9/_.-]|\{YYYY\}|\{YY\}|\{MM\}|\{#{3,8}\})+$/.test(fmt)) {
    return 'Use letters, digits, - / _ . and the tokens {YYYY} {YY} {MM} {###}.';
  }
  if ((fmt.match(/\{#{3,8}\}/g) ?? []).length !== 1) return 'Include exactly one sequence token such as {####}.';
  if (!/[A-Z]/.test(fmt.split('{')[0] ?? '')) return 'Start with a letter prefix such as INV-.';
  return null;
}
