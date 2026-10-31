# Aplicação de autenticação

Esta aplicação cuida do cadastro, entrada, recuperação de senha, troca de e-mail, sessões em dispositivos e registros de segurança de uma conta.

## Comece por aqui: escolha o ambiente

Você não precisa configurar a nuvem para começar a programar. Escolha uma das opções:

| Ambiente | Banco e cache | E-mail e tarefas | Servidor | Quando usar |
| --- | --- | --- | --- | --- |
| Simples | SQLite e memória do processo | E-mail no terminal; tarefa executada na própria requisição | Django com recarga automática | Desenvolver telas e regras rapidamente |
| Integrado | PostgreSQL e Redis reais | Worker Celery e Beat; e-mail no log do worker por padrão | Django com recarga automática | Testar bloqueios, sessões, filas e manutenção com serviços semelhantes aos de produção |
| Produção/homologação | PostgreSQL e Redis persistentes | Worker Celery, Beat único e SMTP | Gunicorn atrás de Nginx com HTTPS | Validar a implantação em um servidor real |

Os ambientes Docker têm nomes e volumes separados. O banco do ambiente integrado não é o banco de produção. As senhas e os endereços também devem ser diferentes.

**Limite importante:** os arquivos de implantação foram preparados, mas Docker, certificados, SMTP e infraestrutura de nuvem não foram executados ou validados nesta entrega. “Produção” é o perfil de configuração, não uma garantia de disponibilidade ou aprovação de segurança. Comece por homologação com contas de teste.

## 1. Desenvolvimento simples, sem Docker

Instale Python 3.14 e PDM. Na pasta do projeto:

```bash
pdm install -G dev
cp .env.example .env
pdm run migrate
pdm run dev
```

- `install` instala as dependências fixadas no projeto.
- `migrate` cria ou atualiza as tabelas do SQLite.
- `dev` inicia o servidor local e recarrega o código quando você salva alterações.
- O SQLite fica em `db.sqlite3`. Parar o servidor não apaga esse arquivo.
- E-mails e códigos aparecem no terminal. Não há provedor de e-mail, Redis ou worker externo nesse modo.
- O cache em memória é separado por processo. Esse modo não demonstra o comportamento de vários servidores concorrentes.
- Uma chave pública de desenvolvimento é usada quando `SECRET_KEY` fica vazia. Nunca utilize essa chave nem esse modo em um servidor público.

Abra **http://127.0.0.1:8000/manual/** para testar os fluxos. O painel administrativo fica em `/admin/`; crie seu acesso com `pdm run python manage.py createsuperuser`. Esse usuário administrativo é uma conta da aplicação, não o administrador do PostgreSQL.

## 2. Desenvolvimento simples, com Docker

Instale Docker com o plugin Docker Compose v2. Os atalhos abaixo também exigem PDM instalado no computador.

```bash
cp .env.dev.example .env.dev
pdm run dev:up
pdm run dev:logs
```

Abra **http://127.0.0.1:8000/manual/**. O código é compartilhado com o contêiner; não precisa reconstruir a imagem para cada alteração em Python, HTML ou JavaScript. Mudanças nas dependências ou no Dockerfile exigem novamente `pdm run dev:up`.

Para criar o administrador e parar o ambiente:

```bash
pdm run compose:dev exec app python manage.py createsuperuser
pdm run dev:down
```

Esse ambiente usa o mesmo `db.sqlite3` da pasta compartilhada. Não execute migrações de dois ambientes sobre esse arquivo ao mesmo tempo. No Linux, se aparecer erro de permissão, preencha `LOCAL_UID` e `LOCAL_GID` em `.env.dev` com os números retornados por `id -u` e `id -g`.

Sem PDM, o comando equivalente para iniciar é:

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d --build
```

## 3. Desenvolvimento integrado: PostgreSQL, Redis e Celery

```bash
cp .env.integrated.example .env.integrated
pdm run secret
```

O comando `secret` gera um valor aleatório. **Ele não altera nenhum arquivo.** Execute-o separadamente para cada segredo e preencha `.env.integrated`:

| Variável | O que preencher |
| --- | --- |
| `SECRET_KEY` | Uma chave aleatória exclusiva deste ambiente |
| `POSTGRES_PASSWORD` | Senha do administrador do PostgreSQL local |
| `APP_DB_PASSWORD` | Outra senha, exclusiva do usuário da aplicação |
| `REDIS_PASSWORD` | Outra senha, exclusiva do Redis |
| `DATABASE_URL` | `postgresql://template_auth:SENHA_APP@db:5432/template_auth`, substituindo `SENHA_APP` pelo mesmo valor de `APP_DB_PASSWORD` |
| `REDIS_URL` | `redis://:SENHA_REDIS@redis:6379/0`, substituindo `SENHA_REDIS` pelo mesmo valor de `REDIS_PASSWORD` |

