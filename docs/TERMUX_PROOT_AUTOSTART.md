# Termux + proot: autonomia 24/7 sem systemd

No Termux com Ubuntu proot não existe `systemd` no modelo clássico.  
Para autonomia real do ClawLite, o caminho recomendado é:

1. `supervisord` dentro do proot (mantém o gateway vivo com `autorestart`)
2. `Termux:Boot` no Android (religa o supervisor após reboot)

---

## Pré-requisitos

No Termux host:

```bash
pkg update -y
pkg install -y proot-distro termux-api
```

No Android:

- app **Termux:Boot** instalado
- otimizações agressivas de bateria desativadas para o Termux

No proot:

- ClawLite já instalado (via `clawlitex setup`)

---

## Setup passo a passo

1) Instale/atualize o ClawLite no proot:

```bash
clawlitex setup
```

2) Configure autostart 24/7:

```bash
clawlitex autostart install
```

Isso cria:

- `supervisord` e `supervisorctl` no Ubuntu proot
- config: `/root/.clawlite/supervisord.conf`
- config do cliente: `/root/.clawlite/supervisorctl.conf`
- start script: `/root/.clawlite/bin/clawlite-supervised-start.sh`
- boot script Termux: `~/.termux/boot/clawlite-supervisord.sh`
  - usa `proot` direto (sem `proot-distro login`) para evitar bloqueios no boot
  - executa em background com `nohup` e log em `/tmp/clawlite-boot.log`
  - ignora execução quando detecta sessão `nested proot` (evita falso erro em testes dentro do próprio proot)

3) Verifique status:

```bash
clawlitex autostart status
```

4) Teste de sobrevivência:

- reinicie o aparelho
- abra Termux e rode:

```bash
clawlitex autostart status
clawlitex status
```

---

## Operação

Logs no proot:

- `/root/.clawlite/logs/supervisord.log`
- `/root/.clawlite/logs/clawlite.out.log`
- `/root/.clawlite/logs/clawlite.err.log`

Checagem rápida de saúde:

```bash
clawlitex status
proot-distro login ubuntu -- /bin/bash -lc "supervisorctl -s http://127.0.0.1:9001 status"
```

---

## Remover autostart

```bash
clawlitex autostart remove
```

Isso:

- para/shutdown do `supervisord` no proot
- remove `~/.termux/boot/clawlite-supervisord.sh`

---

## Checklist objetivo de autonomia (Termux + proot)

- [ ] `clawlitex autostart status` mostra `supervisord pid: RUNNING`
- [ ] `supervisorctl ... status` mostra programa `clawlite` em `RUNNING`
- [ ] cron envia mensagem sem trigger manual (`clawlite cron`)
- [ ] memória persiste após restart (`~/.clawlite/*.db`)
- [ ] pelo menos 1 canal sempre conectado (`/api/channels/status`)
- [ ] execução de ferramentas habilitada (`security.allow_shell_exec=true`)
- [ ] subagentes ativos (`clawlite agents list`)
- [ ] após reboot do Android, gateway volta sem intervenção manual
