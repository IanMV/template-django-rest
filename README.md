# Aplicação de autenticação

Esta aplicação cuida do cadastro, entrada, recuperação de senha, troca de e-mail, sessões em dispositivos e registros de segurança de uma conta.

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

010.RNF O ambiente em contêiner inicia a aplicação, PostgreSQL e Redis, guarda seus dados em volumes e verifica se banco e Redis estão disponíveis antes de iniciar a aplicação. (Dados: contêiner da aplicação; PostgreSQL; Redis; volumes; verificação de disponibilidade;)

011.RNF O ambiente em contêiner fornecido é para integração local. Ele não executa o processo de envio de e-mails nem a manutenção diária. (Dados: servidor de tarefas; agendador diário; **a confirmar** a forma de implantação desses processos;)

012.RNF O ambiente em contêiner fornecido não é uma implantação web de produção. A aplicação usa o servidor de desenvolvimento e depende de HTTPS externo para autenticação em navegador. (Dados: servidor web de produção; proxy HTTPS; **a confirmar** a escolha desses componentes;)

013.RNF A leitura dos registros de auditoria pela aplicação não impede alteração direta no banco de dados. (Dados: permissões do banco; política de retenção; **a confirmar** responsabilidade legal e configuração de escrita imutável;)