Os nomes `db` e `redis` são endereços internos do Docker, não endereços para programas executados diretamente no computador. `APP_DB_USER` e `POSTGRES_DB` valem `template_auth` por padrão; se mudá-los, ajuste também a URL. O usuário da aplicação não é superusuário do PostgreSQL.

Depois de preencher:

```bash
pdm run full:up
pdm run full:logs
pdm run compose:full exec app python manage.py createsuperuser
```

- A aplicação continua em **http://127.0.0.1:8000/manual/**, com cookies próprios para HTTP local e `DEBUG` ativo.
- Um serviço executa as migrações antes de liberar a aplicação, o worker e o Beat.
- O worker envia os e-mails; com o backend padrão de console, veja os códigos nos logs do **worker**, não nos logs da aplicação.
- O Beat agenda a manutenção diária. Não inicie uma segunda cópia do Beat para esse mesmo banco/fila.
- O Django recarrega o código automaticamente. Para alterações nas tarefas Celery, reinicie os processos: `pdm run compose:full restart worker beat`.
- Para trocar a porta, altere `APP_PORT`. As origens CSRF locais desse perfil acompanham a porta escolhida.
- Use `pdm run full:down` para parar sem apagar os volumes.

Esse perfil não deve ser publicado na internet. Para envio real de e-mail em homologação, configure SMTP como explicado adiante; não use endereços de pessoas reais em testes de códigos ou limites.

## 4. Como aplicar variáveis e proteger senhas

Cada atalho escolhe explicitamente seu arquivo: `.env.dev`, `.env.integrated` ou `.env.prod`. O Compose lê esse arquivo e injeta apenas as variáveis declaradas em cada serviço. A aplicação em produção não carrega `.env` por conta própria. Fora do Docker, o modo simples lê apenas o `.env` da raiz.

- Arquivos `.example` contêm modelos, não credenciais utilizáveis.
- Não coloque chaves privadas, senhas ou arquivos `.env` no Git. Os arquivos de ambiente, certificados e backups estão ignorados; o contexto da imagem também exclui arquivos `.env`.
- Para o servidor, use uma pasta acessível somente à equipe responsável e proteja o arquivo: `chmod 600 .env.prod`.
- Valores hexadecimais gerados por `pdm run secret` evitam problemas com `$`, `#`, espaços e caracteres especiais em URLs.
- Para senhas que contêm `@`, `:`, `/`, `%` ou outros caracteres reservados, faça a codificação de URL **somente ao montar a URL**. A senha original continua nas variáveis de senha. Não coloque a senha em serviços públicos de codificação.
- Não copie a saída de `docker inspect` ou `docker compose config` para chamados ou conversas: ela pode conter segredos.
- Não mantenha credenciais de produção na pasta compartilhada pelo Docker de desenvolvimento. O compartilhamento do código permite que o contêiner de desenvolvimento leia arquivos dessa pasta.
- Alterar uma variável no arquivo não reconfigura um contêiner já em execução. Use novamente o comando `up` correspondente para recriá-lo.

**Atenção ao PostgreSQL:** as variáveis de inicialização e o script de criação do usuário só são aplicados na primeira criação de um volume vazio. Alterar `POSTGRES_PASSWORD` ou `APP_DB_PASSWORD` não troca a senha de um banco existente. Para uma rotação, altere a senha no PostgreSQL, atualize as URLs e recrie os clientes. Faça backup antes; não apague o volume para trocar senha.

## 5. Configuração de e-mail e senha de aplicativo

No integrado, troque `EMAIL_BACKEND` para `django.core.mail.backends.smtp.EmailBackend` para testar entrega real. Em produção, o Compose já utiliza SMTP. Preencha:

