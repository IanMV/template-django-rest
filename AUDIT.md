  ──────
  ## Sumário Executivo

  Este documento apresenta a validação técnica independente das 22
  descobertas (D-01 a D-13 e R-01 a R-09) apontadas no relatório de
  auditoria anterior. Cada item foi reavaliado diretamente contra o código-
  fonte, os contratos do Django 6.1 / Django REST Framework, a suíte de
  testes existente e a documentação arquitetural do projeto (README.md),
  buscando ativamente refutar cada hipótese antes de confirmá-la.

  Resultado consolidado da revisão crítica:

  • Confirmados: 8 problemas (1 de severidade Alta, 4 de severidade Média,
  3 de severidade Baixa).
  • Condicionais: 8 problemas (1 de severidade Alta, 4 de severidade Média,
  3 de severidade Baixa).
  • Falsos Positivos (Refutados): 6 descobertas (D-12, R-05, R-06, R-07, R-
  08, R-09).
  • Inconclusivos: 0 das descobertas originais (com ressalvas operacionais
  documentadas na Seção 3).
  ──────
  ## 1. Problemas Confirmados e Condicionais (Ordenados por Severidade)
  ──────
  ### 1.1. Severidade Alta

  #### [D-01] Bloqueio de troca de e-mail e reserva indevida de endereço
  (Email Squatting / DoS) via solicitação pública de cadastro

  • Identificação: D-01
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização:
      • RegistrationService.request_registration
      (core/registration/services.py, linhas 18–36)
      • EmailChangeService.request_change (core/email_change/services.py,
      linhas 20–35)
      • EmailChangeService.confirm_change (core/email_change/services.py,
      linhas 58–73)
      • CustomUserCreationForm (core/admin.py, linhas 18–22)
  • Análise: Tentou-se verificar se EmailChangeService ou
  CustomUserCreationForm ignoram ou sobrescrevem registros provisórios
  (is_active=False, password="") criados por POST
  /api/registration/request/. Constatou-se que não há qualquer tratamento:
  RegistrationService.request_registration insere imediatamente uma linha
  em core_user com email único, e EmailChangeService verifica User.objects.
  filter(email=new_email).exists() (na solicitação) e User.objects.
  filter(email=new_email).exclude(pk=current.pk).exists() (na confirmação)
  sem filtrar contas não confirmadas.
  • Evidências: Reprodução HTTP ponta a ponta executada no ambiente:
      1. Usuário autenticado solicita troca de e-mail (POST /api/email-
      change/request/ para new@example.com) -> retorna 200 OK e emite o
      código OTP de 6 dígitos.
      2. Cliente anônimo chama POST /api/registration/request/ com
      {"email": "new@example.com"} -> retorna 201 Created e insere
      User(email="new@example.com", is_active=False, password="").
      3. Usuário autenticado envia POST /api/email-change/confirm/ com o
      código OTP válido recebido em new@example.com e sua senha atual ->
      falha com 400 Bad Request: {"new_email": ["This e-mail is already in
      use."]}.
  • Condições de ocorrência: Qualquer chamada pública a POST
  /api/registration/request/ informando o endereço de e-mail alvo antes da
  confirmação da troca de e-mail (ou antes do cadastro via Admin).
  Viabilidade trivial.
  • Justificativa do veredito: Comportamento reproduzido integralmente via
  cliente HTTP com CSRF ativo. Nenhuma camada do sistema distingue um User
  provisório não verificado de uma conta ativa durante a troca de e-mail ou
  criação no Admin.
  • Severidade revisada: Alta (mantida).
  • Correção recomendada: Não criar registros na tabela core_user durante
  request_registration antes da validação do OTP, ou permitir que
  EmailChangeService.confirm_change (que já comprovou posse do new_email
  via OTP) e EmailChangeService.request_change removam/substituam registros
  provisórios não verificados (is_active=False, password="", is_staff=False,
  is_superuser=False).
  ──────
  #### [R-01] Exaustão dos workers síncronos do Gunicorn por envio SMTP
  síncrono no ciclo HTTP

  • Identificação: R-01
  • Veredito: Condicional
  • Confiança: Alta
  • Localização:
      • Dockerfile:24 (Dockerfile, linha 24)
      • docker-compose.yml:24-47 (docker-compose.yml, linhas 24 e 42–47)
      • send_email (core/shared/email_token_sender.py, linhas 8–13)
      • app/settings/prod.py:122-135 (app/settings/prod.py, linhas 122–135)
  • Análise: Verificou-se se o parâmetro "timeout": 10 em
  MAILERS["default"]["OPTIONS"] limita a duração total do bloqueio a 10
  segundos ou se o Gunicorn usa threads. Na biblioteca padrão smtplib
  (usada por django.core.mail.backends.smtp.EmailBackend), timeout aplica-
  se a cada operação individual de socket (connect, ehlo, starttls, auth,
  mail, rcpt, data, quit), e o README.md (linha 312) reconhece: "Cada
  espera de rede tem timeout de dez segundos; não é um prazo total
  garantido". Como o Dockerfile não define --threads nem --worker-class, o
  Gunicorn utiliza o worker sync (1 requisição por processo) com
  WEB_CONCURRENCY=2 por padrão no docker-compose.yml.
  • Evidências:
      • Dockerfile:24: CMD ["gunicorn", "app.wsgi:application", "--bind=0.
      0.0.0:8000", ..., "--timeout=30", "--forwarded-allow-ips="]
      • docker-compose.yml:24: WEB_CONCURRENCY: ${WEB_CONCURRENCY:-2}
      • docker-compose.yml:43: healthcheck executa urlopen('http://127.0.0.
      1:8000/api/login/', timeout=3) contra a mesma fila de workers
      Gunicorn.
  • Condições de ocorrência: Lentidão, tarpitting ou queda de pacotes no
  servidor SMTP externo combinada com 2 requisições concorrentes de emissão
  de código (/api/registration/request/, /api/password-reset/request/ ou
  /api/email-change/request/).
  • Justificativa do veredito: Classificado como Condicional porque depende
  da degradação do serviço SMTP externo e da manutenção da configuração
  padrão de 2 workers sync. Quando a condição ocorre, 2 requisições bastam
  para bloquear 100% da capacidade de atendimento da API e derrubar o
  healthcheck do contêiner.
  • Severidade revisada: Alta (mantida).
  • Correção recomendada: Configurar --threads (ex.: --threads=4, ativando
  o worker gthread) no comando do Gunicorn no Dockerfile ou mover o envio
  de e-mails para processamento fora da thread HTTP.
  ──────
  ### 1.2. Severidade Média

  #### [D-02] Enumeração direta e silenciosa de contas existentes via POST
  /api/email-change/request/

  • Identificação: D-02
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização:
      • EmailChangeService.request_change (core/email_change/services.py,
      linhas 20–35)
      • EmailChangeRequestView.post (core/email_change/views.py, linhas
      45–53)
  • Análise: Avaliou-se se os controles de autenticação (IsAuthenticated),
  reautenticação (require_current_password) e limitação de taxa
  (limit_code_requests) impedem a enumeração.
      1. Como o cadastro de conta é público, qualquer agente externo pode
      obter uma sessão autenticada válida conhecendo a própria senha
      (require_current_password nunca falha nem incrementa o contador
      reauth:user quando a senha informada é a correta).
      2. limit_code_requests("email-change", new_email, ip_address) aplica
      um limite de 1 requisição a cada 2 segundos por IP (30
      consultas/minuto por IP por worker) quando new_email varia a cada
      chamada.
      3. Quando User.objects.filter(email=new_email).exists() é verdadeiro,
      a resposta é 400 Bad Request ({"new_email": ["This e-mail is already
      in use."]}) sem disparo de e-mail; quando falso, retorna 200 OK com
      MSG_CODE_SENT ("If the e-mail exists, a code was sent.").
  • Evidências:
      • core/email_change/services.py:33-34:
        if User.objects.filter(email=new_email).exists():
            raise serializers.ValidationError({"new_email":
            MSG_EMAIL_IN_USE})

  • Condições de ocorrência: Possuir qualquer conta ativa na aplicação e
  submeter POST /api/email-change/request/ com a própria senha e o e-mail
  que se deseja consultar.
  • Justificativa do veredito: Confirmado. Há contradição direta entre a
  postura anti-enumeração do projeto (inclusive o texto de MSG_CODE_SENT
  retornado pelo próprio endpoint) e o retorno explícito de 400
  MSG_EMAIL_IN_USE na etapa de solicitação.
  • Severidade revisada: Média (reduzida de Alta para Média, pois exige
  conta autenticada e é limitada a 1 consulta a cada 2s por IP por worker,
  tratando-se de vazamento de existência de conta e não de tomada de conta).
  • Correção recomendada: Retornar resposta uniforme 200 OK (MSG_CODE_SENT)
  em EmailChangeRequestView independentemente de new_email já existir
  (omitindo a criação do código EmailChange quando o endereço estiver em
  uso) e adicionar limite de taxa por user.pk na solicitação de troca de e-
  mail.
  ──────
  #### [D-03] Bypass da normalização e unicidade de e-mail via domínios
  internacionalizados (IDN vs. Punycode) e maiúsculas Unicode

  • Identificação: D-03
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização:
      • UserManager.normalize_email (core/models/user.py, linhas 17–19)
      • limit_code_requests e login_pair_key (core/auth/rate_limit.py)
  • Análise: Verificou-se se o EmailField do DRF/Django converte domínios
  IDN para Punycode ou se os rejeita. O EmailValidator do Django aceita
  tanto user@münchen.de quanto user@xn--mnchen-3ya.de sem alterá-los.
  UserManager.normalize_email aplica apenas .strip().lower(), preservando
  as duas strings como distintas no banco de dados e nas chaves SHA-256 do
  rate limiter. Porém, ao enviar o e-mail via django.core.mail.backends.
  smtp.EmailBackend.prep_address, o Django aplica punycode(mailbox.domain),
  convertendo user@münchen.de em user@xn--mnchen-3ya.de.
  • Evidências: Reprodução confirmada:
      • RegistrationService.request_registration("user@münchen.de") e
      RegistrationService.request_registration("user@xn--mnchen-3ya.de")
      criam dois registros distintos em core_user.
      • EmailBackend(alias="default", host="localhost").
      prep_address("user@münchen.de") retorna 'user@xn--mnchen-3ya.de'.
      • "test@İSTANBUL.COM".strip().lower() produz 'test@i\u0307stanbul.
      com', que prep_address codifica como 'test@xn--istanbul-o0e.com'
      (distinto de 'test@istanbul.com').
  • Condições de ocorrência: Uso de endereços de e-mail com domínios
  internacionalizados (IDN) ou caracteres Unicode com expansão de
  casefolding (como İ).
  • Justificativa do veredito: Confirmado. Viola a invariante documentada
  do projeto de que cada caixa de e-mail corresponde a uma única identidade
  canônica no banco de dados.
  • Severidade revisada: Média (reduzida de Alta para Média, pois não afeta
  domínios puramente ASCII e não permite tomar uma conta existente sem
  acesso à caixa de e-mail correspondente, embora permita criar contas
  duplicadas para a mesma caixa postal e dobrar limites de taxa por e-mail).
  • Correção recomendada: Normalizar o domínio via IDNA (domain.
  encode("idna").decode("ascii")) dentro de UserManager.normalize_email (ou
  restringir domínios/endereços a caracteres ASCII nos serializers).
  ──────
  #### [D-06] Falha de persistência (DataError / HTTP 503 no PostgreSQL) ao
  informar e-mails entre 255 e 320 caracteres
  • Identificação: D-06
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização:
      • RegistrationRequestSerializer (core/registration/serializers.py,
      linha 9)
      • EmailChangeRequestSerializer (core/email_change/serializers.py,
      linha 6)
      • RegistrationService.request_registration
      (core/registration/services.py, linhas 24–61)
      • EmailChangeService.request_change (core/email_change/services.py,
      linhas 37–55)
  • Análise: Na validação crítica, examinou-se o comportamento exato do
  Django 6.1, do DRF e do PostgreSQL:
      1. Em django.core.validators.EmailValidator.__call__, o limite máximo
      aceito é len(value) <= 320. Como os serializers usam serializers.
      EmailField() sem max_length=254, e-mails de 255 a 320 caracteres
      passam por serializer.is_valid(raise_exception=True).
      2. Refinamento em relação à auditoria anterior: Nos endpoints que
      realizam apenas SELECT (login/, password-reset/request/, password-
      reset/confirm/, registration/confirm/), o PostgreSQL não lança
      DataError ao comparar varchar(254) com uma string de 259 caracteres
      na cláusula WHERE. O erro django.db.utils.DataError: value too long
      for type character varying(254) ocorre especificamente nas operações
      de INSERT em POST /api/registration/request/ (core_user.email) e POST
      /api/email-change/request/ (core_emailchange.new_email).
      3. Correção do código de status reportado no título original: Nesses
      dois endpoints, a exceção DataError é capturada pelo except Exception
      as exc: dos serviços, registrando um erro operacional falso nos logs
      (ERROR: Registration code issuance failed (DataError)) e retornando
      503 Service Unavailable (e não HTTP 500) para um erro de validação de
      entrada do cliente que deveria ser 400 Bad Request.
      4. Em SQLite (app.settings.dev), a linha de 259 caracteres é gravada
      no banco (pois o SQLite não restringe o tamanho de VARCHAR(254)),
      tornando o registro inválido ao tentar salvá-lo posteriormente no
      UserAdmin (CustomUserChangeForm aplica max_length=254 do models.
      EmailField).
  • Evidências:
      • EmailValidator.__call__: if not value or "@" not in value or
      len(value) > 320:
      • core/migrations/0001_initial.py (linhas 30 e 57): models.
      EmailField(max_length=254, ...)
      • Teste com e-mail de 259 caracteres: RegistrationRequestSerializer e
      EmailChangeRequestSerializer retornam is_valid() == True.
  • Condições de ocorrência: Envio de e-mail válido com 255 a 320
  caracteres em POST /api/registration/request/ ou POST /api/email-
  change/request/.
  • Justificativa do veredito: Confirmado, com precisão ajustada quanto aos
  endpoints afetados (INSERT) e ao status HTTP retornado (503 Service
  Unavailable em vez de 400 Bad Request).
  • Severidade revisada: Média (mantida).
  • Correção recomendada: Adicionar max_length=254 em todos os campos
  serializers.EmailField(max_length=254, ...) dos serializers da API.
  ──────
  #### [D-09] Ausência de limite superior de tamanho em campos de senha
  permite consumo desproporcional de CPU (DoS por PBKDF2)
  • Identificação: D-09
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização:
      • LoginSerializer (core/auth/serializers.py)
      • RegistrationConfirmSerializer (core/registration/serializers.py)
      • PasswordResetConfirmSerializer (core/password_reset/serializers.py)
      • EmailChangeRequestSerializer e EmailChangeConfirmSerializer
      (core/email_change/serializers.py)
      • DeactivateSelfSerializer (core/users/serializers.py)
  • Análise: Verificou-se se o Django 6.1, o PBKDF2PasswordHasher ou os
  validadores em AUTH_PASSWORD_VALIDATORS impõem algum limite máximo ao
  tamanho da senha:
      1. Nenhum dos validadores configurados em app/settings/base.py limita
      o comprimento máximo.
      2. Em RegistrationConfirmView.post e PasswordResetConfirmView.post,
      serializer.is_valid(raise_exception=True) executa validate_password()
      antes mesmo de
      limit_code_verification_attempts(get_client_ip(request)).
      3. Em POST /api/login/, mesmo para e-mails inexistentes,
      ModelBackend.authenticate executa UserModel().set_password(password)
      para mitigar ataques de tempo, processando integralmente o payload de
      até 1 MB (client_max_body_size 1m no Nginx) no PBKDF2PasswordHasher.
  • Evidências: Benchmark executado no ambiente com app.settings.dev:
      • make_password("abcd" * 250_000) (1 MB) consome 0,790 segundos de
      CPU por chamada.
  • Condições de ocorrência: Envio de requisições contendo senhas próximas
  ao limite de 1 MB permitido pelo Nginx.
  • Justificativa do veredito: Confirmado. A ausência de max_length permite
  amplificar em mais de uma ordem de grandeza o custo de CPU por requisição
  antes ou dentro dos mecanismos de autenticação.
  • Severidade revisada: Média (mantida).
  • Correção recomendada: Definir max_length=128 (ou 256) em todos os
  campos de senha dos serializers.
  ──────
  #### [D-04] Condição de corrida (TOCTOU) na reautenticação por senha
  (require_current_password)

  • Identificação: D-04
  • Veredito: Condicional (reclassificado de Confirmado para Condicional)
  • Confiança: Alta
  • Localização: require_current_password (core/auth/rate_limit.py, linhas
  57–74)
  • Análise: Na validação crítica, testou-se tanto a mecânica do código
  quanto as garantias do servidor de aplicação:
      1. No código de require_current_password: A função lê attempts =
      cache.get(key, 0), verifica if attempts >= 5: raise
      Throttled(wait=300) e imediatamente executa if user.
      check_password(password):, só chamando _limit(key, 5, 300) após
      check_password retornar False. Em teste com
      ThreadPoolExecutor(max_workers=6) partindo de attempts = 4 (apenas 1
      tentativa restante) e enviando 5 senhas erradas + 1 senha correta
      simultaneamente, todas as 6 threads passaram pela guarda attempts >=
      5, executaram check_password e a thread com a senha correta retornou
      SUCCESS apesar de 9 tentativas totais terem sido efetuadas.
      2. Restrição arquitetural na stack padrão (Dockerfile): Na
      configuração padrão do Dockerfile, o Gunicorn roda com o worker sync
      (single-threaded por processo) e LocMemCache (isolado por processo).
      Dentro de um único processo sync sem threads, não há execução
      concorrente sobre a mesma instância de LocMemCache (a amplificação
      entre múltiplos processos sync decorre do isolamento de LocMemCache
      em R-03). Portanto, a condição de corrida TOCTOU em
      require_current_password só se manifesta quando:
	 • O servidor executa múltiplas threads por processo (gthread,
	 uvicorn, runserver ou correção de R-01), ou
	 • Um backend de cache compartilhado (Redis/Memcached, conforme
	 recomendado nos comentários de base.py e rate_limit.py) é
	 utilizado com múltiplos workers.
  • Evidências: Reprodução em runtime com 6 threads concorrentes partindo
  de 4 falhas prévias:
    D-04 results (started at 4/5 attempts, sent 5 wrong + 1 right
    concurrently):
    [('ValidationError', 'wrong1'), ('ValidationError', 'wrong2'),
    ('ValidationError', 'wrong3'),
     ('ValidationError', 'wrong4'), ('ValidationError', 'wrong5'),
     ('SUCCESS', 'CorrectPassword!123')]
  • Condições de ocorrência: Execução concorrente sobre o mesmo backend de
  cache (ambiente multi-thread ou cache distribuído) com sessão autenticada
  ativa.
  • Justificativa do veredito: Reclassificado de Confirmado para
  Condicional porque depende de concorrência sobre o mesmo cache (multi-
  thread ou cache compartilhado).
  • Severidade revisada: Média (reduzida de Alta para Média, pois exige
  sessão autenticada prévia e concorrência no backend de cache).
  • Correção recomendada: Incrementar atomicamente o contador (_limit(key,
  5, 300)) antes de user.check_password(password) e remover a chave em caso
  de acerto (ou realizar a verificação sob o bloqueio select_for_update do
  usuário).
  ──────
  #### [D-05] Sobrescrita silenciosa de estado de segurança (is_active,
  email) no Django Admin por formulário HTML defasado
  • Identificação: D-05
  • Veredito: Condicional (reclassificado de Confirmado para Condicional)
  • Confiança: Alta
  • Localização:
      • UserAdmin.get_object (core/admin.py, linhas 140–150)
      • UserAdmin.fieldsets (core/admin.py, linhas 81–102)
      • UserAdmin.save_model (core/admin.py, linhas 156–163)
  • Análise: Verificou-se por que UserAdmin.get_object foi implementado com
  select_for_update(no_key=True) e o que os testes em
  tests/test_admin_security.py realmente garantem:
      1. O select_for_update em UserAdmin.get_object impede que uma edição
      administrativa em /admin/core/user/<id>/change/ restaure campos que
      não estão no formulário HTML (password e session_version) e impede
      que /admin/core/user/<id>/password/ restaure is_active (pois
      is_active não faz parte de AdminPasswordChangeForm).
      2. Entretanto, em /admin/core/user/<id>/change/, os campos email e
      is_active fazem parte de CustomUserChangeForm. Mesmo que get_object
      recarregue obj com is_active=False sob bloqueio no início do POST, o
      dicionário request.POST enviado pelo navegador do administrador
      contém "is_active": "on" e "email": "<email_antigo>" (valores lidos
      quando o administrador abriu a página GET). O ModelForm aplica
      request.POST sobre obj, reativando a conta (is_active=True) ou
      revertendo o e-mail para o valor antigo.
  • Evidências: Reprodução validada em runtime:
    # Admin carrega GET /admin/core/user/<pk>/change/ enquanto
    owner.is_active == True
    # Owner desativa a própria conta (owner.is_active == False)
    D-05 before admin POST: is_active= False
    # Admin submete POST alterando apenas name="Edited"
    D-05 after admin POST: status= 302 is_active= True name= Edited
  • Condições de ocorrência: Um administrador estar com o formulário de
  edição de um usuário aberto (ou submetê-lo concorrentemente) no momento
  em que esse mesmo usuário desativa a própria conta ou confirma troca de
  e-mail pela API.
  • Justificativa do veredito: Reclassificado para Condicional pois requer
  interação humana concorrente de um administrador editando o mesmo
  registro no Django Admin.
  • Severidade revisada: Média (reduzida de Alta para Média).
  • Correção recomendada: Validar no CustomUserChangeForm se
  session_version ou updated_at mudou entre o render do formulário (GET) e
  a submissão (POST).
  ──────
  #### [R-02] Fallback para REMOTE_ADDR (IP do proxy) em get_client_ip
  quando X-Forwarded-For diverge de NUM_PROXIES
  • Identificação: R-02
  • Veredito: Condicional
  • Confiança: Alta
  • Localização: get_client_ip (core/shared/client_ip.py, linhas 6–23)
  • Análise: Verificou-se se na stack padrão (docker-compose.yml +
  deploy/nginx/snippets/locations.conf com NUM_PROXIES=1) um cliente
  externo consegue forçar get_client_ip a cair no fallback return remote
  (REMOTE_ADDR do contêiner Nginx):
      1. Na topologia padrão de 1 proxy (Nginx fourni): A diretiva
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for; no Nginx
      sempre anexa , <remote_addr> ao final do cabeçalho. Logo, len(chain)
      >= 1 é sempre verdadeiro e chain[-1] é sempre o IP da conexão TCP no
      Nginx (sem porta), que ip_address() valida com sucesso. Portanto, um
      atacante externo não consegue forçar esse fallback na topologia
      padrão de 1 proxy com o Nginx incluído.
      2. Quando ocorre: O problema ocorre exclusivamente se NUM_PROXIES for
      configurado com um número maior que a quantidade real de proxies (ex.
      : NUM_PROXIES=2 quando há apenas 1 proxy) ou se a aplicação for
      colocada atrás de um proxy/balanceador externo (ex.: IIS/Azure
      Application Gateway) que inclua :porta em X-Forwarded-For, fazendo
      ip_address() levantar ValueError e retornar o REMOTE_ADDR
      compartilhado do proxy.
  • Evidências: core/shared/client_ip.py:13-23 e
  tests/test_client_ip.py:26-32.
  • Condições de ocorrência: Configuração incorreta de NUM_PROXIES ou uso
  de proxy reverso que formata X-Forwarded-For com <ip>:<porta>.
  • Justificativa do veredito: Condicional. Não é explorável pelo cliente
  na stack Nginx padrão quando NUM_PROXIES=1, mas causa bloqueio global de
  rate-limit caso a topologia de proxies divirja de NUM_PROXIES ou inclua
  porta no cabeçalho.
  • Severidade revisada: Média (reduzida de Alta para Média, dado que não é
  acionável pelo atacante na configuração Nginx padrão).
  • Correção recomendada: Quando NUM_PROXIES > 0 e a extração de X-
  Forwarded-For falhar, não retornar REMOTE_ADDR (IP interno do proxy)
  silenciosamente sem registrar aviso ou remover sufixo de porta antes do
  parse.
  ──────
  #### [R-04] Contabilização de logins bem-sucedidos no limite por IP
  (login:ip) bloqueia usuários legítimos atrás de NAT

  • Identificação: R-04
  • Veredito: Condicional
  • Confiança: Alta
  • Localização:
      • limit_login_attempts e reset_login_attempts (core/auth/rate_limit.
      py)
      • AuthService.login_user (core/auth/services.py)
  • Análise: Verificou-se em AuthService.login_user que
  limit_login_attempts(email, ip_address) incrementa login:ip (limite 30 /
  300s) antes de authenticate(), e reset_login_attempts(email, ip_address)
  apaga apenas login:pair, mantendo o contador login:ip intacto após logins
  válidos. Além disso, _limit(_key("login:ip", ...), 30, 300) executa antes
  de _limit(login_pair_key(...), 10, 300), de modo que um único
  usuário/atacante insistindo na mesma conta já bloqueada em login:pair
  esgota o limite login:ip de toda a rede compartilhada.
  • Evidências: core/auth/rate_limit.py:37-54 e
  tests/test_rate_limit.py:82-95.
  • Condições de ocorrência: Redes corporativas, universitárias ou CGNAT
  onde mais de 30 logins (ou 30 tentativas contra uma única conta já
  bloqueada em login:pair) partem do mesmo IP público em 5 minutos.
  • Justificativa do veredito: Condicional (depende de compartilhamento de
  IP de saída por múltiplos usuários).
  • Severidade revisada: Média (mantida).
  • Correção recomendada: Avaliar login_pair_key antes de login:ip (para
  que pares já bloqueados não consumam o orçamento do IP) e incrementar
  login:ip apenas quando authenticate() falhar.
  ──────
  ### 1.3. Severidade Baixa
  #### [D-07] Erro 500 (TransactionManagementError) em UserAdmin.get_object
  ao receber POST fora de transação no PostgreSQL
  • Identificação: D-07
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização: UserAdmin.get_object (core/admin.py, linhas 140–150)
  • Análise: Verificou-se quais views de ModelAdmin invocam self.
  get_object() sem envolver a chamada em transaction.atomic(). Enquanto
  changeform_view, delete_view e UserAdmin.user_change_password abrem
  transação antes de chamar get_object em requisições POST, ModelAdmin.
  history_view (/admin/core/user/<id>/history/) não restringe o método HTTP
  a GET e não abre transação. Ao receber um POST, UserAdmin.get_object
  invoca select_for_update(no_key=True) em modo autocommit, lançando
  TransactionManagementError.
  • Evidências: Reprodução validada em runtime simulando
  has_select_for_update = True:
    POST /admin/core/user/96e712f2-1969-46c6-aebd-0d2930458aca/history/
    -> django.db.transaction.TransactionManagementError: select_for_update
    cannot be used outside of a transaction.
  • Condições de ocorrência: Envio de requisição POST autenticada como
  is_staff=True para /admin/core/user/<id>/history/ no PostgreSQL (ou
  chamada direta a UserAdmin.get_object com request.method == "POST" fora
  de transaction.atomic()).
  • Justificativa do veredito: Confirmado e reproduzido.
  • Severidade revisada: Baixa (reduzida de Média para Baixa, pois afeta
  apenas uma rota administrativa interna que não recebe POST durante a
  navegação normal da interface do Django Admin e não causa corrupção de
  dados).
  • Correção recomendada: Em UserAdmin.get_object, condicionar o .
  select_for_update(no_key=True) a connections[router.db_for_write(self.
  model)].in_atomic_block.
  ──────
  #### [D-11] Paginação não determinística em GET /api/users/list/ e
  ausência de índice em User.created_at
  • Identificação: D-11
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização:
      • UserService.list_users (core/users/services.py, linhas 10–11)
      • User.created_at e User.Meta.ordering (core/models/user.py)
  • Análise: Verificou-se a definição do modelo User e a migração
  0001_initial.py. De fato, User.created_at não possui db_index=True, e
  order_by("-created_at") não inclui critério de desempate determinístico
  ("-id").
  • Evidências: core/users/services.py:11 e
  core/migrations/0001_initial.py:33.
  • Condições de ocorrência: Paginação de /api/users/list/ na presença de
  registros com mesmo created_at ou tabelas core_user grandes.
  • Justificativa do veredito: Confirmado.
  • Severidade revisada: Baixa (mantida).
  • Correção recomendada: Usar order_by("-created_at", "-id") e adicionar
  db_index=True em User.created_at.
  ──────
  #### [D-13] Configurações inválidas e conflitantes em .env.example e
  fallback de DEFAULT_FROM_EMAIL em dev.py
  • Identificação: D-13
  • Veredito: Confirmado
  • Confiança: Alta
  • Localização: .env.example:1-35 (linhas 6, 9, 13–14, 28–29) e
  app/settings/dev.py:65 (linha 65)
  • Análise: Verificou-se com dotenv_values(".env.example") que o arquivo .
  env.example presente na árvore de trabalho define
  EMAIL_HOST_PASSWORD=django.core.mail.backends.smtp.EmailBackend, declara
  TRUST_PROXY_HEADERS e NUM_PROXIES duas vezes com valores opostos (false/0
  e depois true/1), e define DEFAULT_FROM_EMAIL= vazio, o que faz os.
  getenv("DEFAULT_FROM_EMAIL", "noreply@localhost") em app/settings/dev.py
  retornar "" em vez de "noreply@localhost".
  • Evidências: Saída de dotenv_values(".env.example") validada diretamente.
  • Condições de ocorrência: Cópia de .env.example para .env.
  • Justificativa do veredito: Confirmado.
  • Severidade revisada: Baixa (mantida).
  • Correção recomendada: Corrigir as chaves em .env.example e alterar a
  linha 65 de app/settings/dev.py para DEFAULT_FROM_EMAIL = (os.
  getenv("DEFAULT_FROM_EMAIL") or "noreply@localhost").strip().
  ──────
  #### [D-08] Condição de corrida entre
  RegistrationService.request_registration e cleanup_auth
  • Identificação: D-08
  • Veredito: Condicional (reclassificado de Confirmado para Condicional)
  • Confiança: Alta
  • Localização: RegistrationService.request_registration
  (core/registration/services.py, linhas 23–27)
  • Análise: O fluxo executa User.objects.get_or_create(email=email,
  defaults={"is_active": False}) (cujo SELECT inicial não adquire bloqueio
  de linha) seguido de User.objects.select_for_update(no_key=True).
  get(pk=user.pk). Se cleanup_auth excluir o registro abandonado exatamente
  entre o SELECT sem bloqueio e o SELECT ... FOR NO KEY UPDATE, .
  get(pk=user.pk) lança User.DoesNotExist, convertido em 503 Service
  Unavailable. Contudo, a janela de corrida é de microssegundos e exige que
  um cadastro abandonado há mais de 48 horas seja solicitado exatamente no
  instante em que cleanup_auth o está removendo.
  • Evidências: core/registration/services.py:23-27.
  • Condições de ocorrência: Execução de cleanup_auth concorrente no mesmo
  milissegundo com request_registration para o mesmo e-mail abandonado há >
  48h.
  • Justificativa do veredito: Reclassificado para Condicional devido à
  janela temporal extremamente estreita e às pré-condições específicas (>
  48h + execução simultânea do job de limpeza).
  • Severidade revisada: Baixa (reduzida de Média para Baixa, dado que a
  probabilidade de colisão é mínima e o impacto limita-se a uma resposta
  503 isolada).
  • Correção recomendada: Usar User.objects.select_for_update(no_key=True).
  get_or_create(email=email, defaults={"is_active": False}).
  ──────
  #### [D-10] User.get_short_name() lança IndexError quando name contém
  apenas espaços em branco
  • Identificação: D-10
  • Veredito: Condicional (reclassificado de Confirmado para Condicional)
  • Confiança: Alta
  • Localização: User.get_short_name (core/models/user.py, linhas 129–130)
  • Análise: A validação buscou verificar se um usuário com name = "   "
  pode ser criado pelas rotas HTTP da API ou pelo Django Admin, e onde
  get_short_name() é chamado:
      1. Na API (RegistrationConfirmSerializer), serializers.CharField
      possui trim_whitespace=True por padrão, convertendo "   " em "" e
      rejeitando a entrada.
      2. No Django Admin (CustomUserCreationForm / CustomUserChangeForm),
      forms.CharField possui strip=True por padrão, também rejeitando "   ".
      3. No template do Django Admin (admin/base.html: {% firstof user.
      get_short_name user.get_username %}), o resolvedor de variáveis de
      template do Django captura IndexError silenciosamente e faz fallback
      para user.get_username.
      Portanto, o IndexError só pode ocorrer se o registro User for criado
      via chamadas diretas ao ORM (User.objects.create_user(..., name="
      ")) e user.get_short_name() for chamado diretamente em código Python.
  • Evidências: core/models/user.py:129-130 e inspeção de
  django/contrib/admin/templates/admin/base.html.
  • Condições de ocorrência: Criação de User via ORM/script com name
  contendo apenas espaços, seguida de chamada direta a user.
  get_short_name() em Python.
  • Justificativa do veredito: Reclassificado de Confirmado para
  Condicional, pois as camadas de validação HTTP (DRF e Django Forms)
  bloqueiam a entrada na superfície pública e administrativa.
  • Severidade revisada: Baixa (mantida).
  • Correção recomendada: Alterar get_short_name para parts = self.name.
  split(); return parts[0] if parts else self.email.
  ──────
  #### [R-03] Invalidação cruzada de códigos OTP em reenvio rápido quando
  WEB_CONCURRENCY > 1 com LocMemCache
  • Identificação: R-03
  • Veredito: Condicional
  • Confiança: Alta
  • Localização:
      • app/settings/base.py:75-78
      • core/auth/rate_limit.py:16-35
  • Análise: A revisão crítica verificou que o uso de LocMemCache e a
  multiplicação da margem dos limitadores pelo número de processos workers
  são decisões arquiteturais explicitamente documentadas em três locais:
  README.md (linha 315: "os contadores são por processo... Mais workers
  ampliam a margem efetiva. Não é limitação global ou estrita"),
  app/settings/base.py (linha 76) e core/auth/rate_limit.py (linha 17).
  Logo, a multiplicação de limites por worker não pode ser tratada como
  defeito não intencional. Resta apenas o efeito colateral funcional em que
  duas solicitações de código feitas em menos de 60 segundos (ex.: duplo
  clique na SPA) e balanceadas para 2 workers distintos passam ambas por
  limit_code_requests, fazendo o segundo worker apagar o OTP do primeiro e-
  mail enquanto este ainda está sendo entregue.
  • Evidências: README.md:315-316 e core/registration/services.py:32.
  • Condições de ocorrência: Múltiplos workers Gunicorn (WEB_CONCURRENCY >
  1) com LocMemCache e envio duplicado de solicitação de código para o
  mesmo e-mail dentro de 60 segundos caindo em processos diferentes.
  • Justificativa do veredito: Condicional, restrito ao efeito de
  invalidação do primeiro código em submissões duplicadas entre workers.
  • Severidade revisada: Baixa (reduzida de Média para Baixa, pois a
  limitação por processo do LocMemCache é parte explícita do contrato
  documentado do projeto).
  • Correção recomendada: Verificar no banco de dados (sob o bloqueio
  select_for_update já existente) se já existe um OneTimeCode criado há
  menos de 60 segundos antes de substituí-lo, ou utilizar cache
  compartilhado.
  ──────
  ## 2. Falsos Positivos Refutados
  ──────
  ### [D-12] Inconsistência na revogação de sessão em memória
  (SessionService.revoke_all_sessions) e revogação no Admin ao salvar e-
  mail com caixa diferente
  • Identificação: D-12
  • Veredito: Falso positivo
  • Confiança: Alta
  • Localização:
      • SessionService.revoke_all_sessions (core/auth/services.py, linhas
      23–25)
      • CustomAdminPasswordChangeForm.save (core/admin.py, linhas 30–39)
      • UserAdmin.save_model (core/admin.py, linhas 156–163)
  • Análise e Evidências de Refutação:
      1. Sobre SessionService.revoke_all_sessions(user) não atualizar user.
      session_version em memória:
      Ao inspecionar django.contrib.auth.admin.UserAdmin.
      user_change_password e django.contrib.auth.update_session_auth_hash,
      constatou-se que, imediatamente após user = form.save(), o Django
      Admin executa:
	update_session_auth_hash(request, form.user)
      O qual grava request.session[HASH_SESSION_KEY] = user.
      get_session_auth_hash() quando request.user == user. Diferentemente
      de CustomAuthentication (usado na API DRF), o
      AuthenticationMiddleware / ModelBackend.get_user usado pelo Django
      Admin (/admin/) não verifica user.has_usable_password() — ele valida
      apenas is_active e o _auth_user_hash da sessão!
      Portanto, quando um administrador desabilita a própria senha em
      /admin/core/user/<admin.pk>/password/, o fato de SessionService.
      revoke_all_sessions(user) incrementar session_version no banco (1) e
      manter form.user.session_version em 0 na memória faz com que
      update_session_auth_hash grave o hash de session_version = 0 na
      sessão, garantindo que a sessão do administrador seja invalidada
      tanto na API quanto no próprio /admin/ (comportamento validado pelo
      teste test_admin_disabling_own_password_revokes_current_session). Se
      revoke_all_sessions atualizasse user.session_version em memória como
      sugerido na auditoria anterior, update_session_auth_hash gravaria o
      hash atualizado (session_version = 1) e manteria o administrador
      logado no /admin/ mesmo com senha desabilitada. Além disso, o retorno
      return user de PasswordResetService.confirm_reset não é utilizado por
      PasswordResetConfirmView.
      2. Sobre form.changed_data no Admin ao digitar e-mail com letras
      maiúsculas:
      Se um administrador edita manualmente o campo email no formulário do
      Django Admin alterando sua grafia, invalidar códigos pendentes e
      rotacionar session_version é um comportamento fail-safe sem qualquer
      impacto negativo de segurança ou estabilidade.
  • Justificativa do veredito: Refutado pela análise do ciclo interno de
  update_session_auth_hash no Django Admin.
  ──────
  ### [R-05] Retenção do cooldown de 60 segundos após falha SMTP e captura
  de exceções em PasswordResetService.request_reset

  • Identificação: R-05
  • Veredito: Falso positivo
  • Confiança: Alta
  • Localização:
      • PasswordResetService.request_reset (core/password_reset/services.py,
      linhas 20–51)
      • tests/test_issuance_logs.py:20-96 (tests/test_issuance_logs.py,
      linhas 20–96)
  • Análise e Evidências de Refutação:
      1. Por que PasswordResetService.request_reset captura Exception
      (incluindo erros de persistência em PasswordReset) e retorna 200 OK:
      Em PasswordResetService.request_reset (linhas 26–37), quando o e-mail
      não existe ou está inativo (if user is None or not user.
      has_usable_password(): return), a função retorna imediatamente na
      linha 32 sem executar PasswordReset.objects.filter(user=user).
      delete(), reset_code.save() ou send_email_token(). Se qualquer
      exceção lançada nas linhas 34–40 propagasse um erro 503 Service
      Unavailable, um atacante saberia com certeza que a conta existe e
      está ativa (pois contas inexistentes jamais passam da linha 32). Esse
      requisito de segurança é explicitamente testado e exigido em
      IssuanceLogSafetyTests.test_database_queue_and_cleanup_errors_do_not_
      log_secrets (("password-reset", PasswordReset, 200)) e em
      test_send_failure_does_not_disclose_account_or_leave_code.
      2. Por que o cooldown de 60 segundos por e-mail não é removido em
      caso de falha SMTP:
      Se falhas de envio SMTP limpassem o rate limit de 60s por e-mail,
      qualquer endereço cujo servidor de destino rejeitasse conexões ou
      estivesse lento permitiria que clientes disparassem novas conexões
      SMTP síncronas a cada 2 segundos, agravando o risco de exaustão de
      workers (R-01).
  • Justificativa do veredito: Refutado. O comportamento é intencional,
  defensivo e validado por testes específicos da suíte.
  ──────
  ### [R-06] Acoplamento entre healthcheck do Docker (Host: localhost),
  ALLOWED_HOSTS e server_name _; no Nginx

  • Identificação: R-06
  • Veredito: Falso positivo
  • Confiança: Alta
  • Localização:
      • docker-compose.yml:12 e linhas 42–47
      • README.md:305 (README.md, linha 305)
      • tests/test_email_templates.py:31-32
  • Análise e Evidências de Refutação:
      1. A inclusão de localhost em ALLOWED_HOSTS ao utilizar o docker-
      compose.yml não é uma suposição oculta: está documentada tanto na
      interpolação obrigatória de docker-compose.yml:12 (ALLOWED_HOSTS:
      ${ALLOWED_HOSTS:?Set the public hostname and localhost}) quanto nas
      instruções de implantação em README.md:305 ("Inclua localhost em
      ALLOWED_HOSTS para a verificação interna").
      2. A aceitação de Host: localhost pelo Nginx (server_name _;) não
      introduz vulnerabilidade de Host Header Injection / Poisoning neste
      projeto porque:
          • Os e-mails transacionais contêm apenas o código numérico de 6
          dígitos ({{ code }}) e não constroem links nem consultam request.
          get_host() (invariante verificada pelo teste
          tests/test_email_templates.py:31-32: self.assertNotIn("http://",
          html) e self.assertNotIn("https://", html)).
          • Os endpoints que geram URLs absolutas (UserListView) são
          decorados com @never_cache, impedindo envenenamento de cache.

  • Justificativa do veredito: Refutado. Não há caminho de exploração para
  Host Header Poisoning e o requisito de configuração está explicitamente
  documentado.
  ──────
  ### [R-07] Canal lateral de tempo em endpoints de confirmação e
  solicitação

  • Identificação: R-07
  • Veredito: Falso positivo
  • Confiança: Alta
  • Localização: README.md:313 (README.md, linha 313)
  • Análise e Evidências de Refutação: A seção 7 do README.md:313 explicita
  como limite conhecido do projeto:
  │ "- Enumeração: a recuperação retorna resposta uniforme, mas SMTP
  │ síncrono pode revelar diferenças de latência. Não há promessa de tempo
  │ constante."
  │ Além disso, nos endpoints de confirmação (confirm_registration e
  │ confirm_reset), o rate limit por IP (limit_code_verification_attempts:
  │ 15 requisições por minuto) restringe severamente a amostragem
  │ estatística de tempo pela rede.

  • Justificativa do veredito: Refutado por estar explicitamente fora do
  contrato de segurança declarado pela documentação do software.
  ──────
  ### [R-08] Gravação redundante de sessão em POST /api/login/ e execução
  de CustomAuthentication em endpoints públicos

  • Identificação: R-08
  • Veredito: Falso positivo
  • Confiança: Alta
  • Localização:
      • AuthService.login_user (core/auth/services.py, linhas 37–47)
      • CustomAuthentication.authenticate (core/auth/authenticate.py,
      linhas 5–13)
  • Análise e Evidências de Refutação:
      1. Em AuthService.login_user, request.session.save() dentro de
      transaction.atomic() garante que qualquer erro de banco na
      persistência da sessão reverta toda a transação de login. O UPDATE
      adicional executado por SessionMiddleware.process_response ao final
      do ciclo HTTP persiste os mesmos valores (session_data e expire_date),
      sendo idempotente e incapaz de produzir estado inconsistente.
      2. A execução de CustomAuthentication nas rotas AllowAny é o
      mecanismo arquitetural escolhido para exigir CSRF em todas as
      mutações públicas (# Public mutations need CSRF too, especially login
      and code issuance), e a segunda chamada a enforce_csrf dentro de
      super().authenticate(request) é inócua porque CsrfViewMiddleware.
      process_view é idempotente na mesma requisição.
  • Justificativa do veredito: Refutado. Não há erro de lógica, perda de
  integridade ou vulnerabilidade de segurança.
  ──────
  ### [R-09] Omissão de log de falha de segurança em DeactivateSelfView e
  classificação de eventos em LoginView

  • Identificação: R-09
  • Veredito: Falso positivo
  • Confiança: Alta
  • Localização:
      • DeactivateSelfView.post (core/users/views.py, linhas 101–107)
      • require_current_password (core/auth/rate_limit.py, linhas 57–74)
  • Análise e Evidências de Refutação: Ao rastrear o fluxo completo de
  DeactivateSelfView.post -> UserService.deactivate_user ->
  require_current_password, verifica-se que require_current_password já
  registra os eventos de segurança em todas as tentativas falhas ou
  bloqueadas de desativação:
      • Na linha 64 de core/auth/rate_limit.py: record_event("REAUTH",
      "BLOCKED")
      • Na linha 73 de core/auth/rate_limit.py: record_event("REAUTH",
      "FAILURE")
      Isso foi confirmado nos logs emitidos durante a execução de
      tests/test_users.py
      (test_deactivation_reauth_throttle_and_cache_failure). Ao contrário
      de EmailChangeConfirmView (que além da senha valida um código OTP e
      por isso registra EMAIL_CHANGE FAILURE quando o OTP falha),
      DeactivateSelfView valida apenas a senha atual, cuja falha já é
      coberta por REAUTH FAILURE / REAUTH BLOCKED.
  • Justificativa do veredito: Refutado. Os eventos de falha e bloqueio na
  desativação já são devidamente auditados pelo módulo core.auth.rate_limit.
  ──────
  ## 3. Problemas Inconclusivos e Verificações Adicionais Necessárias

  Nenhuma das 22 descobertas da auditoria anterior permaneceu com veredito
  inconclusivo; todas puderam ser confirmadas, condicionadas ou refutadas
  com base em evidências concretas do código e testes em memória.

  Todavia, permanecem dependentes de validação no ambiente de implantação
  final (fora do escopo estático do repositório):

  1. Execução da suíte concorrente contra PostgreSQL real (pdm run
  test:postgres): Os testes em AdminConcurrencyTests
  (tests/test_admin_security.py) e ProductionConcurrencyTests
  (tests/test_integration.py) exigem um serviço PostgreSQL em 127.0.0.
  1:5432 para validar o comportamento real de SELECT ... FOR NO KEY UPDATE.
  2. Topologia de domínios entre SPA e API (SameSite=None vs. bloqueio de
  cookies de terceiros): A configuração app/settings/prod.py utiliza
  SameSite=None; Secure. Caso a SPA e a API sejam publicadas em domínios
  registráveis distintos (cross-site), navegadores com restrição a cookies
  de terceiros bloquearão os cookies __Host-sessionid e __Host-csrftoken.
  3. Agendamento externo de manage.py cleanup_auth: O expurgo de sessões
  expiradas e cadastros abandonados depende de configuração de
  cron/scheduler na infraestrutura hospedeira.
  ──────
  ## 4. Descobertas Relacionadas ou com Mesma Causa Raiz

  A análise crítica identificou três grupos de descobertas que compartilham
  causas raiz ou interagem diretamente entre si:

  1. Materialização prematura de User não verificado (D-01 e D-08):
      • Ambos decorrem do fato de RegistrationService.request_registration
      usar a própria tabela core_user (User.objects.
      get_or_create(email=email, defaults={"is_active": False})) para
      armazenar solicitações de cadastro ainda não verificadas por e-mail.
      Isso causa tanto o bloqueio de EmailChangeService e
      CustomUserCreationForm (D-01) quanto a necessidade de expurgo
      periódico de linhas em core_user por cleanup_auth e a condição de
      corrida associada (D-08).
  2. Validação incompleta de limites e formato nos Serializers DRF (D-03,
  D-06 e D-09):
      • D-03 (domínios IDN vs. Punycode), D-06 (EmailField aceitando até
      320 caracteres contra varchar(254) no banco) e D-09 (CharField de
      senha sem max_length aceitando até 1 MB) têm a mesma origem
      estrutural: delegação excessiva aos padrões genéricos dos campos do
      DRF sem alinhar os limites e a normalização dos serializers às
      restrições do banco de dados e do backend SMTP.
  3. Arquitetura de concorrência dos processos workers e cache local (R-01,
  R-03 e D-04):
      • R-01 (bloqueio dos 2 workers sync por SMTP síncrono), R-03
      (isolamento do LocMemCache entre os 2 processos Gunicorn) e D-04
      (TOCTOU em require_current_password quando há acesso concorrente ao
      mesmo cache) são faces complementares do modelo de execução de
      workers e cache: enquanto o Gunicorn opera em modo sync (1 thread por
      processo) com LocMemCache, R-01 e R-03 estão ativos e D-04 fica
      latente; ao habilitar múltiplas threads (gthread) ou um cache
      compartilhado (Redis) para mitigar R-01 e R-03, a condição de corrida
      D-04 passa a ser imediatamente explorável se require_current_password
      não for corrigido.

  ──────
  ## 5. Resumo Quantitativo dos Vereditos

   ID   │ Título Resumido             │ Seve… │ Veredito d… │ Seve… │ Con…
  ──────┼─────────────────────────────┼───────┼─────────────┼───────┼──────
   D-01 │ Bloqueio de troca de e-mail │ Alta  │ Confirmado  │ Alta  │ Alta
        │ (Email Squatting) via       │       │             │       │
        │ registration/request/       │       │             │       │
   R-01 │ Exaustão dos workers sync   │ Alta  │ Condicional │ Alta  │ Alta
        │ do Gunicorn por envio SMTP  │       │             │       │
        │ síncrono                    │       │             │       │
   D-02 │ Enumeração de contas        │ Alta  │ Confirmado  │ Média │ Alta
        │ existentes via POST         │       │             │       │
        │ /api/email-change/request/  │       │             │       │
   D-03 │ Bypass de                   │ Alta  │ Confirmado  │ Média │ Alta
        │ normalização/unicidade de   │       │             │       │
        │ e-mail via domínios IDN vs. │       │             │       │
        │ Punycode                    │       │             │       │
   D-06 │ E-mails de 255–320 chars    │ Média │ Confirmado  │ Média │ Alta
        │ passam no serializer e      │       │             │       │
        │ causam DataError (HTTP 503) │       │             │       │
   D-09 │ Ausência de max_length em   │ Média │ Confirmado  │ Média │ Alta
        │ senhas permite payloads de  │       │             │       │
        │ 1 MB no PBKDF2              │       │             │       │
   D-04 │ Condição de corrida         │ Alta  │ Condicional │ Média │ Alta
        │ (TOCTOU) em                 │       │             │       │
        │ require_current_password    │       │             │       │
   D-05 │ Sobrescrita de              │ Alta  │ Condicional │ Média │ Alta
        │ is_active/email no Django   │       │             │       │
        │ Admin por formulário HTML   │       │             │       │
        │ defasado                    │       │             │       │
   R-02 │ Fallback para REMOTE_ADDR   │ Alta  │ Condicional │ Média │ Alta
        │ (IP do proxy) em            │       │             │       │
        │ get_client_ip               │       │             │       │
   R-04 │ Contabilização de logins    │ Média │ Condicional │ Média │ Alta
        │ válidos em login:ip         │       │             │       │
        │ bloqueia usuários sob NAT   │       │             │       │
   D-07 │ TransactionManagementError  │ Média │ Confirmado  │ Baixa │ Alta
        │ (HTTP 500) em               │       │             │       │
        │ UserAdmin.get_object via    │       │             │       │
        │ POST /history/              │       │             │       │
   D-11 │ Paginação não               │ Baixa │ Confirmado  │ Baixa │ Alta
        │ determinística em           │       │             │       │
        │ users/list/ e falta de      │       │             │       │
        │ índice em created_at        │       │             │       │
   D-13 │ Valores                     │ Baixa │ Confirmado  │ Baixa │ Alta
        │ inválidos/conflitantes em   │       │             │       │
        │ .env.example e              │       │             │       │
        │ DEFAULT_FROM_EMAIL vazio    │       │             │       │
   D-08 │ Corrida entre get_or_create │ Média │ Condicional │ Baixa │ Alta
        │ e select_for_update com     │       │             │       │
        │ cleanup_auth                │       │             │       │
   D-10 │ User.get_short_name() lança │ Baixa │ Condicional │ Baixa │ Alta
        │ IndexError para name só com │       │             │       │
        │ espaços via ORM             │       │             │       │
   R-03 │ Invalidação cruzada de OTP  │ Média │ Condicional │ Baixa │ Alta
        │ em reenvio rápido com       │       │             │       │
	│ LocMemCache e múltiplos     │       │             │       │
        │ workers                     │       │             │       │
   D-12 │ session_version em memória  │ Baixa │    Falso    │  N/A  │ Alta
        │ em revoke_all_sessions e    │       │  positivo   │       │
        │ caixa de e-mail no Admin    │       │             │       │
   R-05 │ Captura de exceções em      │ Média │    Falso    │  N/A  │ Alta
        │ PasswordResetService e      │       │  positivo   │       │
        │ retenção de cooldown de 60s │       │             │       │
   R-06 │ Host: localhost no          │ Baixa │    Falso    │  N/A  │ Alta
	│ healthcheck do Docker e     │       │  positivo   │       │
        │ server_name _; no Nginx     │       │             │       │
   R-07 │ Canal lateral de tempo em   │ Baixa │    Falso    │  N/A  │ Alta
        │ endpoints de solicitação e  │       │  positivo   │       │
	│ confirmação                 │       │             │       │
   R-08 │ Gravação extra de sessão no │ Baixa │    Falso    │  N/A  │ Alta
        │ login e                     │       │  positivo   │       │
        │ CustomAuthentication em     │       │             │       │
	│ rotas públicas              │       │             │       │
   R-09 │ Suposta omissão de log de   │ Baixa │    Falso    │  N/A  │ Alta
        │ falha em DeactivateSelfView │       │  positivo   │       │

  ### Totais por Veredito

  • Confirmados: 8
  • Condicionais: 8
  • Falsos Positivos: 6
  • Inconclusivos: 0
  • Total avaliado: 22