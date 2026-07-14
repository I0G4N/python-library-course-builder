import { defineConfig } from "vite";
import vinext from "vinext";

export default defineConfig({
  plugins: [vinext()],
  server: process.env.CODEX_SANDBOX === "seatbelt"
    ? { watch: { useFsEvents: false, usePolling: true } }
    : undefined,
});