| Variável | Exemplo de significado |
| --- | --- |
| `EMAIL_HOST` | Servidor SMTP indicado pelo provedor |
| `EMAIL_PORT` | Geralmente `587` para STARTTLS ou `465` para TLS desde a conexão |
| `EMAIL_HOST_USER` | Usuário SMTP; pode ser diferente do endereço remetente |
| `EMAIL_HOST_PASSWORD` | Credencial SMTP ou senha de aplicativo emitida pelo provedor |
| `DEFAULT_FROM_EMAIL` | Endereço remetente autorizado/verificado no provedor |
| `EMAIL_USE_TLS` | `true` para STARTTLS; use `false` ao selecionar TLS direto |
| `EMAIL_USE_SSL` | `true` para TLS direto; use `false` com STARTTLS |

Não habilite `EMAIL_USE_TLS` e `EMAIL_USE_SSL` ao mesmo tempo. O timeout de dez segundos vale por espera de rede; não é um prazo total para a entrega.

**Google/Gmail:** quando permitido pela conta, habilite a verificação em duas etapas e gere uma senha de aplicativo no painel de segurança. Use essa senha no lugar da senha normal da conta. Políticas de organizações podem impedir esse recurso. Este cliente SMTP usa usuário/senha; ele não implementa OAuth para provedores que exigem esse método.

**Amazon SES:** crie credenciais **SMTP** para a região escolhida; não use a senha do console AWS nem uma chave de API comum como se fosse senha SMTP. Verifique o remetente/domínio, configure DKIM e revise SPF/DMARC. No sandbox, existem restrições de destinatários e de envio; solicite a liberação adequada antes de enviar a pessoas reais.

Depois de alterar credenciais, recrie aplicação e worker com o atalho `up` do ambiente. Valide recebimento, pasta de spam e logs do worker. Uma tarefa aceita pela fila pode falhar depois da resposta HTTP; a pessoa poderá precisar solicitar outro código.

## 6. Produção ou homologação em servidor próprio

Use um domínio de homologação antes de atender pessoas reais. O perfil usa `DEBUG=False`, cookies seguros, redirecionamento HTTPS, HSTS de um ano, Gunicorn, Nginx, PostgreSQL, Redis autenticado, worker e Beat.

```bash
cp .env.prod.example .env.prod
chmod 600 .env.prod
mkdir -p deploy/tls
```

Preencha os segredos como no integrado, mas **gere novos valores**. Configure também:

```dotenv
ALLOWED_HOSTS=api.seudominio.com,localhost
CSRF_TRUSTED_ORIGINS=https://api.seudominio.com
NUM_PROXIES=1
NGINX_CONFIG=direct.conf
TLS_DIR=./deploy/tls
```

`ALLOWED_HOSTS` recebe nomes de host sem `https://`. `CSRF_TRUSTED_ORIGINS` recebe origens completas, com protocolo e porta quando necessário. Mantenha `localhost` nos hosts permitidos para a verificação interna da aplicação. Essas configurações não habilitam CORS para um frontend em outra origem.

Coloque o certificado válido para esse domínio em `deploy/tls/fullchain.pem` e a chave privada em `deploy/tls/privkey.pem`. Proteja a chave com `chmod 600 deploy/tls/privkey.pem`. Os arquivos são montados somente no Nginx; não entram na imagem da aplicação. A obtenção e a renovação do certificado precisam ser configuradas no servidor; não há emissão automática neste projeto.

Preencha o SMTP e um remetente autorizado antes de iniciar. Deixe `AUDIT_RETENTION_DAYS` vazio para não excluir auditoria, ou informe um número positivo de dias após definir a política de retenção.

```bash
pdm run prod:up
pdm run prod:check
pdm run prod:logs
pdm run compose:prod exec app python manage.py createsuperuser
```

Sem PDM no servidor:

```bash
docker compose --env-file .env.prod -f docker-compose.yml up -d --build
docker compose --env-file .env.prod -f docker-compose.yml exec app python manage.py check --deploy
```

O serviço `release` aplica migrações e coleta arquivos estáticos antes da inicialização dos processos. Apenas o Nginx publica as portas 80 e 443. Gunicorn, PostgreSQL e Redis não publicam portas no host. Não execute migrações automaticamente em cada worker ou réplica da aplicação.

