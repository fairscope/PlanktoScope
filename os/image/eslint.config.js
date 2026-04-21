import js from "@eslint/js"
import globals from "globals"
import { defineConfig, globalIgnores } from "eslint/config"
import nodePlugin from "eslint-plugin-n"

export default defineConfig([
  globalIgnores([".build"]),
  nodePlugin.configs["flat/recommended-script"],
  {
    files: ["**/*.{js,mjs,cjs}"],
    plugins: { js },
    extends: ["js/recommended"],
    languageOptions: {
      sourceType: "module",
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      "no-empty": ["error", { allowEmptyCatch: true }],
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "n/no-top-level-await": "off",
      "n/no-process-exit": "off",
      "n/no-unsupported-features/node-builtins": [
        "error",
        { allowExperimental: true },
      ],
      "n/hashbang": "off",
    },
  },
])
