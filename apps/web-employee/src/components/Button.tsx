import clsx from "clsx";
import React from "react";

type Props = React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" };

export function Button({ className, variant = "primary", ...props }: Props) {
  const base = "inline-flex items-center justify-center rounded-xl px-4 py-2 text-sm font-medium transition";
  const styles =
    variant === "primary"
      ? "bg-black text-white hover:opacity-90"
      : variant === "danger"
      ? "bg-red-600 text-white hover:opacity-90"
      : "bg-white text-black border border-black/15 hover:bg-black/5";
  return <button className={clsx(base, styles, className)} {...props} />;
}
