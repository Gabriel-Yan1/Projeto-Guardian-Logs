# Relatório do GUARDIAN LOGS

**Disciplina:** PROGRAMAÇÃO CONCORRENTE E DISTRIBUÍDA  
**Aluno(s):** GABRIEL YAN E MATEUS RECALDE  
**Professor:** RAFAEL MARCONI RAMOS  

---

## 1. Descrição do Problema

O programa resolve o problema de processamento massivo de arquivos de logs de rede (dataset CIC-DDoS2019) para identificar potenciais ataques de negação de serviço (DDoS).

* **Qual problema foi implementado:** Um analisador de tráfego que identifica os IPs de origem com maior volume de requisições e as portas de destino mais visadas.
* **Qual algoritmo foi utilizado:** Estratégia de **Map-Reduce** baseada em **Byte-Range Scanning**. O arquivo é fatiado em pedaços binários, e cada processo (Map) conta as ocorrências de forma independente. O processo principal (Reduce) consolida os dicionários parciais.
* **Dataset utilizado:** CIC-DDoS2019.
* **Fonte do dataset:** [Kaggle - CIC-DDoS2019](https://www.kaggle.com/datasets/rodrigorosasilva/cic-ddos2019-30gb-full-dataset-csv-files?select=01-12)
* **Tamanho da entrada:** 9.302,0 MB (aproximadamente 9,3 GB) — Arquivo `TFTP.csv`.
* **Objetivo da paralelização:** Reduzir o tempo de processamento de arquivos que excedem a capacidade de leitura sequencial eficiente do Python (devido ao GIL) e otimizar o uso de CPUs multi-core.

### Respostas

* **Objetivo:** Identificar os "Top IPs" atacantes em logs de DDoS.
* **Volume:** ~9,3 GB (milhões de linhas).
* **Algoritmo:** Map-Reduce com divisão por deslocamento de bytes (seek).
* **Complexidade:** **O(n/p)**, onde *n* é o número de linhas e *p* o número de processos, para a fase de Map. A fase de Reduce é **O(k)**, sendo *k* o número de IPs únicos.

---

## 2. Ambiente Experimental

| Item | Descrição |
|---|---|
| **Processador** | Intel Core i5-13400F |
| **Núcleos físicos** | 10 (6 P-Cores + 4 E-Cores) |
| **Threads lógicas** | 16 |
| **Memória RAM** | 32 GB DDR4 |
| **Sistema Operacional** | Windows 11 |
| **Linguagem utilizada** | Python 3.x |
| **Biblioteca de paralelização** | multiprocessing (`ProcessPoolExecutor`) |

---

## 3. Metodologia de Testes

* **Medição de tempo:** Utilizada a função `time.perf_counter()` para medir o tempo total desde o fatiamento do arquivo até a consolidação final.
* **Execuções:** Foram realizadas 3 execuções para cada configuração de workers.
* **Média:** Foi utilizada a média aritmética simples das três rodadas.
* **Entrada:** Arquivo `TFTP.csv` de 9,3 GB.

### Configurações Testadas

* 1 processo (serial)
* 2 processos
* 4 processos
* 8 processos
* 12 processos

### Procedimento Experimental

As execuções foram realizadas com carga mínima do sistema operacional, permitindo que o escalonador do Windows priorizasse os processos da aplicação. O modo `--bench` automatizou a coleta dos resultados.

---

## 4. Resultados Experimentais

| Nº Threads/Processos | Tempo de Execução (s) |
|---|---|
| **1 (Serial)** | 67.672 |
| **2** | 34.970 |
| **4** | 19.603 |
| **8** | 12.203 |
| **12** | 10.868 |

---

## 5. Cálculo de Speedup e Eficiência

### Fórmulas Utilizadas

> **Speedup**
> `Speedup(p) = T(1) / T(p)`
> Onde:
> * `T(1)` = tempo da execução serial
> * `T(p)` = tempo utilizando `p` processos

> **Eficiência**
> `Eficiência(p) = Speedup(p) / p`
> Onde:
> * `p` = número de processos utilizados

---

## 6. Tabelas de Resultados

### Resultados Consolidados

| Processos | Tempo (s) | Speedup | Eficiência |
|---|---|---|---|
| **1** | 67,67 | 1,00 | 100,0% |
| **2** | 34,97 | 1,93 | 96,8% |
| **4** | 19,60 | 3,45 | 86,3% |
| **8** | 12,20 | 5,54 | 69,3% |
| **12** | 10,86 | 6,22 | 51,9% |

### Comparação entre Speedup Ideal e Obtido

| Processos | Speedup Ideal | Speedup Obtido | Eficiência |
|---|---|---|---|
| **2** | 2,00x | 1,93x | 96,8% |
| **4** | 4,00x | 3,45x | 86,3% |
| **8** | 8,00x | 5,54x | 69,3% |
| **12** | 12,00x | 6,22x | 51,9% |

---

## 7. Gráfico de Tempo de Execução
*(Espaço reservado para o gráfico)*

## 8. Gráfico de Speedup
*(Espaço reservado para o gráfico)*

## 9. Gráfico de Eficiência
*(Espaço reservado para o gráfico)*

---

## 10. Análise dos Resultados

### O Speedup Obtido Foi Próximo do Ideal?
* A execução com 2 processos apresentou speedup de aproximadamente 1,93x, alcançando **96,8% de eficiência**, resultado muito próximo do ideal teórico de 2,0x.
* Com 4 processos, o speedup atingiu 3,45x, mantendo uma eficiência elevada de **86,3%**.
* Entretanto, a partir de 8 processos, o crescimento do speedup passou a ser significativamente menor do que o esperado. Com 8 processos foi obtido speedup de apenas 5,54x (ideal 8,0x). Já com 12 processos, alcançou apenas 6,22x (ideal 12,0x).

> Isso indica que a aplicação deixa de escalar linearmente devido à presença de gargalos de hardware e overheads inerentes à paralelização.

### A Aplicação Apresentou Escalabilidade?
**Sim.** A aplicação apresentou escalabilidade positiva ao reduzir o tempo de execução de aproximadamente 67,67 segundos para apenas 10,86 segundos. O ganho total foi de aproximadamente **6,22 vezes** em relação à execução serial.

Entretanto, a escalabilidade observada é **sublinear**. Por exemplo:
* De 1 para 2 processos houve redução de aproximadamente **32,7 segundos**.
* De 2 para 4 processos houve redução de aproximadamente **15,4 segundos**.
* De 4 para 8 processos houve redução de aproximadamente **7,4 segundos**.
* De 8 para 12 processos houve redução de apenas **1,3 segundo**.

Esse comportamento caracteriza retornos decrescentes, comuns em aplicações paralelas.

### Em Qual Ponto a Eficiência Começou a Cair?
A eficiência permaneceu elevada até 4 processos. A queda mais significativa ocorreu após esse limite:

| Processos | Eficiência |
|---|---|
| **2** | 96,8% |
| **4** | 86,3% |
| **8** | 69,3% |
| **12** | 51,9% |

Isso sugere que o hardware utilizado consegue aproveitar muito bem até quatro processos paralelos. A partir desse ponto, os gargalos do sistema passam a consumir uma parcela cada vez maior do tempo.

### Por Que o Speedup de 8 e 12 Processos Está Tão Baixo?
Esta foi a principal observação dos experimentos. Os ganhos deixam de crescer proporcionalmente pelos seguintes fatores:

* **a) Lei de Amdahl:** O speedup máximo é limitado pela parcela serial. No Guardian Logs, a etapa Map é altamente paralelizável, porém a etapa Reduce é executada de forma sequencial pelo processo principal, limitando o speedup máximo.
* **b) Gargalo de I/O:** Todos os workers acessam simultaneamente o mesmo arquivo de 9,3 GB. Com 8 ou 12 processos, o volume de leituras simultâneas provoca contenção de I/O no disco. A aplicação torna-se híbrida entre *CPU-Bound* e *I/O-Bound*.
* **c) Arquitetura Híbrida do Intel Core i5-13400F:** Possui 6 *P-Cores* (alta performance) e 4 *E-Cores* (alta eficiência, mas mais lentos). Usar 8 ou 12 processos aloca workers nos E-Cores, gerando desbalanceamento de carga, pois alguns concluem o processamento antes dos outros.
* **d) Hyper-Threading e Contenção de Cache:** São 16 threads lógicas, mas apenas 10 núcleos físicos. Com 12 processos, workers compartilham os mesmos recursos internos (Cache L1, L2, L3, unidades de execução). A intensa manipulação de strings/dicionários aumenta a taxa de *cache miss*, elevando a latência.
* **e) Overhead de Comunicação Entre Processos (IPC):** Os resultados parciais (dicionários) precisam ser enviados ao processo principal usando *Pickle* (serialização/desserialização). O custo dessa comunicação cresce com o número de processos e de dados.
* **f) Desbalanceamento de Carga:** Apesar de fatias de tamanho semelhante em bytes, elas podem conter volumes diferentes de dados reais (mais linhas, IPs ou portas distintas). O tempo final é determinado pelo worker mais lento.

