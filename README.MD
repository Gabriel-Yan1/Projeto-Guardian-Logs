BANCO DE DADOS: https://www.kaggle.com/datasets/rodrigorosasilva/cic-ddos2019-30gb-full-dataset-csv-files?select=01-12

---

# Relatório do GUARDIAN LOGS

* **Disciplina:** PROGRAMAÇÃO CONCORRENTE E DISTRIBUÍDA 
* **Aluno(s):** GABRIEL YAN E MATEUS RECALDE 
* **Professor:** RAFAEL MARCONI RAMOS

---

# 1. Descrição do Problema

O programa resolve o problema de processamento massivo de arquivos de logs de rede (dataset CIC-DDoS2019) para identificar potenciais ataques de negação de serviço (DDoS).

* *Qual problema foi implementado:* Um analisador de tráfego que identifica os IPs de origem com maior volume de requisições e as portas de destino mais visadas.
* *Qual algoritmo foi utilizado:* Estratégia de *Map-Reduce* baseada em *Byte-Range Scanning*. O arquivo é fatiado em pedaços binários, e cada processo (Map) conta as ocorrências de forma independente. O processo principal (Reduce) consolida os dicionários parciais.
* *Tamanho da entrada:* 9.302,0 MB (aproximadamente 9.3 GB) — Arquivo TFTP.csv.
* *Objetivo da paralelização:* Reduzir o tempo de processamento de arquivos que excedem a capacidade de leitura sequencial eficiente do Python (devido ao GIL) e otimizar o uso de CPUs multi-core.

*Respostas:*
* *Objetivo:* Identificar os "Top IPs" atacantes em logs de DDoS.
* *Volume:* ~9.3 GB (milhões de linhas).
* *Algoritmo:* Map-Reduce com divisão por deslocamento de bytes (seek).
* *Complexidade:* $O(n/p)$, onde $n$ é o número de linhas e $p$ o número de processos, para a fase de Map. A fase de Reduce é $O(k)$, sendo $k$ o número de IPs únicos.

---

# 2. Ambiente Experimental

| Item                        | Descrição                             |
| --------------------------- | ------------------------------------- |
| Processador                 | i5-13400F (10 Cores / 16 Threads)     |
| Número de núcleos           | 16 núcleos                            |
| Memória RAM                 | 32 GB DDR4                            |
| Sistema Operacional         | Windows 11                            |
| Linguagem utilizada         | Python 3.x                            |
| Biblioteca de paralelização | multiprocessing (ProcessPoolExecutor) |

---

# 3. Metodologia de Testes

* *Medição de tempo:* Utilizada a função time.perf_counter() para medir o tempo total desde o fatiamento do arquivo até a consolidação final.
* *Execuções:* Foram realizadas *3 execuções* para cada configuração de workers.
* *Média:* Foi utilizada a média aritmética simples das três rodadas.
* *Entrada:* Arquivo TFTP.csv de 9.3 GB.

### Configurações testadas
* 1 (Serial), 2, 4, 8 e 12 processos.

### Procedimento experimental
As execuções foram feitas em máquina com carga mínima de sistema, garantindo que o escalonador do Windows pudesse priorizar os processos do analisador. O modo --bench automatizou a coleta dos dados.

---

# 4. Resultados Experimentais

| Nº Threads/Processos | Tempo de Execução (s) |
| -------------------- | --------------------- |
| 1 (Serial)           | 67.672                |
| 2                    | 34.970                |
| 4                    | 19.603                |
| 8                    | 12.203                |
| 12                   | 10.868                |

---

# 5. Cálculo de Speedup e Eficiência

## Fórmulas Utilizadas

### Speedup

```
Speedup(p) = T(1) / T(p)
```

Onde:

* **T(1)** = tempo da execução serial
* **T(p)** = tempo com p threads/processos

### Eficiência

```
Eficiência(p) = Speedup(p) / p
```

Onde:

* **p** = número de threads ou processos

---

# 6. Tabela de Resultados

| Threads/Processos | Tempo (s) | Speedup | Eficiência |
| ----------------- | --------- | ------- | ---------- |
| 1                 | 67.6728   | 1.0000  | 100.0%     |
| 2                 | 34.9702   | 1.9352  | 96.8%      |
| 4                 | 19.6031   | 3.4522  | 86.3%      |
| 8                 | 12.2030   | 5.5456  | 69.3%      |
| 12                | 10.8680   | 6.2268  | 51.9%      |

---

# 7. Gráfico de Tempo de Execução

![Gráfico Tempo Execução](graficos/tempo_execucao.png)

---

# 8. Gráfico de Speedup

![Gráfico Speedup](graficos/speedup.png)

---

# 9. Gráfico de Eficiência

![Gráfico Eficiência](graficos/eficiencia.png)

---

# 10. Análise dos Resultados

* *O speedup obtido foi próximo do ideal?* Até 2 processos sim (96.8%). A partir de 4 processos, começou a haver um distanciamento da linha ideal, embora o ganho de tempo ainda fosse expressivo.
* *A aplicação apresentou escalabilidade?* Sim, o tempo caiu de 67s para 10s. No entanto, a escalabilidade é sublinear.
* *Em qual ponto a eficiência começou a cair?* A queda acentuada iniciou após 4 processos (caindo de 86% para 69% com 8).
* *O número de threads ultrapassa o núcleo físico?* Sim. O i5-1235U possui 2 núcleos de performance (P) e 8 de eficiência (E). Ao usar 12 workers, o sistema utiliza núcleos de menor desempenho e hyper-threading, o que explica a queda na eficiência.
* *Overhead de paralelização:* Houve overhead significativo na comunicação entre processos (IPC) para transferir os dicionários de resultados via Pickle, além da contenção de I/O no disco para ler 9.3GB em tão pouco tempo.

*Gargalos identificados:*
1. *I/O de Disco:* Ler a ~850 MB/s satura a maioria dos SSDs NVMe de entrada.
2. *Arquitetura Híbrida Intel:* A diferença de potência entre núcleos P e E causa desbalanceamento de carga (um worker termina muito antes do outro).
3. *Fase de Reduce:* Unir dicionários no processo pai é uma tarefa serial.

---

# 11. Conclusão

* *Ganho de desempenho:* O paralelismo trouxe um ganho drástico, reduzindo o tempo de análise em *6.2x*.
* *Melhor configuração:* Em termos de tempo absoluto, *12 processos. Em termos de eficiência de hardware, **2 ou 4 processos*.
* *Escalabilidade:* O programa escala bem para grandes volumes de dados, mas é limitado pelo hardware (disco e topologia da CPU).
* *Melhorias:* Para melhorar a eficiência, poderíamos utilizar bibliotecas como Polars ou PyArrow para parsing mais rápido das strings ou usar memória compartilhada (SharedMemory) para evitar a serialização de dicionários grandes.

---