Abra `https://api.seudominio.com/api/docs/urls/` e `/admin/`. As páginas `/manual/` devem retornar 404 em produção. Faça o fluxo completo de cadastro, e-mail, entrada, renovação e saída antes de considerar a implantação aprovada. Alterar as portas públicas exige ajustar também a origem CSRF e o redirecionamento no Nginx.

### Operação e limites deste perfil

- `prod:down` para os contêineres sem apagar os volumes. **Não use `down -v` em um ambiente com dados que precise preservar.**
- Há um único PostgreSQL e um único Redis. Os volumes não são backup, replicação nem alta disponibilidade.
- O Redis usa persistência AOF e política `noeviction`: ao atingir a memória configurada, ele recusa gravações em vez de remover silenciosamente dados da fila. O valor inicial é 256 MB; ajuste `REDIS_MAXMEMORY` e a memória disponível no servidor com base no uso real. AOF não garante perda zero em uma falha abrupta.
- Cache, sessões e fila compartilham o Redis em bancos lógicos diferentes. Isso não isola capacidade, falhas ou permissões; separar instâncias é uma evolução para cargas e disponibilidade maiores.
- `WEB_CONCURRENCY` e `CELERY_CONCURRENCY` começam em dois processos. Dimensione após medir consumo, latência e carga; não há meta de capacidade comprovada aqui.
- As verificações de saúde indicam servidor HTTP, banco, Redis, resposta do worker e processo Beat. Elas não comprovam entrega de e-mail, sucesso da última manutenção ou recuperação de desastre. Um contêiner marcado como não saudável também não é reiniciado automaticamente só por esse estado.
- Faça backup, monitore armazenamento, fila, falhas de envio e erros HTTP. Atualize imagens/dependências em homologação antes de publicar.
- A migração de e-mail pode parar por colisão entre contas. Resolva a propriedade dos endereços manualmente; não apague nem una contas para forçar a implantação.

Para gerar um backup do PostgreSQL deste Compose, em um terminal com acesso autorizado:

```bash
umask 077
mkdir -p backups
docker compose --env-file .env.prod -f docker-compose.yml exec -T db sh -c 'pg_dump -U postgres -d "$POSTGRES_DB" -Fc' > backups/postgres.dump
```

O backup contém dados pessoais: proteja, criptografe e copie para um local separado. Confirme o sucesso do comando e teste a restauração em um ambiente isolado. Nunca ensaie restauração diretamente sobre a produção. Para RDS, use também a política de backups e recuperação do serviço gerenciado.

## 7. Proxy reverso: o que realmente precisa ser confiável

O caminho normal recomendado é **navegador → Nginx HTTPS → Gunicorn privado**. O arquivo `deploy/nginx/direct.conf` atende esse caso. O Nginx informa o protocolo real e acrescenta o endereço recebido à cadeia de IPs. O Compose de produção habilita explicitamente a confiança nesses cabeçalhos; fora dele, `TRUST_PROXY_HEADERS` é desabilitado por padrão.

Não publique Gunicorn diretamente na internet. Se optar por uma implantação sem proxy, será necessário configurar TLS no próprio servidor e manter `TRUST_PROXY_HEADERS=false` e `NUM_PROXIES=0`; esse não é o caminho implementado pelo Compose de produção.

`NUM_PROXIES` conta os componentes confiáveis que acrescentam endereços ao cabeçalho `X-Forwarded-For`:

| Caminho até o Django | Valor esperado |
| --- | --- |
| Nginx → Gunicorn | `1` |
| Cloudflare → Nginx → Gunicorn | `2` |
| ALB → Nginx → Gunicorn | `2` |
| Cloudflare → ALB → Nginx → Gunicorn | `3` |

Esses números só valem para as cadeias descritas, com acréscimo de um endereço por etapa. Não ative reescrita de `REMOTE_ADDR`, `real_ip` ou Proxy Protocol sem rever a contagem. Bloqueie caminhos que pulem os proxies confiáveis; caso contrário, um cliente pode falsificar IPs e contornar os limites da aplicação.

## 8. Cloudflare com origem na AWS ou em outro servidor

A Cloudflare pode cuidar de DNS, proxy de borda, HTTPS e WAF. Esse Django não roda diretamente no ambiente Workers da Cloudflare; ele continua no servidor de origem, por exemplo em uma instância EC2.

