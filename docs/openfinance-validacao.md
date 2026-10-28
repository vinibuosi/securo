# Entrega — Open Finance Brasil no Securo

Data: 28/10/2026. Fork: `vinibuosi/securo`.

PR em rascunho: https://github.com/vinibuosi/securo/pull/2

Branch: `feature/brazilian-openfinance-complete-fixes`, criada sobre o merge
`5696005` da `main`. Código da aplicação validado: `81d9d59`. Os ajustes Docker `f0b98c2` e `d448fe3` foram validados separadamente, sem
alterar a lógica da aplicação. O trabalho anterior foi encontrado intacto,
organizado em sete commits e publicado antes da retomada da validação. Nenhuma
reconstrução foi necessária.

## 1. Correções entregues

**Mercado Pago:** importação do formato documentado de `reservedBalances`,
com `identification`, múltiplos `availableAmounts`, moeda e remuneração.
A conta mostra reservas separadas, instituição, valor, atualização, origem e
classificação. Reconciliação e classificação manuais são persistentes. Relação
incerta, referência a investimento ou dado desatualizado não acrescentam um
segundo valor ao patrimônio. Zero explícito e `hasReservedBalance=false`
tratam resgates. Dados ausentes continuam visíveis como desatualizados.

**Nubank:** agrupamento visual de lotes, com seleção manual persistente quando
não há identificador confiável da Caixinha. A carteira é expansível e não é um
novo ativo valorizado. Todos os lotes, impostos e referências permanecem no
banco. Aquisição prioriza `purchaseDate`; custos e rendimentos incompletos são
sinalizados. A reconciliação de saldo aplicado automaticamente usa confirmação
de identidade, somando os lotes, sem inferir identidade por igualdade de valores.

**XP:** tela de faturas para cartões Pluggy, selecionadas pelo ID estável.
Dívida total, limite disponível, total oficial da fatura, soma dos detalhes,
pagamentos identificados e restante aparecem separadamente. Faturas com o mesmo
vencimento continuam distintas. Compras pendentes, parcelas futuras e compras
integrais sem ciclo confirmado têm seções próprias. A linha integral de uma
compra parcelada não é dividida artificialmente, e representações identificadas
como agregadas não inflam despesas. Lançamentos originais continuam acessíveis
para edição e auditoria. Vínculos tardios de `billId` e correções de vencimento
são atualizados na sincronização.

## 2. Migração e preservação

A revisão **101** adiciona apenas `accounts.provider_metadata`, coluna JSON
anulável. As revisões 099/100 não foram alteradas. Existe somente um head: 101.
A migração não apaga contas, posições, transações, conexões ou credenciais.
Seu downgrade automático é recusado para preservar a reconciliação financeira.

Foram usados PostgreSQL descartável, schemas isolados e somente dados sintéticos.
A cadeia completa foi aplicada a banco novo. A atualização 100 → 101 preservou
exatamente os usuários, workspaces, conexões, credenciais sintéticas, saldo e
configurações do teste. Os testes também verificam a adição em schema existente.

## 3. Validação

| Verificação | Resultado |
|---|---|
| Backend completo, código publicado | 5.924 aprovados; 2 pulados; 1 falha esperada preexistente; nenhuma falha inesperada |
| Frontend completo, código publicado | 1.224 aprovados, em 152 arquivos |
| Bateria direcionada: integração, sincronização, reconciliação, APIs, faturas, contratos Pluggy e migrações | 349 aprovados |
| Ruff | Aprovado |
| Tipagem Python com ty | Aprovada |
| ESLint | Aprovado, código de saída 0 |
| Tipagem TypeScript e build Vite | Aprovados; build do frontend executado também dentro da imagem Docker |
| Alembic | Um head, 101; banco novo e atualização existentes validados |
| Docker backend e frontend | Backend e frontend construídos; correções de CA do proxy e leitura do template nginx verificadas |
| API/Celery dentro da imagem e smoke HTTP do frontend | Aprovados: head 101, carregamento da API e Celery, HTTP 200 da página e arquivos JavaScript do frontend |
| Backup e recuperação sintéticos | `pg_dump`/`pg_restore` para outro banco descartável preservaram contas, conexões e revisão 101 |
| Overrides Compose | PostgreSQL, Redis, ambientes, volumes e comandos dos workers preservados |

