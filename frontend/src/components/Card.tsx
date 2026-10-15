import type { ReactNode } from "react";

type CardProps = {
  title?: string;
  children: ReactNode;
  className?: string;
};

export function Card({ title, children, className = "" }: CardProps) {
  return (
    <section className={`rounded-card border border-line bg-paper-raised p-5 shadow-card ${className}`}>
      {title ? <h2 className="mb-3 font-display text-xl text-ink">{title}</h2> : null}
      {children}
    </section>
  );
}
