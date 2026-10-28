import os from "node:os"
import { defineConfig } from "vite"
import solidPlugin from "vite-plugin-solid"
import Pages from "vite-plugin-pages"

import solidSvg from "vite-plugin-solid-svg"

export default defineConfig({
  plugins: [
    Pages({
      dirs: ["src/pages"],
    }),
    solidPlugin(),
    solidSvg({
      defaultAsComponent: true,
    }),
  ],
  server: {
    port: 3000,
    allowedHosts: [
      os.hostname(),
      `${os.hostname()}.local`,
      "192.168.4.1",
    ],
  },
  build: {
    target: "esnext",
  },
})
