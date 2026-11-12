import React, { useId } from "react";

/*
 * Lia's logo, inline so it follows the theme: colours come from --lia-ink / --lia-blue
 * (index.css), and the clapper stripes are real holes (mask), so it works on any background.
 * Source files for other uses: /brand/*.svg
 */

const SPARK =
  "M64 63.5C65.3 72.3 68.5 75.6 77 77.5C68.5 79.4 65.3 82.7 64 91.5C62.7 82.7 59.5 79.4 51 77.5C59.5 75.6 62.7 72.3 64 63.5Z";
const BUBBLE =
  "M30 54H98A14 14 0 0 1 112 68V87A14 14 0 0 1 98 101H51L31.5 113.8C29 115.4 26.3 113 27.4 110.4L31 101H30A14 14 0 0 1 16 87V68A14 14 0 0 1 30 54Z";

function Symbol({ maskId }) {
  return (
    <>
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse" x="0" y="0" width="128" height="128">
          <rect x="16" y="33" width="96" height="17" rx="5" fill="#fff" />
          <g fill="#000">
            <polygon points="38,33 52,33 43,50 29,50" />
            <polygon points="66,33 80,33 71,50 57,50" />
            <polygon points="94,33 108,33 99,50 85,50" />
          </g>
        </mask>
      </defs>
      <rect x="16" y="33" width="96" height="17" rx="5" fill="var(--lia-ink)" mask={`url(#${maskId})`} transform="rotate(-14 16 50)" />
      <path fill="var(--lia-blue)" d={BUBBLE} />
      <path fill="var(--lia-spark)" d={SPARK} />
    </>
  );
}

/* The symbol alone (clapper + bubble + spark). */
export function LiaMark({ size = 20, title = "", className = "" }) {
  const id = `lia-${useId().replace(/:/g, "")}`;
  return (
    <svg
      className={`lia-mark ${className}`}
      viewBox="0 0 128 128"
      width={size}
      height={size}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title || undefined}
    >
      <Symbol maskId={id} />
    </svg>
  );
}

/* Symbol + "lia" wordmark. */
export function LiaLogo({ height = 24, title = "Lia" }) {
  const id = `lia-${useId().replace(/:/g, "")}`;
  return (
    <svg className="lia-mark" viewBox="0 0 250 128" height={height} width={(height * 250) / 128} role="img" aria-label={title}>
      <Symbol maskId={id} />
      <g fill="var(--lia-ink)">
        <rect x="132" y="33" width="13" height="68" rx="6.5" />
        <rect x="157" y="59" width="13" height="42" rx="6.5" />
        <circle cx="201" cy="80" r="14.5" fill="none" stroke="var(--lia-ink)" strokeWidth="13" />
        <rect x="209" y="59" width="13" height="42" rx="6.5" />
      </g>
      <path
        fill="var(--lia-blue)"
        d="M163.5 33.5C164.4 39.6 166.6 41.8 172.5 43C166.6 44.2 164.4 46.4 163.5 52.5C162.6 46.4 160.4 44.2 154.5 43C160.4 41.8 162.6 39.6 163.5 33.5Z"
      />
    </svg>
  );
}
