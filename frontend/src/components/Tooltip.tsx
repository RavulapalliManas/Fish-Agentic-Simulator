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
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-[color:var(--line-strong)] bg-white/80 text-[10px] font-semibold text-[color:var(--ink-muted)] transition hover:border-[color:var(--accent)] hover:text-[color:var(--accent)] focus:outline-none focus:ring-2 focus:ring-[color:var(--accent-soft)]"
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
          className="absolute right-0 top-7 z-20 w-64 rounded-2xl border border-[color:var(--line-strong)] bg-[color:var(--panel-strong)] px-3 py-3 text-xs font-medium leading-5 text-[color:var(--ink)] shadow-[0_18px_48px_rgba(15,33,46,0.18)] backdrop-blur"
        >
          {content}
        </span>
      )}
    </span>
  );
}

export default Tooltip;
