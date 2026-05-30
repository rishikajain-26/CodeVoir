<<<<<<< HEAD
# React + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and [`typescript-eslint`](https://typescript-eslint.io) in your project.
=======
# CodeVoir Frontend

React + Vite frontend for the CodeVoir interview and opportunity-preparation experience.

## Run locally

```bash
npm install
npm run dev
```

The frontend expects the backend at `http://127.0.0.1:8000` unless `VITE_API_URL` is set.

```env
VITE_API_URL=http://127.0.0.1:8000
VITE_ELEVENLABS_API_KEY=optional_key
VITE_ELEVENLABS_VOICE_ID=optional_voice_id
```

## Current structure

```txt
src/App.jsx               Main app shell and legacy screen composition
src/pages/                Extracted pages
src/assets/               Static UI assets
src/main.jsx              React entrypoint
```

## Development note

`src/App.jsx` is intentionally left behavior-compatible for the current demo. New screens should be created in `src/pages/`, and reusable UI should be placed in `src/components/` before wiring it into `App.jsx`.
>>>>>>> b2a9557 (WIP: saving local work before sync)