1. Crie o registro DNS do domínio apontando para a origem e habilite o proxy da Cloudflare quando quiser usar sua borda.
2. Instale na origem um certificado público válido ou um certificado Origin CA da Cloudflare, com o nome correto do domínio.
3. Use **Full (strict)**, não Flexible. O trecho Cloudflare → origem também precisa de HTTPS com certificado válido.
4. Com Cloudflare → Nginx, mantenha `NGINX_CONFIG=direct.conf` e configure `NUM_PROXIES=2`.
5. Restrinja o firewall/Security Group da origem aos intervalos oficiais da Cloudflare. Revise periodicamente os intervalos; apenas esconder o IP no DNS não impede acesso direto.
6. Não armazene em cache respostas de autenticação, perfil ou auditoria. Configure desvio de cache para `/api/*` e `/admin/*`; não aplique regras de cache geral a sessões autenticadas.
7. Não remova nem substitua a cadeia de IPs adicionada pelos proxies. Desabilite opções que troquem IPs reais por valores sintéticos sem adaptar a aplicação.

Um certificado Origin CA não é, por si só, confiável em acesso direto pelo navegador: ele é destinado à conexão da Cloudflare com a origem. Renovação, validação do certificado e recuperação de falhas continuam sob responsabilidade da implantação.

## 9. AWS: EC2, ALB e serviços gerenciados

### EC2 com Nginx

Para começar, o Compose de produção pode rodar em uma EC2 com Docker/Compose. Publique somente 80/443 do Nginx no Security Group; use SSM ou acesso administrativo restrito, nunca SSH aberto a todos. Não libere 5432, 6379 ou 8000 publicamente. Use armazenamento criptografado e uma rotina de backup fora da instância.

### ALB encerrando HTTPS

No ALB, instale um certificado ACM para o domínio, redirecione o listener HTTP para HTTPS e encaminhe o tráfego ao Nginx pela porta HTTP da rede privada. Nesse caso:

```dotenv
NGINX_CONFIG=alb.conf
NUM_PROXIES=2
```

- Restrinja a porta HTTP da EC2 **ao Security Group do ALB**. O arquivo `alb.conf` confia no protocolo informado pelo ALB e nunca deve receber tráfego direto da internet.
- Mantenha o processamento de `X-Forwarded-For` do ALB em **append** e a preservação da porta do cliente desabilitada. A aplicação espera endereços IP, não `IP:porta`.
- Configure a checagem do target group para `/healthz`. Essa rota comprova o Nginx; acompanhe também a saúde da aplicação e das dependências.
- Crie a pasta configurada em `TLS_DIR`, mesmo que vazia: o Compose monta esse diretório, mas `alb.conf` não usa os certificados locais nem escuta na porta 443.
- O Compose ainda declara o mapeamento 443; no modo ALB, você pode usar `HTTPS_BIND=127.0.0.1` e deve negar essa entrada no Security Group.
- Com Cloudflare antes do ALB, use `NUM_PROXIES=3` e impeça acesso externo ao ALB que não passe pela borda confiável.

Não use `direct.conf` nessa cadeia HTTP interna: ele identificaria HTTP entre ALB e Nginx e causaria redirecionamentos desnecessários. `alb.conf` preserva apenas o protocolo HTTPS recebido do ALB confiável.

### RDS, Redis gerenciado e ECS

- **RDS PostgreSQL:** crie banco e usuário de aplicação sem privilégios de administrador. Aponte `DATABASE_URL` para o endpoint privado; use TLS e valide o certificado, por exemplo com `sslmode=verify-full` e `sslrootcert` apontando para o arquivo CA montado no contêiner.
- **Redis gerenciado:** use autenticação e `rediss://` com validação de certificado. Esta aplicação usa os bancos Redis `0`, `1` e `2`; não selecione uma oferta que só aceite banco `0`, como Redis Cluster ou modos serverless incompatíveis. Confirme a compatibilidade do produto contratado, inclusive comandos de fila do Celery.
- **Segredos:** em ECS, injete as variáveis por Secrets Manager/Parameter Store e uma role IAM de menor privilégio. Não coloque valores nas imagens, no Git ou no texto da definição de tarefa. Em EC2, use um mecanismo autorizado para materializar o arquivo protegido; esta aplicação não busca segredos AWS automaticamente.
- **ECS:** utilize a imagem de produção para processos web, worker e um Beat único; execute a migração/coleta como tarefa de implantação antes de liberar tráfego. A forma de compartilhar ou publicar arquivos estáticos deve ser escolhida para a topologia, por exemplo via armazenamento/CDN dedicado.
- Os arquivos Nginx incluídos usam o DNS interno do Docker Compose. Eles não são uma definição pronta de ECS: adapte o upstream/DNS, armazenamento estático, certificados, roles e redes à arquitetura escolhida.
- Ao usar RDS/Redis externos, não inicie as instâncias locais `db`/`redis` por hábito. O Compose fornecido é a implantação completa de host único; substitua a orquestração e as dependências locais para o ambiente gerenciado. Não há provisionamento automático de VPC, RDS, ECS, ALB ou certificados neste repositório.

