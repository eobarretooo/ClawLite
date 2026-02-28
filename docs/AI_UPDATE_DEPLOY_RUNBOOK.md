# AI Update & Deploy Runbook (ClawLite)

Guia padrão para qualquer IA executar atualizações de **documentação**, **site oficial** e **site de skills** sem quebrar produção.

---

## 1) Mapa dos repositórios

- **Core / Docs fonte:** `/root/projetos/ClawLite`
- **Site oficial (Vercel):** `/root/projetos/clawlite-site`
- **Site de skills (Vercel):** `/root/projetos/clawlite-skills-site`

Repos remotos:
- `https://github.com/eobarretooo/ClawLite`
- `https://github.com/eobarretooo/clawlite-site`
- `https://github.com/eobarretooo/clawlite-skills`

Produção:
- Site oficial: `https://clawlite-site.vercel.app`
- Docs: `https://eobarretooo.github.io/ClawLite/`
- Skills site: `https://clawlite-skills-site.vercel.app`

---

## 2) Regras obrigatórias para IA

1. **Nunca confundir caminhos:** usar sempre `ClawLite` com C maiúsculo.
2. Fazer mudança **somente no repo alvo**.
3. Rodar validação mínima antes de commit/push.
4. Commits pequenos e com mensagem clara.
5. Não fazer `git push --force` sem instrução explícita.
6. Se houver erro de build/deploy, corrigir e reenviar.

---

## 3) Fluxo: atualizar DOCUMENTAÇÃO (ClawLite)

### 3.1 Arquivos comuns
- `README.md`
- `docs/**`
- `docs-site/**`

### 3.2 Comandos
```bash
cd /root/projetos/ClawLite
git pull --rebase origin main

# editar arquivos...

# validação mínima
python -m pytest tests/ -q --tb=short

# commit + push
git add README.md docs docs-site
git commit -m "docs: atualizar documentação"
git push origin main
```

### 3.3 Resultado esperado
- Workflow de docs publica no GitHub Pages.
- Verificar: `https://eobarretooo.github.io/ClawLite/`

---

## 4) Fluxo: atualizar SITE OFICIAL (clawlite-site)

### 4.1 Comandos
```bash
cd /root/projetos/clawlite-site
git pull --rebase origin main

# editar arquivos...

# validação mínima
npm install
npm run build

# commit + push
git add .
git commit -m "feat(site): atualizar conteúdo/layout"
git push origin main
```

### 4.2 Resultado esperado
- Vercel faz deploy automático.
- Verificar: `https://clawlite-site.vercel.app`

---

## 5) Fluxo: atualizar SITE DAS SKILLS (clawlite-skills-site)

### 5.1 Comandos
```bash
cd /root/projetos/clawlite-skills-site
git pull --rebase origin main

# editar arquivos...

# validação mínima
npm install
npm run build

# commit + push
git add .
git commit -m "docs(skills-site): atualizar catálogo"
git push origin main
```

### 5.2 Resultado esperado
- Vercel faz deploy automático.
- Verificar: `https://clawlite-skills-site.vercel.app`

---

## 6) Checklist final (obrigatório)

Após qualquer deploy, a IA deve reportar:

1. Repo alterado
2. Arquivos alterados
3. Commit hash
4. URL de produção verificada
5. Se houve erro e como foi resolvido

Formato recomendado:

```text
✅ Atualizado: [docs/site/skills-site]
📁 Arquivos: [lista]
🔖 Commit: [hash]
🌐 Produção: [url]
🧪 Validação: [comando + resultado]
```

---

## 7) Troubleshooting rápido

### 7.1 Push rejeitado
```bash
git pull --rebase origin main
git push origin main
```

### 7.2 Build falhou (site)
```bash
npm install
npm run build
```
Corrigir erro e repetir commit/push.

### 7.3 Docs não atualizaram
- Checar workflow no GitHub Actions (`docs.yml` no repo ClawLite).
- Reexecutar job se necessário.

---

## 8) Política de segurança

- Não commitar secrets/tokens/chaves.
- Não alterar branches/release process sem pedido explícito.
- Não mexer em `.venv`, `node_modules` ou artefatos temporários.
