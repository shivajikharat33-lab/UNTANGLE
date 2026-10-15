export type ButtonVariant = "primary" | "secondary" | "ghost";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-copper-deep text-paper hover:bg-copper",
  secondary: "bg-paper-raised text-ink border border-line hover:border-ink",
  ghost: "bg-transparent text-ink hover:bg-ink/5",
};

export function buttonClass(variant: ButtonVariant = "primary", className = ""): string {
  return `inline-flex items-center justify-center gap-2 rounded-control px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`;
}