## 10. Referência rápida dos comandos

| Comando | Uso |
| --- | --- |
| `pdm run dev` | Servidor nativo simples |
| `pdm run dev:up` / `dev:down` / `dev:logs` | Docker simples |
| `pdm run full:up` / `full:down` / `full:logs` | Docker integrado |
| `pdm run prod:up` / `prod:down` / `prod:logs` | Docker de produção |
| `pdm run compose:dev ps` | Estado dos serviços simples |
| `pdm run compose:full exec app python manage.py migrate` | Migração manual do integrado, quando necessária |
| `pdm run compose:prod ps` | Estado dos serviços de produção |
| `pdm run prod:check` | Verificações Django de configuração de produção |
| `pdm run secret` | Gerar um segredo aleatório, sem gravar arquivo |

Para rodar testes quando você decidir fazê-lo, use `pdm run test <nome-do-teste>`. As novas verificações de configuração estão em `tests.test_prod_settings` e `tests.test_container_config`; não substituem build, inicialização, TLS, teste funcional nem teste de carga. O perfil `tests.settings_integration` continua sendo exclusivo da suíte: usa um banco temporário e serviços locais, não os bancos Docker de desenvolvimento ou produção.

Referências oficiais: [Cloudflare Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/), [cabeçalhos do AWS ALB](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/x-forwarded-headers.html), [comandos restritos do ElastiCache](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/ClientConfig.RestrictedCommands.html). Confirme limites e políticas atuais do serviço contratado antes de provisionar.

## Como ler este documento

- **RN**: regra de negócio. Explica o que a aplicação permite, exige ou impede.
- **RF**: requisito funcional. Explica uma ação que a pessoa ou a equipe administradora consegue realizar.
- **RNF**: requisito não funcional. Explica segurança, disponibilidade, operação ou limite técnico que afeta o funcionamento.

## Regras de negócio (RN)

001.RN Uma conta é identificada por um único endereço de e-mail. Letras maiúsculas e minúsculas não diferenciam endereços. (Dados: `Pessoa@Exemplo.com` e `pessoa@exemplo.com` representam a mesma conta; o e-mail é guardado em letras minúsculas;)

002.RN O cadastro acontece em três etapas: pedir código, conferir código e confirmar dados pessoais. (Dados: e-mail; código de seis dígitos; nome; senha;)

003.RN Somente uma conta cujo cadastro ainda não foi concluído pode ser ativada pelo fluxo de cadastro. Uma conta já criada e desativada não volta a funcionar por esse fluxo. (Dados: conta inativa sem senha definida; conta sem privilégios administrativos;)

004.RN Códigos de cadastro, redefinição de senha e troca de e-mail têm seis dígitos, duram quinze minutos e deixam de valer após cinco tentativas incorretas. (Dados: código; data de expiração; número de tentativas;)

005.RN Conferir um código não o consome. Confirmar uma operação com código válido o consome e realiza a mudança de uma só vez. (Dados: código válido; operação de confirmação;)

006.RN Uma nova solicitação substitui o código anterior da mesma finalidade. (Dados: e-mail; finalidade do código; novo prazo de validade;)

007.RN Quando alguém tenta se cadastrar com um e-mail já ativo, a conta recebe um aviso de segurança, não um novo código de cadastro. A resposta enviada a quem fez a solicitação permanece igual. (Dados: e-mail existente; aviso de segurança;)

008.RN A solicitação de redefinição de senha responde da mesma forma para e-mail inexistente, conta inativa ou falha ao enfileirar o envio. (Dados: e-mail informado; resposta uniforme;)

