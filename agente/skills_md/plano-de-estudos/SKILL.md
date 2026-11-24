---
name: plano-de-estudos
description: Monta um plano de estudos personalizado para um perfil e uma cidade da Dataprev, juntando conteúdo programático, concorrência e cronograma até a prova. Use quando o usuário pedir plano de estudos, cronograma, rotina ou "por onde começar".
---

# Plano de estudos

Siga os passos na ordem. Não faça contas de data nem de horas: use as ferramentas.

1. **Dados do usuário.** Precisa de perfil (ex.: Desenvolvimento de Software), localidade (ex.: Natal) e horas de estudo por semana. Se faltar algum, faça uma única pergunta pedindo o que falta e pare até a resposta. O prazo até a prova não é um desses dados: ele é tratado no passo 2.
2. **Prazo até a prova.** Ele vem da data da prova ou do número de semanas até a prova. Nunca pergunte o prazo antes de seguir o que está abaixo.
   - Se o usuário informou uma data da prova, chame `get_current_time` com `timezone` "America/Sao_Paulo" para ter a data de hoje (AAAA-MM-DD), use a data informada, sem buscar datas no edital, e vá ao passo 3. Se informou também as semanas, vale a data.
   - Se informou só as semanas, use-as e vá ao passo 3, sem consultar a data de hoje nem o edital.
   - Se não informou nenhum dos dois, chame `get_current_time` e busque a data da prova com `search_dataprev` ("data de aplicação da prova objetiva", edital "2026"). Se a data encontrada for anterior a hoje (como 17/11/2024 e 11/10/2026), essa prova já aconteceu: responda só avisando isso e perguntando quantas semanas o usuário tem para estudar (ou a data prevista da próxima prova, se ele souber), e pare aqui. Não invente datas de provas futuras.
3. **Conteúdo.** Chame `search_dataprev` com o nome do perfil e "conteúdo programático" (edital "2026") e escolha no máximo cinco tópicos de Conhecimentos Específicos, com a fonte.
4. **Concorrência.** Chame `consultar_concorrencia` com edital "2026", o perfil e a localidade, e anote vagas, candidatos e candidatos por vaga.
5. **Cronograma.** Chame `montar_cronograma_estudo` com as horas por semana e edital "2026". Com data da prova, passe também `data_inicio` igual a hoje e `data_prova`; só com semanas, passe `semanas`. Se devolver erro, explique-o ao usuário.
6. **Resposta.** Use só os números que as ferramentas devolveram nos passos 4 e 5, que são obrigatórios; sem eles, não monte o plano. Em até doze linhas: concorrência, semanas até a prova, fases, horas por disciplina e os tópicos prioritários, com as fontes dos trechos. Termine perguntando: "Você tem mais facilidade ou dificuldade em alguma disciplina? Posso ajustar as horas."
7. **Ajuste.** Se o usuário citar disciplinas, chame `montar_cronograma_estudo` de novo com os mesmos dados e `dificuldades` e/ou `facilidades`. Mostre as horas novas e diga quais disciplinas ganharam ou perderam tempo (campo ajuste_do_aluno); se vier nao_reconhecidas, peça o nome correto. Se ele não quiser ajustar, mantenha o plano. Depois pergunte se quer salvar.
8. **Salvar.** Só se o usuário aceitar, chame `salvar_plano` com um nome simples como `plano-desenvolvimento-natal` e o plano em Markdown, e informe o arquivo salvo.