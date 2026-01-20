import type { HTMLProps, PropsWithChildren } from "react";
import styles from "./Code.module.scss";

interface CodeProps extends PropsWithChildren, Omit<HTMLProps<HTMLSpanElement>, "size"> {
  size?: "1" | "2" | "3";
}

export const Code = ({ className, children, size = "2", style, ...rest }: CodeProps) => {
  const classNames = [styles.code, className].filter(Boolean).join(" ");

  return (
    <span className={classNames} style={{ ...style, fontSize: `var(--font-size-${size})` }} {...rest}>
      {children}
    </span>
  );
};
