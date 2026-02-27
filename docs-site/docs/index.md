---
title: ClawLite
slug: /
---

<div className="hero-pro">
  <div className="hero-badges">
    <img src="https://img.shields.io/badge/version-0.3.0-7c3aed?style=for-the-badge" alt="version"/>
    <img src="https://img.shields.io/badge/license-MIT-10b981?style=for-the-badge" alt="license"/>
    <img src="https://img.shields.io/github/stars/eobarretooo/ClawLite?style=for-the-badge" alt="stars"/>
    <img src="https://img.shields.io/badge/downloads-growing-f59e0b?style=for-the-badge" alt="downloads"/>
  </div>

  <h1>ClawLite</h1>
  <p className="hero-tagline">Universal AI assistant for Linux + Termux. Fast, portable, and production-ready.</p>
  <p className="hero-sub">Run autonomous workflows, gateway APIs, and modular skills in one consistent runtime.</p>

  <div className="hero-cta">
    <a className="button button--primary button--lg" href="/ClawLite/getting-started">Get Started</a>
    <a className="button button--secondary button--lg" href="/ClawLite/gateway-api">View Gateway API</a>
  </div>
</div>

## Live Terminal Demo

<div className="terminal-demo">
  <pre>
{`$ clawlite onboarding
✅ Model configured: openai/gpt-4o-mini
✅ Gateway token generated

$ clawlite gateway --port 8787
[clawlite] gateway online at http://0.0.0.0:8787

$ curl http://127.0.0.1:8787/health
{"ok":true,"service":"clawlite-gateway","connections":0}`}
  </pre>
</div>

## Compatibility

<div className="compat-grid">
  <div className="compat-item">🐧 Linux</div>
  <div className="compat-item">📱 Termux</div>
  <div className="compat-item">🤖 Android</div>
  <div className="compat-item">🧠 ARM64 / x86_64</div>
</div>

## What People Are Building

<div className="cards-grid">
  <div className="pro-card"><h3>Ops Copilot</h3><p>Automate server checks, deploy routines and incident summaries from terminal.</p></div>
  <div className="pro-card"><h3>Personal Agent</h3><p>Daily planning, reminders, memory notes, and contextual follow-up in messaging channels.</p></div>
  <div className="pro-card"><h3>Termux AI Stack</h3><p>Run local-first assistant workflows on Android with low overhead and modular skills.</p></div>
</div>

## ClawLite vs OpenClaw vs nanobot

| Feature | ClawLite | OpenClaw | nanobot |
|---|---:|---:|---:|
| Linux + Termux-first runtime | ✅ | 🟡 | 🟡 |
| Lightweight install | ✅ | 🟡 | ✅ |
| Embedded Gateway (WS + dashboard) | ✅ | ✅ | 🟡 |
| Skill registry + custom skills | ✅ | ✅ | ✅ |
| Offline strategy (Ollama roadmap) | ✅ | 🟡 | 🟡 |
| Community skill ecosystem roadmap | ✅ | ✅ | 🟡 |

## FAQ

### Is ClawLite production-ready?
Core runtime is stable and actively expanding. Gateway and CLI are usable now; advanced orchestration is under fast iteration.

### Can I run it without cloud APIs?
Roadmap includes offline mode with Ollama fallback. Current setup supports online providers first.

### Can I add private skills?
Yes. Add a local skill file, register it, and keep it private in your own repo/fork.
