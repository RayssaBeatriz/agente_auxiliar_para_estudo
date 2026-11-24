---
name: diagnostico-de-desempenho
description: Diagnostica o desempenho do aluno a partir dos acertos em um simulado ou estimativa, calcula a nota, compara com os resultados reais dos concursos da Dataprev e indica o que reforçar. Use quando o usuário informar acertos por disciplina, pedir para simular a nota ou perguntar se passaria.
---

# Diagnóstico de desempenho

Não faça contas de nota nem de posição: use as ferramentas.

1. **Dados.** Precisa de perfil (ex.: Desenvolvimento de Software), localidade (ex.: Natal) e do número de acertos em cada uma das seis disciplinas: Língua Portuguesa, Língua Inglesa, Raciocínio Lógico, Atualidades, Legislação de Segurança e Proteção de Dados, Conhecimentos Específicos. Se faltar algo, faça uma única pergunta pedindo o que falta e pare até a resposta.
2. **Nota.** Chame `simular_nota` com os acertos e edital "2026".
3. **Se não for aprovado.** Se `aprovado_na_prova_objetiva` for falso, diga que a nota está abaixo do limiar de habilitação ou que há disciplina zerada, com os motivos e `pontos_que_faltam`. Não estime posição. Vá ao passo 5.
4. **Se for aprovado.** Chame `estimar_posicao` uma única vez, com a nota, o perfil, a localidade e edital "todos", que devolve a estimativa de 2026 e a de 2024. Apresente os dois concursos. Informe a posição estimada, quantos habilitados há, a nota da última vaga e se a nota fica dentro, no limite ou fora das vagas. Avise que o resultado de 2026 é provisório, que "vagas" inclui cadastro de reserva e que a posição é entre habilitados, sem separar cotas. Se a ferramenta pedir um perfil mais específico, mostre as opções e pergunte.
5. **Ponto fraco.** Identifique a disciplina com menor proporção de acertos. Chame `search_dataprev` com o nome dela e "conteúdo programático" (edital "2026") e liste no máximo três tópicos, com a fonte.
6. **Resposta.** Em até dez linhas, nesta ordem: nota e situação (habilitado ou não); se habilitado, uma linha para 2026, marcada como "resultado provisório", com posição, número de habilitados, vagas e nota da última vaga, e uma linha para 2024 com os mesmos dados (a resposta precisa trazer os dois concursos); a disciplina a reforçar e os tópicos, com a fonte. Termine oferecendo montar um cronograma que dê mais horas a essa disciplina; se o usuário aceitar, carregue a skill plano-de-estudos com `load_skill` e informe a disciplina como dificuldade.
