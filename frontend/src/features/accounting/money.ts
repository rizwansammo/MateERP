/** Exact parsing and formatting. Monetary Number/parseFloat conversions are forbidden here. */
export function minor(value: string, places = 6): bigint {
  if (!/^-?\d+(\.\d+)?$/.test(value))
    throw new Error("Enter an exact decimal amount.");
  const negative = value.startsWith("-");
  const [whole = "0", frac = ""] = value.replace("-", "").split(".");
  if (frac.slice(places).replace(/0/g, ""))
    throw new Error("Too many decimal places.");
  return (
    (BigInt(whole) * 10n ** BigInt(places) +
      BigInt(frac.slice(0, places).padEnd(places, "0") || "0")) *
    (negative ? -1n : 1n)
  );
}
export function decimal(value: bigint, places = 6): string {
  const sign = value < 0n ? "-" : "";
  const v = value < 0n ? -value : value;
  const scale = 10n ** BigInt(places);
  return `${sign}${v / scale}${places ? `.${(v % scale).toString().padStart(places, "0")}` : ""}`;
}
export function amount(
  value: string | undefined,
  currency = "",
  grouping = "international",
): string {
  if (value === undefined) return "—";
  const currencyPlaces = currency === "JPY" || currency === "KRW" ? 0 : 2;
  try {
    // Unit prices/costs can have finer precision than posted currency amounts.
    // Preserve those digits while retaining the usual minimum currency scale.
    const places = Math.max(currencyPlaces, (value.split(".")[1] ?? "").replace(/0+$/, "").length);
    const exact = decimal(minor(value, places), places);
    const [whole = "0", fraction] = exact.split(".");
    const sign = whole.startsWith("-") ? "−" : "";
    const digits = whole.replace("-", "");
    const grouped =
      grouping === "south_asian" && digits.length > 3
        ? `${digits.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${digits.slice(-3)}`
        : digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return `${currency ? `${currency} ` : ""}${sign}${grouped}${fraction !== undefined ? `.${fraction}` : ""}`;
  } catch {
    return `${currency ? `${currency} ` : ""}${value}`;
  }
}