Comandos principais:

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/ty check
.venv/bin/alembic heads
POSTGRES_TEST_URL=<PostgreSQL-descartavel> .venv/bin/pytest -q -n 4 --dist loadfile -ra
cd ../frontend
npm test -- --maxWorkers=2 --testTimeout=20000
npm run lint
npm run build
```

O timeout de 20 segundos foi usado nos testes de interface devido à concorrência
no ambiente de dois núcleos. A primeira execução sobrecarregada teve timeouts em
testes preexistentes; a suíte foi repetida. Novas rotas exigiram atualização
explícita do baseline de contratos, mantendo os testes de autenticação e de papel
viewer. As últimas correções foram revalidadas sobre o código já publicado. O build
final detectou que a instalação editável do backend também precisava receber
o segredo opcional de CA do proxy; esse passo foi corrigido, sem desabilitar TLS. O smoke do frontend também
detectou a dependência das permissões locais do template nginx; o Dockerfile
agora fixa sua leitura pelo usuário sem privilégios com `COPY --chmod=644`. O smoke do frontend também
detectou a dependência das permissões locais do template nginx; o Dockerfile
agora fixa a leitura pelo usuário sem privilégios com `COPY --chmod=644`.

Os dois casos pulados são os contratos de `GET /api/dashboard/monthly-trend`
e `GET /api/reports/income-expenses`, porque essa varredura usa SQLite e depende
de `to_char()` do PostgreSQL. A falha esperada já existia no upload de conhecimento
de agentes: `MissingGreenlet` quando o despacho Celery falha e expira o documento.
Esses três casos não foram declarados aprovados nem removidos da suíte.

A interface foi validada com Vitest/Testing Library e pelo servidor HTTP da
imagem. Não houve teste E2E de navegador com conexões bancárias reais.

A validação descrita é do Codex Cloud. Não houve teste com credenciais bancárias
reais nem acesso à instalação Fedora. Não há execução remota de GitHub Actions
registrada no commit consultado; os resultados acima são das execuções locais.

## 4. Demonstrações financeiras

| Cenário sintético | Cálculo | Resultado |
|---|---|---:|
| Mercado Pago, reserva confirmada fora da conta e dos investimentos | 338,79 + 8.720,00 | R$ 9.058,79 |
| Reserva com relação desconhecida/desatualizada | 338,79 + 0 adicional; 8.720,00 exibidos como pendentes | R$ 338,79 confirmado |
| Resgate confirmado entrou na conta | banco 9.058,79 + reserva 0 | R$ 9.058,79 |
| Reserva já incluída na conta ou em investimento | nenhuma segunda inclusão pela reserva | Contada uma vez |
| Uma Caixinha, três lotes | principal 100 + 200 + 300; valores 101 + 202 + 303 | R$ 600 investidos; R$ 606 atuais; R$ 6 de rendimento |
| Saldo aplicado automaticamente, identidade confirmada | banco 938,79 − 600 + lotes 600 | R$ 938,79 |
| XP: compra 1.200 em 12x, parcela oficial 100, pagamento 40 | fatura 100 − 40 | R$ 60 restantes; dívida total continua R$ 1.200 |
| Patrimônio integrado do teste PostgreSQL | conta 338,79 + Cofrinho 8.720 + posições 606 − dívida XP 1.200 | R$ 8.464,79 |

A carteira da Caixinha não recebe uma quarta valorização. Pagamento oficial e
pagamento identificado no feed não são somados entre si. A compra integral de
1.200 permanece em auditoria e não se soma à parcela mensal de 100 quando a
representação agregada pode ser identificada pelos dados disponíveis.

## 5. Limitações e decisões conservadoras

- A Pluggy pode não informar um identificador durável da reserva, a relação
  reserva/saldo ou a correspondência com `/investments`. Sem essa informação,
  mostra-se a reserva e exige-se reconciliação; a falta de identidade impede
  inclusão adicional automática. Mudanças de identificadores sem referência
  durável não permitem garantir identidade após uma reconexão.
- O contrato público de investimentos não garante ID de Caixinha. Nesse caso,
  a seleção manual dos lotes é a alternativa oferecida. Não há agrupamento
  automático por nomes, emissor, taxa ou valores parecidos.
- Investimentos com possível sobreposição ao saldo aplicado ficam pendentes
  até confirmação. Isso pode subestimar temporariamente o patrimônio; os valores
  informados continuam disponíveis para revisão. Dados históricos anteriores
  à correção não são reescritos em massa.
- Vendas, resgates ou custo incompleto podem impedir um retorno confiável.
  Não se calcula TIR ou retorno ponderado pelo tempo a partir de dados parciais.
- A documentação da Pluggy confirma que o XP 602 pode fornecer a compra
  integral sem `billId`, e que faturas abertas e algumas parcelas podem só
  aparecer após fechamento/vencimento. Sem qualquer metadado que identifique
  parcelamento, uma compra legítima não é eliminada por semelhança: o valor pode
  permanecer estimado até haver fatura oficial ou vínculo suficiente.
- Dados de pagamento ausentes não são tratados como zero. Entradas anônimas
  indistinguíveis não produzem um total de pagamento supostamente exato.
  Duplicidades de encargos são conciliadas por referências explícitas; sem
  identidade, a divergência entre detalhes e total oficial permanece visível.
- A leitura de histórico dos cartões Pluggy custa mais requisições, para
  permitir associação tardia de faturas e ajustes antigos.
- As traduções novas estão em português e inglês; os demais idiomas recebem
  texto inglês para as novas funcionalidades, preservando as chaves do projeto.

Fontes verificadas:

- https://v2.docs.pluggy.ai/en/reference/account/accounts-retrieve
- https://docs.pluggy.ai/en/reference/bill/bills-list
- https://v2.docs.pluggy.ai/en/reference/investment/investments-list
- https://docs.pluggy.ai/en/docs/open-finance/investments
- https://docs.pluggy.ai/en/docs/open-finance/considerations-faq

## 6. Instalação Fedora e recuperação

O guia completo, com comandos, está em
[docs/openfinance-brasil.md](https://github.com/vinibuosi/securo/blob/feature/brazilian-openfinance-complete-fixes/docs/openfinance-brasil.md).

Ele inclui backup consistente de PostgreSQL, `.env`, chaves e anexos; builds das
imagens próprias; uso do mesmo projeto e volumes; validação e execução explícita
da migração; início coordenado de backend, frontend, worker e beat; orientações
SELinux; verificação dos serviços; e recuperação com as imagens anteriores.

Arquivos de implantação:

- `docker-compose.openfinance.yml`: sobreposição de build local; preserva banco,
  Redis, ambientes e volumes do arquivo de produção.
- `docker-compose.openfinance.rollback.yml`: usa as imagens anteriores locais;
  inicia o backend sem Alembic, pois a imagem antiga não conhece a revisão 101.

Não foi executado deploy, merge, alteração na instalação real ou remoção de
volumes. A recuperação preserva a revisão 101; não usa downgrade ou `stamp`
para ocultar migrações.

## 7. Checklist após implantação

- [ ] Serviços usam as imagens do mesmo commit personalizado.
- [ ] Alembic tem um head e o banco está em 101.
- [ ] Login, workspaces, contas e conexões existentes foram preservados.
- [ ] Mercado Pago mostra conta e reservas separadas e reconciliação correta.
- [ ] Reserva pendente não gera um segundo valor patrimonial.
- [ ] Nubank permite consolidar e expandir os lotes da Caixinha.
- [ ] Saldo aplicado automaticamente foi conciliado com as posições certas.
- [ ] XP navega por fatura, com pagamentos, restante e diferenças visíveis.
- [ ] Compra integral parcelada não se soma indevidamente à parcela mensal.
- [ ] Parcelas futuras e pendências permanecem separadas.
- [ ] A dívida patrimonial continua sendo a dívida total do cartão.
- [ ] Segunda sincronização não cria registros ou valores duplicados.
- [ ] Outros cartões, posições XP, anexos e processos Celery funcionam.

## 8. Arquivos alterados e criados

- `.gitignore`
- `backend/Dockerfile`
- `backend/alembic/versions/101_openfinance_account_metadata.py`
- `backend/app/api/accounts.py`
- `backend/app/api/asset_groups.py`
- `backend/app/models/account.py`
- `backend/app/providers/base.py`
- `backend/app/providers/pluggy.py`
- `backend/app/schemas/account.py`
- `backend/app/schemas/asset.py`
- `backend/app/schemas/asset_group.py`
- `backend/app/services/account_service.py`
- `backend/app/services/asset_group_service.py`
- `backend/app/services/asset_service.py`
- `backend/app/services/card_charge_reconciliation.py`
- `backend/app/services/card_statement_service.py`
- `backend/app/services/connection_service.py`
- `backend/app/services/reserve_service.py`
- `backend/app/services/transaction_service.py`
- `backend/tests/api_contract/baseline.json`
- `backend/tests/test_connection_service.py`
- `backend/tests/test_openfinance_api.py`
- `backend/tests/test_openfinance_migration.py`
- `backend/tests/test_openfinance_positions.py`
- `backend/tests/test_openfinance_postgres.py`
- `backend/tests/test_openfinance_reserves.py`
- `backend/tests/test_openfinance_statements.py`
- `docker-compose.openfinance.rollback.yml`
- `docker-compose.openfinance.yml`
- `docs/openfinance-brasil.md`
- `frontend/Dockerfile`
- `frontend/src/components/auto-investment-reconciliation.tsx`
- `frontend/src/components/card-statements.test.tsx`
- `frontend/src/components/card-statements.tsx`
- `frontend/src/components/consolidate-positions.test.tsx`
- `frontend/src/components/consolidate-positions.tsx`
- `frontend/src/components/position-provenance.tsx`
- `frontend/src/components/reserved-balances.test.tsx`
- `frontend/src/components/reserved-balances.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/position-group.test.ts`
- `frontend/src/lib/position-group.ts`
- `frontend/src/locales/cs.json`
- `frontend/src/locales/de.json`
- `frontend/src/locales/el.json`
- `frontend/src/locales/en.json`
- `frontend/src/locales/es.json`
- `frontend/src/locales/fr.json`
- `frontend/src/locales/hi.json`
- `frontend/src/locales/hu.json`
- `frontend/src/locales/it.json`
- `frontend/src/locales/ja.json`
- `frontend/src/locales/nl.json`
- `frontend/src/locales/pl.json`
- `frontend/src/locales/pt-BR.json`
- `frontend/src/locales/pt-PT.json`
- `frontend/src/locales/ru.json`
- `frontend/src/locales/sk.json`
- `frontend/src/locales/uk.json`
- `frontend/src/pages/account-detail.tsx`
- `frontend/src/pages/assets.tsx`
- `frontend/src/types/index.ts`

- `docs/openfinance-validacao.md`
