# Open Finance Brasil: reservas, posições e faturas

Esta branch parte de `main` no merge `5696005`. Não muda credenciais Pluggy,
chaves, conexão de produção, banco do usuário ou revisões Alembic 099/100.
A migração 101 adiciona somente `accounts.provider_metadata`, JSON anulável.
Não existe downgrade automático dessa informação financeira.

## Regras financeiras

### Mercado Pago e outras reservas

O contrato documentado é `bankData.hasReservedBalance` e
`reservedBalances[].{name,identification,availableAmounts[]}`. Cada valor tem
`amount`, `currencyCode` e pode ter `remuneration`. Todos esses detalhes são
preservados; moedas diferentes nunca são somadas. Formatos planos de conectores
(`id`, `balance`/`amount`) também são aceitos. O nome não é identidade.

A tela da conta mostra nome, instituição, moeda, valor, última atualização,
origem e classificação. É possível classificar manualmente Cofrinho, reserva
genérica, saldo bloqueado ou bloqueio judicial. Uma classificação desconhecida
não é inferida pelo nome. Identificações repetidas/ausentes são ambíguas.

| Relação confirmada | Conta | Ativo adicional | Patrimônio do exemplo |
|---|---:|---:|---:|
| Desconhecida | 338,79 | 0,00 | 338,79, com reserva 8.720,00 pendente |
| Fora da conta e dos investimentos | 338,79 | 8.720,00 | 9.058,79 |
| Já incluída no saldo bancário | saldo original da API | 0,00 | saldo original da API |
| Representada em `/investments` | 338,79 | 0,00 pela reserva | 338,79 + investimento contado uma vez |

A confirmação “fora da conta e dos investimentos” cria um ativo valorizado
`source=pluggy_reserve`, separado do importador de posições. Não cria outro
saldo bancário. Um vínculo explícito `investmentId`, se o conector o expuser,
impede a segunda valorização, inclusive se chegar numa sincronização posterior.
A API pública não garante esse vínculo: nesse caso, use a confirmação manual.
Sem identificação estável ou valor válido, a inclusão adicional fica bloqueada.

Um zero explícito zera a valorização. Campo ausente, resposta vazia ou inválida
não prova resgate: mantém o último valor válido e sinaliza atualização pendente.
A reserva desatualizada continua visível, mas seu valor adicional patrimonial fica
zero até uma nova leitura válida; isso evita somá-la a um possível resgate que já
entrou na conta. `hasReservedBalance=false` confirma ausência de reservas ativas.
A identidade usa a identificação da reserva e a identidade durável da conta
quando disponível; transferNumber é somente usado como hash, nunca armazenado
integralmente. Sem identificador durável fornecido pela instituição, não é
possível garantir a correspondência após uma reconexão que substitua os IDs.
Não desconecte bancos para atualizar esta versão.

### Nubank / Caixinhas

Uma posição continua sendo um `Asset`, com valores, impostos, metadados e
referências próprios. A carteira (`AssetGroup`) é só uma apresentação: não recebe
um `AssetValue` e não é somada novamente ao patrimônio.

Em **Ativos → Consolidar Caixinha / posições**, selecione explicitamente os lotes
que pertencem à mesma Caixinha e salve seu nome. A seleção é atômica, persistente,
limitada ao mesmo workspace, conexão e moeda. A sincronização preserva carteiras
manuais. A carteira pode ser expandida, e cada posição mantém seu detalhamento.
Não há agrupamento automático por emissor, nomes, taxa ou igualdade de valores.
O contrato público de `/investments` não garante um ID de Caixinha: a alternativa
normal é a seleção manual. Um `caixinhaId` semanticamente explícito, se presente
em dados enriquecidos do conector, também é aceito; não se presume que o Nubank
forneça essa extensão.

