"""
╔══════════════════════════════════════════════════════════════════════════╗
║   Analisador Paralelo de Logs de DDoS — CIC-DDoS2019                     ║
║   Programação Paralela e Distribuída                                     ║
╠══════════════════════════════════════════════════════════════════════════╣
║   Modelo       : Memória Compartilhada                                   ║
║   Paralelismo  : multiprocessing (ProcessPoolExecutor)                   ║
║   Estratégia   : Map-Reduce por byte-ranges (sem GIL)                    ║
║   Dataset      : CIC-DDoS2019 (Kaggle)                                   ║
╠══════════════════════════════════════════════════════════════════════════╣
║   Como usar:                                                             ║
║     python ddos_analyzer.py -f TFTP.csv                                  ║
║     python ddos_analyzer.py -f TFTP.csv --bench                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

import os, sys, csv, time, json, argparse, logging
import numpy as np
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO,
                    format="[%(asctime)s] %(levelname)s  %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
#  DETECÇÃO AUTOMÁTICA DE COLUNAS
# ══════════════════════════════════════════════════════════════════════════════
_IP_ORIG  = [" Source IP","Source IP","src ip","src_ip","source_ip","srcip"]
_PORT_DST = [" Destination Port","Destination Port","dst port","dst_port","dport"]
_IP_DST   = [" Destination IP","Destination IP","dst ip","dst_ip"]
_PROTO    = [" Protocol","Protocol","protocol","proto"]
_LABEL    = [" Label","Label","label","class","type","attack"]

def detectar_colunas(header_line: str) -> Dict[str, Optional[int]]:
    """Detecta índices de colunas relevantes a partir do cabeçalho CSV."""
    raw  = header_line.strip().split(",")
    norm = {c.strip().lower(): i for i, c in enumerate(raw)}
    def _achar(cands):
        for c in cands:
            idx = norm.get(c.strip().lower())
            if idx is not None: return idx
        return None
    return {
        "ip_origem"    : _achar(_IP_ORIG),
        "porta_destino": _achar(_PORT_DST),
        "ip_destino"   : _achar(_IP_DST),
        "protocolo"    : _achar(_PROTO),
        "label"        : _achar(_LABEL),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  DIVISÃO POR BYTE-RANGE
# ══════════════════════════════════════════════════════════════════════════════
def dividir_arquivo(filepath: str, n_workers: int) -> List[Dict]:
    """Divide o CSV em n byte-ranges, detectando colunas uma única vez."""
    with open(filepath, "rb") as fb:
        header_raw   = fb.readline()
        after_header = fb.tell()
    col_map   = detectar_colunas(header_raw.decode("utf-8", errors="replace"))
    file_size = os.path.getsize(filepath)
    data_size = file_size - after_header
    chunk     = max(data_size // n_workers, 1)
    return [
        {
            "filepath"  : filepath,
            "start_byte": after_header + i * chunk,
            "end_byte"  : after_header + (i+1)*chunk if i < n_workers-1 else file_size,
            "col_map"   : col_map,
        }
        for i in range(n_workers)
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  WORKER (MAP) — deve ficar no escopo do módulo para ser serializável
# ══════════════════════════════════════════════════════════════════════════════
def _worker_map(args: Dict) -> Dict[str, Dict]:
    """
    Processa um byte-range e conta hits por (IP de origem, porta de destino).
    Roda em processo independente — sem GIL, CPU dedicada.

    Retorna: { '192.168.1.5': {80: 150, 53: 89}, ... }
    """
    filepath   = args["filepath"]
    start_byte = args["start_byte"]
    end_byte   = args["end_byte"]
    col_map    = args["col_map"]
    idx_ip     = col_map.get("ip_origem") or 0
    idx_port   = col_map.get("porta_destino")

    local: Dict[str, Dict] = {}
    try:
        with open(filepath, "rb") as fb:
            fb.seek(start_byte)
            if start_byte > 0:
                fb.readline()           # descarta linha cortada ao meio
            while fb.tell() < end_byte:
                raw = fb.readline()
                if not raw: break
                parts = raw.decode("utf-8", errors="replace").strip().split(",")
                if idx_ip >= len(parts): continue
                ip = parts[idx_ip].strip().strip('"')
                if not ip or "ip" in ip.lower(): continue   # pula cabeçalhos repetidos
                porta = -1
                if idx_port is not None and idx_port < len(parts):
                    try: porta = int(float(parts[idx_port].strip()))
                    except ValueError: pass
                if ip not in local: local[ip] = {}
                local[ip][porta] = local[ip].get(porta, 0) + 1
    except Exception:
        pass
    return local


# ══════════════════════════════════════════════════════════════════════════════
#  REDUCE — mescla resultados dos workers
# ══════════════════════════════════════════════════════════════════════════════
def _reduce(resultados: List[Dict]) -> Dict[str, Dict]:
    """Une os contadores parciais de todos os processos."""
    total: Dict[str, Dict] = {}
    for parcial in resultados:
        for ip, portas in parcial.items():
            if ip not in total: total[ip] = {}
            for porta, hits in portas.items():
                total[ip][porta] = total[ip].get(porta, 0) + hits
    return total


# ══════════════════════════════════════════════════════════════════════════════
#  CLASSE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
class DDoSAnalyzer:
    """
    Analisa logs do CIC-DDoS2019 contando hits por IP e porta.

    Fluxo Map-Reduce:
      dividir_arquivo() → ProcessPoolExecutor.map(_worker_map) → _reduce()
    """

    def __init__(self, n_workers: int = None, top_n: int = 20):
        self.n_workers = n_workers or cpu_count()
        self.top_n     = top_n
        self._dados: Dict[str, Dict] = {}   # {ip: {porta: hits}}

    # ── Análise de arquivo ───────────────────────────────────────────────────
    def analisar_arquivo(self, filepath: str, silencioso: bool = False) -> Dict:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Não encontrado: {filepath}")

        if not silencioso:
            log.info(f"Arquivo  : {path.name}  ({path.stat().st_size/1e6:.1f} MB)")
            log.info(f"Workers  : {self.n_workers} processos")

        chunks = dividir_arquivo(str(path), self.n_workers)
        t0     = time.perf_counter()

        # ── MAP ──
        with ProcessPoolExecutor(max_workers=self.n_workers) as ex:
            parciais = list(ex.map(_worker_map, chunks))

        # ── REDUCE ──
        resultado = _reduce(parciais)
        elapsed   = time.perf_counter() - t0

        # Acumula no estado global (suporte a múltiplos arquivos)
        for ip, portas in resultado.items():
            if ip not in self._dados: self._dados[ip] = {}
            for porta, hits in portas.items():
                self._dados[ip][porta] = self._dados[ip].get(porta, 0) + hits

        total_hits = sum(sum(p.values()) for p in resultado.values())
        if not silencioso:
            log.info(f"Concluído: {elapsed:.3f}s | IPs: {len(resultado):,} | Hits: {total_hits:,}")
        return {"tempo": elapsed, "ips": len(resultado), "hits": total_hits}

    # ── Análise de diretório ─────────────────────────────────────────────────
    def analisar_diretorio(self, dirpath: str, padrao: str = "*.csv"):
        arqs = sorted(Path(dirpath).glob(padrao))
        if not arqs: raise FileNotFoundError(f"Nenhum {padrao} em {dirpath}")
        log.info(f"{len(arqs)} arquivo(s) encontrado(s)")
        for a in arqs: self.analisar_arquivo(str(a))

    # ── Resumo por IP ────────────────────────────────────────────────────────
    def _resumo(self) -> List[Dict]:
        res = []
        for ip, portas in self._dados.items():
            total = sum(portas.values())
            top_p = max(portas, key=portas.get) if portas else -1
            res.append({
                "ip_origem"         : ip,
                "total_hits"        : total,
                "portas_unicas"     : len(portas),
                "porta_mais_atacada": top_p,
                "lista_portas"      : sorted(p for p in portas if p != -1),
            })
        return sorted(res, key=lambda x: x["total_hits"], reverse=True)

    def top_ips(self, n: int = None) -> List[Dict]:
        return self._resumo()[: n or self.top_n]

    # ── Sumário no terminal ──────────────────────────────────────────────────
    def imprimir_sumario(self):
        top   = self.top_ips()
        total = sum(sum(p.values()) for p in self._dados.values())
        print("\n" + "═"*72)
        print(f"  SUMÁRIO — TOP {self.top_n} IPs ATACANTES")
        print("═"*72)
        print(f"  {'#':<5} {'IP de Origem':<22} {'Hits':>10} {'Portas':>8} {'Porta Principal':>17}")
        print("─"*72)
        for i, r in enumerate(top, 1):
            print(f"  {i:<5} {r['ip_origem']:<22} {r['total_hits']:>10,} "
                  f"{r['portas_unicas']:>8} {r['porta_mais_atacada']:>17}")
        print("═"*72)
        print(f"  IPs únicos : {len(self._dados):>8,}")
        print(f"  Total hits : {total:>8,}")
        print("═"*72 + "\n")

    # ── Salvar relatórios ────────────────────────────────────────────────────
    def salvar_relatorios(self, prefixo: str = "ddos"):
        resumo = self._resumo()
        total  = sum(r["total_hits"] for r in resumo)

        # JSON completo
        json_path = f"{prefixo}_relatorio.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"total_ips": len(resumo), "total_hits": total,
                       "n_workers": self.n_workers, "resultados": resumo},
                      f, indent=2, ensure_ascii=False)

        # CSV resumo por IP
        csv1 = f"{prefixo}_resumo_por_ip.csv"
        with open(csv1, "w", newline="", encoding="utf-8") as f:
            campos = ["ip_origem","total_hits","portas_unicas",
                      "porta_mais_atacada","lista_portas"]
            w = csv.DictWriter(f, fieldnames=campos)
            w.writeheader()
            for r in resumo: w.writerow({k: r[k] for k in campos})

        # CSV detalhado IP × porta
        csv2  = f"{prefixo}_contagem_ip_porta.csv"
        linhas = sorted(
            [{"ip_origem": ip, "porta_destino": p, "hits": h}
             for ip, portas in self._dados.items()
             for p, h in portas.items()],
            key=lambda x: x["hits"], reverse=True
        )
        with open(csv2, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["ip_origem","porta_destino","hits"])
            w.writeheader(); w.writerows(linhas)

        log.info(f"Relatórios → {json_path}, {csv1}, {csv2}")


# ══════════════════════════════════════════════════════════════════════════════
#  BENCHMARK
# ══════════════════════════════════════════════════════════════════════════════
CONFIGS_BENCH = [1, 2, 4, 8, 12]
REPETICOES    = 3

def executar_benchmark(filepath: str):
    """
    Mede tempo com diferentes números de workers.
    1 worker = execução serial (baseline)
    Speedup(p) = T(1)/T(p)    Eficiência(p) = Speedup(p)/p
    """
    max_cpu = cpu_count()
    configs = sorted(set(c for c in CONFIGS_BENCH if c <= max_cpu + 1))
    tam_mb  = os.path.getsize(filepath) / 1e6

    print(f"\n{'═'*65}")
    print(f"  BENCHMARK — {REPETICOES} execuções por configuração")
    print(f"  Arquivo : {Path(filepath).name}  ({tam_mb:.1f} MB)")
    print(f"  CPUs    : {max_cpu} disponíveis")
    print(f"  Nota    : 1 worker = execução SERIAL (referência)")
    print(f"{'═'*65}\n")

    medias: Dict[int, float] = {}
    for w in configs:
        tempos = []
        modo = "(SERIAL — baseline)" if w == 1 else f"(paralelo)"
        print(f"  ── {w} worker(s) {modo}")
        for r in range(REPETICOES):
            print(f"     rodada {r+1}/{REPETICOES}...", end=" ", flush=True)
            a = DDoSAnalyzer(n_workers=w)
            t0 = time.perf_counter()
            a.analisar_arquivo(filepath, silencioso=True)
            dt = time.perf_counter() - t0
            tempos.append(dt)
            print(f"{dt:.3f}s")
        medias[w] = float(np.mean(tempos))
        print(f"     → média: {medias[w]:.4f}s\n")

    # Tabela final
    t1 = medias[configs[0]]
    linhas = []
    print(f"{'─'*63}")
    print(f"  {'Workers':>8}  {'Modo':<10}  {'Tempo(s)':>10}  {'Speedup':>9}  {'Eficiência':>11}")
    print(f"{'─'*63}")
    for w, tp in medias.items():
        sp   = t1 / tp
        ef   = sp / w
        modo = "serial" if w == 1 else "paralelo"
        print(f"  {w:>8}  {modo:<10}  {tp:>10.4f}  {sp:>9.4f}  {ef:>10.1%}")
        linhas.append({"workers": w, "modo": modo, "tempo_s": round(tp,6),
                       "speedup": round(sp,4), "eficiencia": round(ef,4)})
    print(f"{'─'*63}\n")

    with open("benchmark_resultado.csv","w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["workers","modo","tempo_s","speedup","eficiencia"])
        w.writeheader(); w.writerows(linhas)
    log.info("Tabela salva: benchmark_resultado.csv")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════
def main():
    p = argparse.ArgumentParser(
        prog="ddos_analyzer.py",
        description="Analisador Paralelo de Logs de DDoS — CIC-DDoS2019",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python ddos_analyzer.py -f DrDoS_SNMP.csv
  python ddos_analyzer.py -d pasta_csvs/
  python ddos_analyzer.py -f arquivo.csv -w 8 -n 50
  python ddos_analyzer.py -f arquivo.csv --bench
        """)
    p.add_argument("-f","--file",                          help="Arquivo CSV")
    p.add_argument("-d","--dir",                           help="Diretório com CSVs")
    p.add_argument("-w","--workers", type=int,             help=f"Workers (padrão: {cpu_count()})")
    p.add_argument("-n","--top",     type=int, default=20, help="Top-N IPs (padrão: 20)")
    p.add_argument("-o","--output",  default="ddos",       help="Prefixo dos arquivos de saída")
    p.add_argument("--bench", action="store_true",         help="Executar benchmark serial vs paralelo")
    args = p.parse_args()

    if args.bench:
        if not args.file: p.error("--bench requer -f <arquivo>")
        executar_benchmark(args.file)

    elif args.file:
        a = DDoSAnalyzer(n_workers=args.workers, top_n=args.top)
        a.analisar_arquivo(args.file)
        a.imprimir_sumario()
        a.salvar_relatorios(args.output)

    elif args.dir:
        a = DDoSAnalyzer(n_workers=args.workers, top_n=args.top)
        a.analisar_diretorio(args.dir)
        a.imprimir_sumario()
        a.salvar_relatorios(args.output)

    else:
        p.print_help()


# O bloco if __name__ == "__main__" é OBRIGATÓRIO para multiprocessing:
# impede que processos filhos tentem iniciar novos processos ao importar o módulo.
if __name__ == "__main__":
    main()