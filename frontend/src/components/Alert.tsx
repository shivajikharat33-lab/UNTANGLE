import type { ReactNode } from "react";

type AlertTone = "info" | "success" | "warning" | "error";

const tones: Record<AlertTone, string> = {
  info: "bg-alert-info-bg text-alert-info-fg",
  success: "bg-alert-success-bg text-alert-success-fg",
  warning: "bg-alert-warning-bg text-alert-warning-fg",
  error: "bg-alert-error-bg text-alert-error-fg",
};

type AlertProps = {
  tone?: AlertTone;
  title: string;
  children?: ReactNode;
};

export function Alert({ tone = "info", title, children }: AlertProps) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-card px-4 py-3 ${tones[tone]}`}>
      <p className="font-semibold">{title}</p>
      {children ? <div className="mt-1 text-sm leading-6">{children}</div> : null}
    </div>
  );
}
