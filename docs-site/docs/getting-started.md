# ⚡ Início Rápido

Rode o ClawLite em 5 minutos com fluxo guiado.

:::tip
O quickstart padrão é interativo (estilo OpenClaw). Setup manual é opcional.
:::

## 1) Instalar

Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

Termux (proot Ubuntu):

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/setup_termux_proot.sh | bash
```

## 2) Diagnóstico

```bash
clawlite doctor
```

## 3) Onboarding guiado

```bash
clawlite onboarding
```

## 4) Status + start

```bash
clawlite status
clawlite start --host 0.0.0.0 --port 8787
```

➡️ Próxima página: [Instalação](/instalacao)
