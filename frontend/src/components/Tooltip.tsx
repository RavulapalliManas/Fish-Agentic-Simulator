import { useId, useState } from "react";

type TooltipProps = {
  content: string;
};

function Tooltip({ content }: TooltipProps) {
  const tooltipId = useId();
  const [open, setOpen] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        aria-describedby={open ? tooltipId : undefined}
        aria-label="More information"
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-[color:var(--line-strong)] bg-white text-[10px] font-semibold text-[color:var(--ink-faint)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)] focus:outline-none focus:ring-2 focus:ring-[color:var(--accent-soft)]"
        type="button"
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((current) => !current)}
        onFocus={() => setOpen(true)}
      >
        i
      </button>
      {open && (
        <span
          id={tooltipId}
          role="tooltip"
          className="absolute right-0 top-6 z-40 w-60 rounded-lg border border-[color:var(--line-strong)] bg-white px-3 py-2 text-xs font-medium leading-5 text-[color:var(--ink-muted)] shadow-[0_4px_16px_rgba(15,27,45,0.12)]"
        >
          {content}
        </span>
      )}
    </span>
  );
}

export default Tooltip;