### Conclusão da Análise
A estratégia de paralelização foi extremamente eficiente até 4 processos (>85% de eficiência). A partir de 8 processos, a combinação de limitações de I/O, overhead de IPC, arquitetura híbrida do processador, contenção de cache e a Lei de Amdahl impede o crescimento linear do speedup. 

Mesmo a configuração com 12 processos entregando o menor tempo absoluto (10,86 s), sua eficiência de **51,9%** demonstra que quase metade da capacidade computacional adicional foi consumida por overhead.

---

## 11. Conclusão

O projeto demonstrou que técnicas de programação concorrente e distribuída podem reduzir drasticamente o tempo de processamento de grandes volumes de dados. O paralelismo proporcionou um speedup máximo de aproximadamente **6,22x**, reduzindo o tempo de execução de 67,67 segundos para 10,86 segundos.

A melhor configuração em termos de tempo absoluto foi a de **12 processos**. Contudo, visando a eficiência computacional e aproveitamento do hardware, as configurações com **2 e 4 processos** apresentaram a melhor relação custo-benefício.

### Melhorias Futuras

* Utilização de bibliotecas como **Polars** ou **PyArrow** para acelerar a leitura de arquivos CSV.
* Uso de **SharedMemory** para reduzir o custo de serialização via IPC.
* Implementação de **balanceamento dinâmico de carga**.
* Utilização de `mmap()` para otimizar o acesso direto ao arquivo em disco.
* Paralelização da etapa de Reduce através de estratégias hierárquicas de agregação (Tree Reduction).

> Conclui-se que a abordagem **Map-Reduce** baseada em **Byte-Range Scanning** mostrou-se altamente adequada, tornando viável o processamento de bilhões de bytes em tempos compatíveis com aplicações reais de monitoramento e segurança.