009.RN Alterar e-mail exige a senha atual tanto ao pedir o código quanto ao confirmar a troca. O novo endereço precisa estar livre. (Dados: senha atual; novo e-mail; código;)

010.RN A confirmação da troca de e-mail encerra todas as sessões da conta e invalida códigos pendentes de redefinição de senha. (Dados: novo e-mail confirmado; sessões ativas; códigos de redefinição pendentes;)

011.RN A senha é literal: espaços antes ou depois fazem parte dela. Senhas vazias ou compostas apenas por espaços não são aceitas. (Dados: senha informada;)

012.RN A pessoa pode desativar a própria conta somente após informar a senha atual. (Dados: conta autenticada; senha atual;)

013.RN Uma sessão representa um acesso em um dispositivo e endereço de rede. Um novo acesso da mesma conta, dispositivo e endereço substitui a sessão anterior. (Dados: conta; dispositivo; endereço de rede;)

014.RN A opção “lembrar de mim” amplia o período sem uso da sessão de um para sete dias. Nenhuma sessão pode existir por mais de trinta dias desde sua criação. (Dados: opção lembrar de mim; data de criação; último uso;)

015.RN Reutilizar um código de renovação de sessão já substituído encerra a sessão relacionada. (Dados: código de renovação anterior; sessão relacionada;)

016.RN Uma pessoa não pode encerrar a sessão que está usando pela lista de dispositivos; para isso deve sair da conta. (Dados: sessão atual; lista de sessões;)

017.RN Apenas pessoas da equipe podem consultar a lista de usuários ativos e os registros de auditoria. (Dados: perfil de equipe; usuários ativos; registros de auditoria;)

018.RN Registros de segurança não guardam senha, código de confirmação, token de acesso, token de renovação ou valor de proteção contra falsificação de requisição. (Dados: evento de segurança; dados permitidos do evento;)

## Requisitos funcionais (RF)

001.RF A pessoa pode obter a proteção necessária antes de entrar e então entrar usando e-mail e senha. (Dados: cookie de proteção; e-mail; senha;)

002.RF Após uma entrada válida, a aplicação mantém o acesso no navegador sem expor os tokens ao código da página. (Dados: cookie de acesso; cookie de renovação;)

003.RF A pessoa pode renovar o acesso sem informar a senha novamente, desde que apresente a proteção exigida e a sessão ainda seja válida. (Dados: cookie de renovação; cookie de proteção;)

004.RF A pessoa pode sair da conta mesmo sem ter o cookie de renovação disponível. (Dados: sessão autenticada;)

005.RF A pessoa pode ver seus dispositivos ativos, identificar o dispositivo atual e encerrar outro dispositivo da mesma conta. (Dados: identificador da sessão; dispositivo; endereço de rede; data de criação;)

006.RF A pessoa pode pedir, conferir e confirmar o próprio cadastro por e-mail. (Dados: e-mail; código; nome; senha;)

007.RF A pessoa pode pedir, conferir e confirmar uma nova senha por e-mail. (Dados: e-mail; código; nova senha;)

008.RF A pessoa pode pedir, conferir e confirmar a troca do próprio e-mail. (Dados: novo e-mail; senha atual; código;)

009.RF A pessoa pode encerrar todas as sessões da própria conta ou desativar a própria conta. (Dados: sessão autenticada; senha atual para desativação;)

010.RF Uma pessoa da equipe pode consultar usuários ativos em páginas de até cem itens. (Dados: perfil de equipe; página; quantidade por página;)

011.RF Uma pessoa da equipe pode consultar registros de segurança em páginas de até cem itens. (Dados: perfil de equipe; página; quantidade por página;)

012.RF A equipe administradora pode administrar contas no painel administrativo. Sessões são apenas para consulta e seu encerramento usa a mesma regra de segurança da aplicação. (Dados: conta; sessão; painel administrativo;)

013.RF A aplicação envia mensagens de cadastro, redefinição de senha e troca de e-mail em versão simples e visual. (Dados: destinatário; assunto; conteúdo textual; conteúdo visual;)

014.RF A aplicação executa uma manutenção diária para remover cadastros abandonados, sessões vencidas e, quando configurado, registros antigos de auditoria. (Dados: horário 03:00; fuso America/Sao_Paulo; prazo de retenção de auditoria;)

