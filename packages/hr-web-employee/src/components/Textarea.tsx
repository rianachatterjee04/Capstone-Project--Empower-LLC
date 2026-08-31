import clsx from "clsx";
import React from "react";

type Props = React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; hint?: string };

export function Textarea({ className, label, hint, ...props }: Props) {
  return (
    <label className="block">
      {label ? <div className="mb-1 text-sm font-medium text-ink">{label}</div> : null}
      <textarea
        className={clsx(
          "w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm outline-none placeholder:text-faint focus:ring-2 focus:ring-accent/30 focus:border-accent",
          className
        )}
        {...props}
      />
      {hint ? <div className="mt-1 text-xs text-muted">{hint}</div> : null}
    </label>
  );
}