Exemplo: aportes 100 + 200 + 300 = **600**. Valores atuais fictícios 101 + 202 +
303 = **606**. Diferença = **6**, percentual sobre custo = 6/600 = **1%**,
nunca a soma dos percentuais dos lotes. `purchaseDate` precede `issueDate`.
Resgates parciais, movimentações de venda e custo ausente tornam o rendimento
incompleto; o sistema não chama aportes de lucro nem inventa retorno realizado.
O rendimento mostrado é diferença entre valor e custo conhecido das posições,
não uma TIR ou rentabilidade ponderada pelo tempo.

`automaticallyInvestedBalance` não é reconciliado por semelhança de valores.
Se a conta informa aplicação automática e a relação com as posições é incerta,
os valores informados das posições são preservados nos metadados e exibidos,
mas seu valor adicional patrimonial fica zero, marcado como pendente. Na conta,
use **Saldo aplicado automaticamente** para confirmar as posições já incluídas
no banco e os investimentos independentes. Salvar executa uma sincronização.
Lotes confirmados são somados, e a dedução do banco é limitada à parcela
aplicada e ao valor efetivamente contado. Exemplo: banco 938,79 incluindo 600;
três lotes confirmados 100+200+300; total = (938,79−600)+600 = **938,79**.
Posições de outra conta explicitamente identificada não participam dessa dedução.
Essa política pode subestimar temporariamente o patrimônio enquanto houver
relações desconhecidas; a interface explicita a pendência para correção.

### Faturas XP e demais cartões Pluggy

A tela de cartões Pluggy abre em **Faturas mensais**. A seleção usa o UUID da
fatura, preservado quando seu vencimento muda. Duas faturas com a mesma data
continuam distintas. **Ver e editar lançamentos da conta** mantém a interface
anterior para edição/auditoria e cartões de outros provedores.

- Dívida total e limite disponível são separados dos totais mensais.
- O total oficial de `/bills` é a referência, com soma dos detalhes e divergência.
- Fechamento oficial, vencimento, pagamentos identificados, saldo restante e
  estado da fatura aparecem separados; ausência de pagamentos não significa zero.
- Pagamentos oficiais são a fonte principal; transações identificadas como
  pagamentos são fallback e não são adicionadas aos pagamentos oficiais.
- Estornos reduzem os detalhes. Encargos com referência explícita duplicada
  mantêm ambas as fontes brutas, mas só uma participação contábil.
- Transações sem `billId` podem ser estimadas pelo fechamento/vencimento
  configurados. Relações ambíguas ficam separadas. Valores de faturas não
  substituem `accounts.balance` nos cálculos de patrimônio.
- Parcelas futuras e compras pendentes têm seções próprias. Apenas parcelas
  efetivamente informadas são mostradas: não existe divisão artificial de 1.200/12.
- Compra integral parcelada sem fatura e metadados incompletos ficam numa seção
  de auditoria, fora das estimativas mensais. Um vínculo explícito da família da
  compra confirma representações agregadas/parcelas. Nome e valor semelhantes
  não eliminam compras legítimas. O raw original é preservado nas atualizações. Representações integrais
  não resolvidas também ficam fora do resultado de despesas, mantendo a linha
  original e respeitando uma eventual escolha manual de inclusão/exclusão.
- A leitura de transações de cartões Pluggy cobre o histórico disponível a cada
  sincronização para capturar `billId` tardio; isso custa mais requisições que a
  janela incremental de contas bancárias. Paginação com falha mantém dados válidos.

Exemplo: dívida total **1.200**, fatura de outubro **100**, pagamento identificado
**40**, restante **60**. Novembro tem outra parcela de **100**. A representação
agregada de **1.200** permanece visível, fora da soma da primeira parcela.
Pagamentos oficiais repetidos com o mesmo ID contam uma vez. Entradas anônimas
indistinguíveis não geram um total de pagamento supostamente exato.

## Limitações do provedor