015.RF A pessoa desenvolvedora pode testar os endpoints da API em páginas com formulários simples, sem copiar tokens. As páginas separam acesso e sessões, cadastro e recuperação, e conta e equipe. O navegador envia os cookies; a página prepara a proteção CSRF e mostra o status e o conteúdo da última resposta. Os botões executam ações reais, por isso devem ser usados com contas de teste. (Dados: comando `pdm run dev`; endereço `http://127.0.0.1:8000/manual/`; JavaScript habilitado; códigos recebidos por e-mail ou mostrados no terminal de desenvolvimento;)

## Requisitos não funcionais (RNF)

001.RNF Operações sensíveis conferem novamente o estado da conta antes de alterar dados ou criar sessão. (Dados: conta ativa; senha atual; e-mail atual; bloqueio de banco de dados;)

002.RNF A aplicação limita tentativas de entrada, envio de código, conferência de código e confirmação de senha para reduzir tentativas automatizadas. (Dados: endereço de rede; e-mail; conta; janela de tempo;)

003.RNF Em produção, a aplicação exige banco de dados PostgreSQL, Redis, chave secreta, hosts permitidos e origens confiáveis para proteção do navegador. (Dados: banco PostgreSQL; Redis; chave secreta; hosts; origens confiáveis;)

004.RNF Em produção, os cookies de autenticação são protegidos e a aplicação redireciona para HTTPS. (Dados: cookies seguros; redirecionamento HTTPS; política de segurança do navegador por um ano;)

005.RNF A aplicação mantém as informações principais de sessão no banco de dados e usa Redis como apoio temporário. Se a limpeza desse apoio falhar, um acesso já revogado pode durar no máximo sessenta segundos a mais. (Dados: sessão; Redis; prazo máximo de sessenta segundos;)

006.RNF O envio de e-mail acontece depois de salvar a operação. Falhas de rede ou SMTP são tentadas novamente até três vezes; cada espera de rede pode durar no máximo dez segundos. (Dados: fila de e-mail; até três tentativas; tempo máximo de dez segundos;)

007.RNF Mensagens de erro de emissão de código não expõem o conteúdo original do erro nos registros. (Dados: nome da operação; tipo do erro;)

008.RNF A limpeza diária remove apenas cadastros abandonados que atendem às condições de idade, código vencido e não utilizado. Contas desativadas pela própria pessoa não são removidas por essa rotina. (Dados: cadastro pendente; 48 horas; código vencido; conta desativada;)

009.RNF A mudança para e-mail minúsculo interrompe a atualização se existirem duas contas que passariam a ter o mesmo e-mail. A aplicação não une contas automaticamente. (Dados: migração de e-mail; colisão de e-mail; revisão manual;)

010.RNF O desenvolvimento simples usa SQLite e memória; o integrado usa PostgreSQL, Redis, worker e Beat; a produção acrescenta Gunicorn, Nginx, HTTPS e preparação separada de migrações e arquivos estáticos. Os perfis Docker têm dados e configurações separados. (Dados: perfil simples; perfil integrado; perfil de produção; volumes; verificações de disponibilidade;)

011.RNF O integrado e a produção executam um worker de tarefas e um único agendador Beat. O modo simples executa e-mail de forma imediata no terminal e não inicia esses processos externos. (Dados: worker Celery; Beat; fila Redis; modo simples sem fila externa;)

012.RNF A implantação de produção depende de um certificado válido e de acesso restrito aos serviços internos. O desenvolvimento permanece acessível apenas pela interface local nos arquivos Compose. (Dados: Gunicorn; Nginx; certificado TLS; firewall; **a confirmar** validação do ambiente real e sua capacidade;)

013.RNF A leitura dos registros de auditoria pela aplicação não impede alteração direta no banco de dados. (Dados: permissões do banco; política de retenção; **a confirmar** responsabilidade legal e configuração de escrita imutável;)

014.RNF As páginas de teste manual ficam indisponíveis fora do modo de desenvolvimento, não guardam tokens no armazenamento do navegador e não substituem as permissões nem os limites da API. Operações destrutivas pedem confirmação; senhas são apagadas dos campos depois do envio. O painel administrativo e a documentação podem ser abertos pelos links dessas páginas. (Dados: configuração `DEBUG` ativa; páginas `/manual/auth/`, `/manual/codes/` e `/manual/account/`; cookies da própria aplicação;)
