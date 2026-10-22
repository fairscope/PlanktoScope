import js from "@eslint/js"
import globals from "globals"
import { defineConfig, globalIgnores } from "eslint/config"
import nodePlugin from "eslint-plugin-n"
import solid from "eslint-plugin-solid/configs/recommended"

export default defineConfig([
  globalIgnores([
    "controller/.venv",
    "segmenter/.venv",
    "frontend/dist",
    "frontend/public",
  ]),
  {
    ...nodePlugin.configs["flat/recommended-script"],
    files: ["**/*.{js,mjs,cjs}", "!frontend/**"],
  },
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
      "n/no-unsupported-features/node-builtins": [
        "error",
        { allowExperimental: true, version: ">=26.3.0" },
      ],
      "n/no-process-exit": "off",
      "n/hashbang": "off",
    },
  },
  {
    files: ["lib/**/*.{js,mjs,cjs}"],
    rules: {
      "n/no-top-level-await": "error",
      "n/no-process-exit": "error",
    },
  },
  {
    files: ["frontend/**/*.{js,jsx}"],
    languageOptions: {
      sourceType: "module",
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
      globals: { ...globals.browser },
    },
    ...solid,
  },
])
