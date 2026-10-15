type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
};

export function PageHeader({ eyebrow, title, description }: PageHeaderProps) {
  return (
    <header className="mb-6 max-w-3xl">
      {eyebrow ? <p className="mb-2 font-mono text-xs uppercase tracking-[0.18em] text-copper-deep">{eyebrow}</p> : null}
      <h1 className="font-display text-title text-ink">{title}</h1>
      {description ? <p className="mt-2 text-base leading-7 text-ink-soft">{description}</p> : null}
    </header>
  );
}
