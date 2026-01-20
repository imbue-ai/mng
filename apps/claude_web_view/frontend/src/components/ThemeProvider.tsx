import { Theme as RadixTheme } from "@radix-ui/themes";
import { type PropsWithChildren, useEffect, useState } from "react";

type ThemeAppearance = "light" | "dark";

declare global {
  interface Window {
    __INITIAL_THEME__?: string;
  }
}

export const ThemeProvider = ({ children }: PropsWithChildren) => {
  const [theme, setTheme] = useState<ThemeAppearance>("light");

  useEffect(() => {
    // Get initial theme from server-injected value
    const initialTheme = window.__INITIAL_THEME__ || "system";

    if (initialTheme === "system") {
      // Use system preference
      const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
      setTheme(mediaQuery.matches ? "dark" : "light");

      // Listen for system theme changes
      const handler = (e: MediaQueryListEvent) => {
        setTheme(e.matches ? "dark" : "light");
      };
      mediaQuery.addEventListener("change", handler);
      return () => mediaQuery.removeEventListener("change", handler);
    } else {
      setTheme(initialTheme as ThemeAppearance);
    }
  }, []);

  return (
    <RadixTheme accentColor="gold" grayColor="sand" appearance={theme}>
      {children}
    </RadixTheme>
  );
};
