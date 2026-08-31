import clsx from "clsx";
import React from "react";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" };

export function Button({ className, variant = "primary", type = "button", ...props }: Props) {
  // Aligned to the ds.tsx `Action` primitive so legacy Button call sites share
  // the same calm design language (accent primary, hairline secondary).
  const base = "inline-flex items-center justify-center gap-1.5 rounded-md px-4 py-2 text-sm font-medium transition-colors duration-150 ease-calm disabled:opacity-40";
  const styles =
    variant === "primary"
      ? "bg-accent text-accent-fg hover:opacity-90"
      : variant === "danger"
      ? "bg-danger text-white hover:opacity-90"
      : "bg-surface text-ink border border-line hover:bg-sunken";
  return <button type={type} className={clsx(base, styles, className)} {...props} />;
}
