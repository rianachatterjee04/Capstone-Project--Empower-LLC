import clsx from "clsx";
import React from "react";

type Props = React.InputHTMLAttributes<HTMLInputElement> & { label?: string; hint?: string };

export function Input({ className, label, hint, ...props }: Props) {
  return (
    <label className="block">
      {label ? <div className="mb-1 text-sm font-medium">{label}</div> : null}
      <input
        className={clsx(
          "w-full rounded-xl border border-black/15 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-black/20",
          className
        )}
        {...props}
      />
      {hint ? <div className="mt-1 text-xs text-black/60">{hint}</div> : null}
    </label>
  );
}