As fontes abaixo foram verificadas em 28/10/2026. A API pode omitir identificação
de reserva, relação entre reserva e saldo, ID de Caixinha, transações de resgate,
parcelas futuras ou pagamentos. Não se inventam essas informações. No XP 602,
a representação integral parcelada pode não ter `billId`. Faturas abertas podem
não estar disponíveis até fechamento ou vencimento, e os próprios lançamentos
podem só surgir quando a fatura aparece. Estimativa não é fatura oficial.

- [Contas](https://v2.docs.pluggy.ai/en/reference/account/accounts-retrieve)
- [Faturas](https://docs.pluggy.ai/en/reference/bill/bills-list)
- [Investimentos](https://v2.docs.pluggy.ai/en/reference/investment/investments-list)
- [Caixinhas/CDBs](https://docs.pluggy.ai/en/docs/open-finance/investments)
- [Limitações Open Finance / XP 602](https://docs.pluggy.ai/en/docs/open-finance/considerations-faq)

## Atualização no Fedora com Docker Compose

Não há deploy automático. Execute somente depois de revisar o PR. Mantenha o
mesmo diretório de produção, o mesmo `.env`, os mesmos arquivos em `secrets/`,
o mesmo projeto Compose e os mesmos nomes de volumes. Não publique backups ou
configurações renderizadas: eles podem conter segredos.

### 1. Identificar e registrar a instalação

```bash
docker compose ls
docker compose -f docker-compose.prod.yml ps
# Confira o nome do projeto EXISTENTE; não crie um projeto novo.
export SECURO_PROJECT=securo
prod() { docker compose --project-name "$SECURO_PROJECT" --env-file .env -f docker-compose.prod.yml "$@"; }
custom() { docker compose --project-name "$SECURO_PROJECT" --env-file .env -f docker-compose.prod.yml -f docker-compose.openfinance.yml "$@"; }
# Registre o commit e os IDs exatos das imagens atuais para recuperação.
git rev-parse HEAD
prod images
prod ps -q | xargs -r docker inspect --format '{{.Name}} {{.Image}}'
# Liste os volumes que já estão associados ao banco e aos anexos.
prod ps -q db backend | xargs -r docker inspect --format '{{.Name}} {{range .Mounts}}{{.Name}}:{{.Destination}} {{end}}'
```

Se a instalação usa opções Compose adicionais, nomes externos de volume,
arquivo de produção modificado ou variáveis para PostgreSQL/Redis externos,
reutilize-os nos dois helpers; o override não altera `db`, `redis`, ambientes,
volumes ou portas. Não substitua personalizações pelo arquivo padrão.

### 2. Backup consistente antes da atualização

Escolha um diretório fora do checkout e mantenha permissões privadas. Pare
somente os processos da aplicação para impedir escritas durante o backup;
PostgreSQL e Redis continuam ativos. Inclua `mcp-server` se o perfil agents
estiver ativo. Guarde também o ID das imagens e o commit anterior nesse diretório.

```bash
export SECURO_BACKUP_DIR="/caminho/privado/securo-backup-$(date +%Y%m%d-%H%M%S)"
umask 077
mkdir -p "$SECURO_BACKUP_DIR"
cp -p .env docker-compose.prod.yml "$SECURO_BACKUP_DIR/"
[ ! -d secrets ] || cp -a secrets "$SECURO_BACKUP_DIR/"
git rev-parse HEAD > "$SECURO_BACKUP_DIR/previous-commit.txt"
prod ps -q | xargs -r docker inspect --format '{{.Name}} {{.Image}}' > "$SECURO_BACKUP_DIR/previous-images.txt"
prod stop frontend backend celery-worker celery-beat
# Se estiver ativo: prod --profile agents stop mcp-server
prod exec -T db pg_dump -U postgres -d securo -Fc > "$SECURO_BACKUP_DIR/securo.dump"
test -s "$SECURO_BACKUP_DIR/securo.dump"
prod exec -T db pg_restore --list < "$SECURO_BACKUP_DIR/securo.dump" > "$SECURO_BACKUP_DIR/dump-contents.txt"
# Copia anexos, base de conhecimento e modelos do volume montado no backend.
# O container efêmero usa os MESMOS volumes e não inicia dependências.
prod run --rm --no-deps --entrypoint sh backend -c 'tar -C /app/data -czf - .' > "$SECURO_BACKUP_DIR/app-data.tar.gz"
tar -tzf "$SECURO_BACKUP_DIR/app-data.tar.gz" > "$SECURO_BACKUP_DIR/app-data-contents.txt"
```

Adapte usuário/database apenas se sua configuração os alterou. Com PostgreSQL
externo, use `pg_dump` contra aquele banco, sem colocar senhas no histórico.
Antes de continuar, restaure o dump numa instância descartável com pgvector e
confirme que ele abre; listar o dump não comprova sua restauração. Preserve a
`SECRET_KEY` e quaisquer arquivos de criptografia: trocar a chave pode tornar
as conexões bancárias ilegíveis. Não há necessidade de credenciais Pluggy novas.

### 3. Obter o código e construir imagens locais

```bash
git status --short
# Resolva mudanças locais antes de trocar a branch; não use reset destrutivo.
git fetch origin feature/brazilian-openfinance-complete-fixes
git switch feature/brazilian-openfinance-complete-fixes
# Ou use o commit exato revisado no PR.
export SECURO_CUSTOM_TAG="$(git rev-parse --short HEAD)"
custom config --quiet
custom build backend frontend
```

Backend, Celery worker, Celery beat e MCP usam a mesma imagem personalizada.
Frontend tem build próprio. O override usa `pull_policy: never`, evitando baixar
uma imagem upstream por engano. Não edite o `.env` para remover ou trocar chaves.
No Fedora com SELinux, preserve os rótulos dos volumes existentes; se um bind
mount personalizado precisar de `:Z`, aplique-o somente ao caminho necessário,
sem desativar o SELinux. Backups também precisam manter os contextos adequados.

Em redes com proxy corporativo, os Dockerfiles aceitam o segredo BuildKit
opcional `proxy_ca` (bundle público de CAs), sem incluí-lo nas camadas da imagem.
Em uma rede comum, `custom build backend frontend` é suficiente. Não desabilite TLS.

### 4. Verificar e executar a migração

Os comandos `heads` e `current` não mudam o banco. O primeiro deve mostrar
somente `101`; o banco existente esperado é `100`.

```bash
custom run --rm --no-deps --entrypoint alembic backend heads
custom run --rm --no-deps --entrypoint alembic backend current
# Depois de validar o backup e a revisão de origem:
custom run --rm --no-deps --entrypoint alembic backend upgrade head
custom run --rm --no-deps --entrypoint alembic backend current
# Deve estar em 101. Só então iniciar os processos.
custom up -d --no-deps backend frontend celery-worker celery-beat
# Se agents estava ativo: custom --profile agents up -d --no-deps mcp-server
custom ps
custom logs --tail=100 backend celery-worker celery-beat frontend
```

Não altere a imagem PostgreSQL, não recrie Redis e não remova volumes para aplicar
esta atualização. O backend também executa `alembic upgrade head` no startup,
mas a execução explícita acima evita que workers novos iniciem antes da migração.

### 5. Checklist após implantação

- [ ] Todos os serviços usam as imagens do mesmo commit personalizado.
- [ ] Alembic está em 101, com um único head; não houve erro de migração.
- [ ] Login, workspaces, contas e saldos anteriores continuam disponíveis.
- [ ] Conexões Pluggy existentes permanecem vinculadas; não reconecte sem necessidade.
- [ ] Mercado Pago mostra 338,79 da conta e 8.720,00 da reserva separadamente.
- [ ] Confirme no banco se os 8.720 estão dentro/fora da conta e se já são investimento.
- [ ] Reserva pendente não aumenta o patrimônio; confirme sua classificação.
- [ ] Nubank permite selecionar e expandir a Caixinha, mantendo cada aplicação.
- [ ] Se houver saldo aplicado automaticamente, conclua a reconciliação dos lotes.
- [ ] Faturas XP navegam por ciclo; total oficial, pagamentos e restante fazem sentido.
- [ ] Compra integral parcelada não foi adicionada à primeira parcela.
- [ ] Parcelas futuras aparecem separadas; ausência de dados é sinalizada.
- [ ] Dívida patrimonial do cartão continua sendo a dívida total da instituição.
- [ ] Uma segunda sincronização não cria ativos, posições, reservas ou faturas extras.
- [ ] XP investimentos, outros cartões, anexos, importações e Celery continuam funcionando.

### 6. Recuperação

Se o build falhar, mantenha as imagens anteriores; nada mudou no banco. Se a
migração falhar, ela é transacional no PostgreSQL: examine `current` e os logs
antes de repetir, sem apagar tabelas nem forçar `stamp`.

Se a aplicação falhar após a revisão 101, pare os processos da aplicação e
retorne às imagens/commit anteriores registrados, usando exatamente os mesmos
volumes e `.env`. A coluna JSON adicional é anulável; a versão anterior pode
operar com ela sem executar downgrade. Não use tags flutuantes `latest` para
reverter: use os IDs/digests guardados. Um override de recuperação pode apontar
backend/worker/beat/MCP para o mesmo ID anterior e frontend para seu ID anterior.

O overlay `docker-compose.openfinance.rollback.yml` evita um detalhe importante:
a imagem antiga não conhece o identificador Alembic 101. Por isso, na recuperação
o backend inicia diretamente o Uvicorn, sem `alembic upgrade` e sem alterar a
revisão do banco. Não tente `stamp 100` para contornar essa diferença.

```bash
custom stop frontend backend celery-worker celery-beat
# Acrescente mcp-server se ele estava ativo.
# Use os IDs EXATOS registrados no backup para criar tags locais estáveis:
docker tag sha256:ID_ANTERIOR_BACKEND securo-recovery-backend:before-openfinance
docker tag sha256:ID_ANTERIOR_FRONTEND securo-recovery-frontend:before-openfinance
export SECURO_RECOVERY_BACKEND_IMAGE=securo-recovery-backend:before-openfinance
export SECURO_RECOVERY_FRONTEND_IMAGE=securo-recovery-frontend:before-openfinance
recovery() { docker compose --project-name "$SECURO_PROJECT" --env-file .env -f docker-compose.prod.yml -f docker-compose.openfinance.rollback.yml "$@"; }
recovery config --quiet
recovery up -d --no-deps backend frontend celery-worker celery-beat
# Se estava ativo: recovery --profile agents up -d --no-deps mcp-server
recovery logs --tail=100 backend celery-worker celery-beat
```

Não altere `db` nem `redis` nesse procedimento. Mantenha esses overlays acessíveis
se decidir também trocar o checkout de código; as imagens, não o checkout,
contêm o código executado nos containers de produção.

Se houver necessidade de recuperação de dados, faça primeiro outro dump da
situação atual, restaure o backup numa instância PostgreSQL **nova e separada**,
valide contas, conexões e migrações, e só então altere a configuração da aplicação
para essa instância. Preserve o banco original para investigação. Restaure os
anexos do mesmo ponto no tempo e a mesma chave. Nunca apague o volume original
nem execute downgrade destrutivo.

## Validação de desenvolvimento

Os testes novos ficam em `backend/tests/test_openfinance_*.py` e nos componentes
React e bibliotecas correspondentes. Integração PostgreSQL usa
`POSTGRES_TEST_URL` e schemas descartáveis, apenas com dados sintéticos.
A suíte de contratos inclui autenticação, papel viewer e IDs desconhecidos dos
novos endpoints. Resultados reais e eventuais verificações não concluídas são
registrados no relatório de entrega do PR.
