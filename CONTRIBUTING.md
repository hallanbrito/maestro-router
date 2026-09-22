# Como contribuir

Obrigado pelo interesse no Maestro Router. O projeto recebe contribuições que
preservem simplicidade, neutralidade entre provedores, controle explícito de
custos e decisões explicáveis.

## Antes de começar

1. Leia [AGENTS.md](AGENTS.md).
2. Use [docs/INDEX.md](docs/INDEX.md) para localizar as fontes normativas da
   mudança.
3. Verifique as decisões aplicáveis em [docs/decisions/](docs/decisions/).
4. Confirme que a proposta pertence ao escopo atual antes de implementar.

Decisões abertas não autorizam uma implementação por suposição. Mudanças de
produto, arquitetura ou contrato público precisam de aprovação explícita do
Product Owner.

## Ambiente local

Requer Python 3.12.

```shell
python -m venv .venv
```

Ative o ambiente no Linux ou macOS com `source .venv/bin/activate`; no
PowerShell, use `.venv\Scripts\Activate.ps1`. Depois execute:

```shell
python -m pip install -r requirements-dev.txt
```

## Fluxo de contribuição

1. Parta da `master` atualizada e com a árvore limpa.
2. Crie uma branch temática, como `feat/...`, `fix/...`, `docs/...` ou `test/...`.
3. Faça a menor alteração capaz de atender à necessidade aprovada.
4. Adicione ou atualize testes quando houver comportamento executável.
5. Revise o diff completo e confirme que nenhum arquivo fora do escopo mudou.
6. Abra um Draft Pull Request para `master`.

Não inclua segredos, credenciais, preços reais, payloads externos brutos ou
dados pessoais. Testes automatizados não podem realizar chamadas reais a
provedores externos.

## Validação

Com o ambiente virtual ativo:

```shell
python -m pytest -q
python -m pip check
python -m compileall -q src
git diff --check
```

O Pull Request deve informar objetivo, limites, arquivos alterados, validações,
decisões aplicadas e limitações preservadas.

## Licença

Ao contribuir, você concorda que sua contribuição será licenciada sob a
[Apache License 2.0](LICENSE).
