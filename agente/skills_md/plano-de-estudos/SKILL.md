---
name: plano-de-estudos
description: Monta um plano de estudos personalizado para um perfil e uma cidade da Dataprev, juntando conteúdo programático, concorrência e cronograma até a prova. Use quando o usuário pedir plano de estudos, cronograma, rotina ou "por onde começar".
---

# Plano de estudos

Siga os passos na ordem. Não faça contas de data nem de horas: use as ferramentas.

1. **Dados do usuário.** Precisa de perfil (ex.: Desenvolvimento de Software), localidade (ex.: Natal) e horas de estudo por semana. Se faltar algum, faça uma única pergunta pedindo o que falta e pare até a resposta.
2. **Hoje.** Chame `get_current_time` com `timezone` "America/Sao_Paulo" e guarde a data de hoje no formato AAAA-MM-DD.
3. **Data da prova.** Se o usuário informou, use a dele. Se não, busque com `search_dataprev` ("data de aplicação da prova objetiva", edital "2026").
   - Se a data encontrada for anterior a hoje, essa prova já aconteceu: avise isso e peça uma data prevista para a próxima prova. Não invente datas de provas futuras.
4. **Conteúdo.** Chame `search_dataprev` com o nome do perfil e "conteúdo programático" (edital "2026") e escolha no máximo cinco tópicos de Conhecimentos Específicos, com a fonte.
5. **Concorrência.** Chame `consultar_concorrencia` com edital "2026", o perfil e a localidade, e anote vagas, candidatos e candidatos por vaga.
6. **Cronograma.** Chame `montar_cronograma_estudo` com `data_inicio` igual a hoje, a data da prova, as horas por semana e edital "2026". Se devolver erro, explique-o ao usuário.
7. **Resposta.** Em até doze linhas: concorrência, semanas até a prova, fases, horas por disciplina e os tópicos prioritários, com as fontes dos trechos. Termine perguntando: "Você tem mais facilidade ou dificuldade em alguma disciplina? Posso ajustar as horas."
8. **Ajuste.** Se o usuário citar disciplinas, chame `montar_cronograma_estudo` de novo com os mesmos dados e `dificuldades` e/ou `facilidades`. Mostre as horas novas e diga quais disciplinas ganharam ou perderam tempo (campo ajuste_do_aluno); se vier nao_reconhecidas, peça o nome correto. Se ele não quiser ajustar, mantenha o plano. Depois pergunte se quer salvar.
9. **Salvar.** Só se o usuário aceitar, chame `salvar_plano` com um nome simples como `plano-desenvolvimento-natal` e o plano em Markdown, e informe o arquivo salvo.