# 🧰 Instalação

Passo a passo para Linux e Termux (via proot Ubuntu).

## Linux (genérico)

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip curl git
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/install.sh | bash
```

## Termux (somente proot Ubuntu)

```bash
curl -fsSL https://raw.githubusercontent.com/eobarretooo/ClawLite/main/scripts/setup_termux_proot.sh | bash
clawlitex status
clawlitex onboarding
clawlitex start
```

:::warning
No repositório oficial, não documentamos instalação nativa no Termux. Use apenas proot Ubuntu.
:::

➡️ Próxima página: [Onboarding](/onboarding)
