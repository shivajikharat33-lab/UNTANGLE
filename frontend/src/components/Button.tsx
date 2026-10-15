import type { ButtonHTMLAttributes, ReactNode, Ref } from "react";
import { buttonClass, type ButtonVariant } from "../lib/buttonClass";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
  ref?: Ref<HTMLButtonElement>;
};

export function Button({ variant = "primary", className = "", type = "button", children, ref, ...props }: ButtonProps) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClass(variant, className)}
      {...props}
    >
      {children}
    </button>
  );
}
