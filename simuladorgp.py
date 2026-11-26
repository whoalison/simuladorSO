import math
import hashlib
import os
import re
import random
import shlex
from collections import deque

#parametros
BLOCK_SIZE = 4096        # 4KB Bloco de Disco e pag de mem
TOTAL_BLOCKS = 16        # 64KB Disco fisico
RESERVED_RAM_KB = 4096   # 4MB reserva p alocação contigua
DYNAMIC_FRAMES = 4       # 4(16 KB) na RAM Dinâmica 

#GERENCIAMENTO DE IDENTIDADE E AUTENTICAÇÃO
class UserManager:
    def __init__(self):
        self.users = {}
        self.add_user("root", "admin", "toor")
        self.add_user("carlos", "devs", "1234")

    def add_user(self, username, group, password):
        salt = os.urandom(16)
        hash_obj = hashlib.sha256(salt + password.encode('utf-8'))
        self.users[username] = {"group": group, "salt": salt, "hash": hash_obj.hexdigest()}

    def authenticate(self, username, password):
        if username not in self.users: return False
        u = self.users[username]
        return hashlib.sha256(u["salt"] + password.encode('utf-8')).hexdigest() == u["hash"]


#PROCESSOS+THREADS+MUTEX E MEMÓRIA HÍBRIDA
class Thread:
    def __init__(self, tid, parent_pid):
        self.tid = tid
        self.parent_pid = parent_pid
        self.state = "PRONTO"  #estado

class Mutex:
    """Implementação real de exclusão mútua com fila de espera."""
    def __init__(self, name):
        self.name = name
        self.locked_by = None
        self.wait_queue = deque()

    def acquire(self, thread, clock_t):
        print(f"[t={clock_t}ms] Thread {thread.tid} (PID {thread.parent_pid}) tenta acessar Região Crítica ('{self.name}').")
        if self.locked_by is None:
            self.locked_by = thread
            thread.state = "EXECUTANDO"
            print(f"        Mutex [LIVRE] -> {thread.tid} adquire o Mutex [BLOQUEADO].")
            return True
        else:
            thread.state = "BLOQUEADO"
            self.wait_queue.append(thread)
            print(f"        Mutex [BLOQUEADO por {self.locked_by.tid}]!")
            print(f"        - Mudança de Estado de {thread.tid}: EXECUTANDO -> BLOQUEADO (Aguardando Mutex).")
            return False

    def release(self, thread, clock_t):
        if self.locked_by == thread:
            print(f"[t={clock_t}ms] Thread {thread.tid} libera o Mutex ('{self.name}').")
            if self.wait_queue:
                next_t = self.wait_queue.popleft()
                self.locked_by = next_t
                next_t.state = "PRONTO"
                print(f"        - Thread {next_t.tid} acordada da fila: BLOQUEADO -> PRONTO (Adquiriu Mutex).")
            else:
                self.locked_by = None

class MemorySegment:
    def __init__(self, start_kb, size_kb, owner_name=None):
        self.start_kb = start_kb
        self.size_kb = size_kb
        self.owner_name = owner_name

    @property
    def end_kb(self):
        return self.start_kb + self.size_kb

class Process:
    def __init__(self, pid, name, size_bytes, is_critical, burst_ms=5, priority=2, syscall_cfg=None, arrival_ms=0):
        self.pid = pid
        self.name = name
        self.size_bytes = size_bytes
        self.is_critical = is_critical
        self.page_table = {}  #pagina_logica: moldura_fisica ou None

        # escalonamento e ciclo de vida
        self.state = "NOVO"
        self.priority = priority
        self.burst_time = burst_ms
        self.remaining_burst = burst_ms
        self.cpu_executed = 0
        self.arrival_time = arrival_ms
        self.completion_time = None

        #perfil de I/O (Syscalls)
        self.syscall_cfg = syscall_cfg  
        self.syscall_triggered = False
        self.unblock_time = None

        #threads para concorrencia
        self.threads = [Thread("T1", pid), Thread("T2", pid)]

class MemoryManager:
    def __init__(self):
        self.next_pid = 101
        self.processes = {}
        self.reserved_segments = [
            MemorySegment(0, 1024, "Núcleo Base do SO"),
            MemorySegment(1024, RESERVED_RAM_KB - 1024, None)
        ]
        self.frames = [None] * DYNAMIC_FRAMES  #'pid', 'name', 'page', 'last_used', 'status'
        self.swap_space = set()

    def _parse_syscall(self, syscall_str):
        if not syscall_str:
            return None
        s = syscall_str.strip().lower()
        if s == "random":
            return {"mode": "random", "action": "random_io", "duration": 3}
        #"read_disk at 3ms (duration: 4ms)"
        match = re.search(r'(\w+)\s+at\s+(\d+)ms.*duration:\s*(\d+)ms', s)
        if match:
            return {
                "mode": "scheduled",
                "action": match.group(1),
                "at": int(match.group(2)),
                "duration": int(match.group(3))
            }
        return None

    def create_process(self, name, size_kb, proc_type, current_mode, burst_ms=5, priority=2, syscall_str=None):
        if name in self.processes:
            return print(f"Erro: Processo '{name}' já existe.")

        is_critical = (proc_type == "critical")
        if is_critical and current_mode != "MODO_KERNEL":
            return print("[NEGADO]: Apenas MODO_KERNEL (root) pode alocar processos críticos.")

        pid = self.next_pid
        self.next_pid += 1
        size_bytes = int(size_kb * 1024)
        syscall_cfg = self._parse_syscall(syscall_str)

        proc = Process(pid, name, size_bytes, is_critical, burst_ms, priority, syscall_cfg, arrival_ms=0)

        if is_critical:
            allocated = False
            for i, seg in enumerate(self.reserved_segments):
                if seg.owner_name is None and seg.size_kb >= size_kb:
                    start = seg.start_kb
                    rem = seg.size_kb - size_kb
                    self.reserved_segments[i] = MemorySegment(start, size_kb, name)
                    if rem > 0:
                        self.reserved_segments.insert(i + 1, MemorySegment(start + size_kb, rem, None))
                    allocated = True
                    break
            if not allocated:
                return print(f"[FALHA]: Sem bloco contíguo de {int(size_kb)} KB na Área Reservada.")
            aloc_desc = f"Área Reservada Contígua ({int(size_kb)} KB)"
        else:
            num_pages = max(1, math.ceil(size_bytes / BLOCK_SIZE))
            for p in range(num_pages):
                proc.page_table[p] = None
                self.swap_space.add((pid, p))
            aloc_desc = f"Memória Virtual Paginada ({num_pages} Páginas Lógicas)"

        proc.state = "PRONTO"
        self.processes[name] = proc

        prio_label = "Alta" if priority == 1 else ("Média" if priority == 2 else "Baixa")
        print(f"\n[CRIAÇÃO DE PROCESSO] PID: {pid} | Nome: {name} | Burst: {burst_ms}ms | Prioridade: {priority} ({prio_label})")
        print(f"Alocação      : {aloc_desc}")
        if syscall_cfg:
            if syscall_cfg["mode"] == "scheduled":
                print(f"Syscall/I/O   : '{syscall_cfg['action']}' agendada para t={syscall_cfg['at']}ms (Bloqueio: {syscall_cfg['duration']}ms)")
            else:
                print("Syscall/I/O   : Evento Aleatório Habilitado")
        else:
            print("Syscall/I/O   : Nenhuma")
        print(f"Estado Inicial: {proc.state}\n")

    def access_page(self, proc, page_num, clock_t):
        """Executa tradução de página e substituição LRU real usando o relógio lógico."""
        if page_num not in proc.page_table:
            page_num = page_num % max(1, len(proc.page_table))

        frame_idx = proc.page_table[page_num]
        if frame_idx is not None:
            self.frames[frame_idx]["last_used"] = clock_t
            self.frames[frame_idx]["status"] = "HIT"
            return "HIT", frame_idx, None

        #pagina
        free_frame = next((i for i, f in enumerate(self.frames) if f is None), None)
        evicted_info = None

        if free_frame is not None:
            target_frame = free_frame
        else:
            #LRU=escolhe a moldura com o menor timestamp 'last_used'
            lru_idx = min(range(DYNAMIC_FRAMES), key=lambda i: self.frames[i]["last_used"])
            vitima = self.frames[lru_idx]
            evicted_info = (vitima["pid"], vitima["name"], vitima["page"], clock_t - vitima["last_used"])
            self.processes[vitima["name"]].page_table[vitima["page"]] = None
            self.swap_space.add((vitima["pid"], vitima["page"]))
            target_frame = lru_idx

        self.swap_space.discard((proc.pid, page_num))
        self.frames[target_frame] = {
            "pid": proc.pid,
            "name": proc.name,
            "page": page_num,
            "last_used": clock_t,
            "status": "PAGE FAULT (NEW)"
        }
        proc.page_table[page_num] = target_frame
        return "PAGE_FAULT", target_frame, evicted_info

    def print_ram_summary_table(self):
        print("\n[RESUMO DA GERÊNCIA DE MEMÓRIA (RAM DINÂMICA)]")
        print("+------------------+---------------+-------------------+---------------------+")
        print("| Moldura RAM (F)  | Processo/Pág  | Estado de Acesso  | Último Acesso (LRU) |")
        print("+------------------+---------------+-------------------+---------------------+")
        for i, f in enumerate(self.frames):
            if f:
                m_str = f"Moldura {i:02d}"
                p_str = f"PID {f['pid']} / P{f['page']}"
                s_str = f["status"]
                t_str = f"t = {f['last_used']} ms"
                print(f"| {m_str:^16} | {p_str:^13} | {s_str:<17} | {t_str:<19} |")
            else:
                print(f"| {f'Moldura {i:02d}':^16} | {'[LIVRE]':^13} | {'-':<17} | {'-':<19} |")
        print("+------------------+---------------+-------------------+---------------------+\n")

    def memory_status_reserved(self):
        print(f"\n--- MAPA DA ÁREA RESERVADA ({RESERVED_RAM_KB//1024} MB) ---")
        for seg in self.reserved_segments:
            st = "[OCUPADO]" if seg.owner_name else "[LIVRE]"
            print(f"[{seg.start_kb/1024:.1f} MB - {seg.end_kb/1024:.1f} MB] : {(seg.owner_name or 'LIVRE'):<22} ({int(seg.size_kb)} KB) {st}")

    def compact_reserved(self, current_mode):
        if current_mode != "MODO_KERNEL":
            return print("[NEGADO]: Exige MODO_KERNEL.")
        new_segs, cursor = [], 0
        for seg in self.reserved_segments:
            if seg.owner_name:
                new_segs.append(MemorySegment(cursor, seg.size_kb, seg.owner_name))
                cursor += seg.size_kb
        if RESERVED_RAM_KB - cursor > 0:
            new_segs.append(MemorySegment(cursor, RESERVED_RAM_KB - cursor, None))
        self.reserved_segments = new_segs
        print("Área Reservada compactada com sucesso.")


#ESCALONADOR MESCLADO POR PRIORIDADE E ROUND-ROBIN + SIMULAÇÃO
class Scheduler:
    def __init__(self, mem_manager):
        self.mem = mem_manager
        self.clock = 0
        self.mutexes = {}

    def run_simulation(self, proc_name, steps):
        """Simula N passos de CPU para um processo, acessando páginas e checando Syscall."""
        if proc_name not in self.mem.processes:
            return print(f"Erro: Processo '{proc_name}' não encontrado.")
        proc = self.mem.processes[proc_name]
        if proc.is_critical:
            return print("Processos críticos usam área contígua sem paginação.")

        proc.state = "EXECUTANDO"
        num_pages = len(proc.page_table)

        for step in range(1, steps + 1):
            self.clock += 1
            proc.cpu_executed += 1
            page_to_access = random.randint(0, num_pages - 1)

            print(f"\n--- STEP {step} (t={self.clock}ms) | Executando PID {proc.pid} ({proc.name}) ---")
            status, frame_idx, evicted = self.mem.access_page(proc, page_to_access, self.clock)

            if status == "HIT":
                print(f"CPU acessa: Página Lógica {page_to_access:02d} -> [RAM: Moldura {frame_idx:02d} - HIT] | Histórico LRU atualizado (t={self.clock}ms)")
            else:
                print(f"CPU acessa: Página Lógica {page_to_access:02d} -> [PAGE FAULT!]")
                if evicted:
                    ev_pid, ev_name, ev_page, idade = evicted
                    print(f"Substituição LRU: Página Lógica {ev_page:02d} do PID {ev_pid} ('{ev_name}', inativa há {idade}ms) removida para o Swap.")
                print(f"Página Lógica {page_to_access:02d} alocada na Moldura {frame_idx:02d}.")

            #Verifica servico de Syscall agendado ou aleatório
            if proc.syscall_cfg and not proc.syscall_triggered:
                trigger = False
                if proc.syscall_cfg["mode"] == "scheduled" and proc.cpu_executed == proc.syscall_cfg["at"]:
                    trigger = True
                elif proc.syscall_cfg["mode"] == "random" and random.random() < 0.35:
                    trigger = True

                if trigger:
                    proc.syscall_triggered = True
                    proc.state = "BLOQUEADO"
                    dur = proc.syscall_cfg["duration"]
                    proc.unblock_time = self.clock + dur
                    print(f"\n[SYSCALL DETECTADA]: PID {proc.pid} atingiu instrução '{proc.syscall_cfg['action']}' em t={self.clock}ms!")
                    print(f"- Mudança de Estado: EXECUTANDO -> BLOQUEADO (E/S de Disco).")
                    print(f"- Tempo de Retorno Previsto: {dur}ms (Desbloqueio em t={proc.unblock_time}ms).")
                    print("- CPU liberada -> Escalonador selecionará próximo processo da Fila de Pronto.")
                    break

        self.mem.print_ram_summary_table()

    def test_mutex(self, proc_name, resource_name):
        """Demonstra concorrência real de threads disputando um Mutex."""
        if proc_name not in self.mem.processes:
            return print(f"Erro: Processo '{proc_name}' não encontrado.")
        proc = self.mem.processes[proc_name]
        if resource_name not in self.mutexes:
            self.mutexes[resource_name] = Mutex(resource_name)
        mtx = self.mutexes[resource_name]

        t1, t2 = proc.threads[0], proc.threads[1]
        print(f"\n[CONCORRÊNCIA DE THREADS EM PID {proc.pid} ({proc.name})]")
        self.clock += 1
        mtx.acquire(t1, self.clock)
        self.clock += 1
        mtx.acquire(t2, self.clock)
        self.clock += 2
        mtx.release(t1, self.clock)
        print()

    def schedule_priority_rr(self, quantum_ms):
        """Escalonador real tick-a-tick: Filas de Prioridade + Round-Robin."""
        #zera os contadores dos processos ativos para proximo round limpa do escalonador
        procs = [p for p in self.mem.processes.values() if not p.is_critical]
        if not procs:
            return print("Nenhum processo paginado criado para escalonar.")

        queues = {}
        for p in procs:
            p.state = "PRONTO"
            p.remaining_burst = p.burst_time
            p.cpu_executed = 0
            p.arrival_time = 0
            p.completion_time = None
            p.syscall_triggered = False
            p.unblock_time = None
            queues.setdefault(p.priority, deque()).append(p)

        print("\nFila de Pronto Inicial:")
        for prio in sorted(queues.keys()):
            desc = ", ".join([f"PID {p.pid} ({p.name}, Burst {p.burst_time}ms)" for p in queues[prio]])
            print(f"- Prioridade {prio}: [{desc}]")

        print(f"\n--- LINHA DO TEMPO DA CPU (Priority + Round-Robin | Quantum: {quantum_ms}ms) ---")

        t = 0
        blocked = []
        completed = []
        current_proc = None
        quantum_used = 0
        slice_start = 0
        context_switches = 0
        cpu_busy = 0

        def pick_next():
            for prio in sorted(queues.keys()):
                if queues[prio]:
                    return queues[prio].popleft()
            return None

        while len(completed) < len(procs):
            #verifica processos bloqueados que o I/O terminou neste instante (t)
            for bp in list(blocked):
                if bp.unblock_time <= t:
                    blocked.remove(bp)
                    bp.state = "PRONTO"
                    queues[bp.priority].append(bp)
                    print(f"[{t}ms]       Evento E/S: PID {bp.pid} encerrou I/O -> BLOQUEADO -> PRONTO")

            #seleciona processo seguinte se CPU desocupada
            if current_proc is None:
                current_proc = pick_next()
                if current_proc:
                    current_proc.state = "EXECUTANDO"
                    quantum_used = 0
                    slice_start = t
                else:
                    #CPU ociosa aguardando I/O
                    t += 1
                    continue

            #executa 1ms de CPU (e referencia uma página na RAM)
            t += 1
            cpu_busy += 1
            quantum_used += 1
            current_proc.remaining_burst -= 1
            current_proc.cpu_executed += 1

            #att a RAM para manter a integração
            pg = current_proc.cpu_executed % max(1, len(current_proc.page_table))
            self.mem.access_page(current_proc, pg, t)

            #verifica condições de saída da CPU (Conclusão, Syscall ou Quantum)
            if current_proc.remaining_burst == 0:
                current_proc.state = "CONCLUÍDO"
                current_proc.completion_time = t
                completed.append(current_proc)
                print(f"[{slice_start}ms - {t}ms] Executando PID {current_proc.pid} | PID {current_proc.pid} CONCLUÍDO!")
                current_proc = None
                if len(completed) < len(procs):
                    context_switches += 1

            elif (current_proc.syscall_cfg and not current_proc.syscall_triggered and
                  ((current_proc.syscall_cfg["mode"] == "scheduled" and current_proc.cpu_executed == current_proc.syscall_cfg["at"]) or
                   (current_proc.syscall_cfg["mode"] == "random" and random.random() < 0.25))):
                current_proc.syscall_triggered = True
                current_proc.state = "BLOQUEADO"
                dur = current_proc.syscall_cfg["duration"]
                current_proc.unblock_time = t + dur
                blocked.append(current_proc)
                print(f"[{slice_start}ms - {t}ms] Executando PID {current_proc.pid} | Dispara Syscall -> BLOQUEADO (até t={current_proc.unblock_time}ms)")
                current_proc = None
                context_switches += 1

            elif quantum_used == quantum_ms:
                current_proc.state = "PRONTO"
                queues[current_proc.priority].append(current_proc)
                print(f"[{slice_start}ms - {t}ms] Executando PID {current_proc.pid} | Quantum {quantum_ms}ms expirou -> Volta p/ Fila P{current_proc.priority}")
                current_proc = None
                context_switches += 1

        #métricas finais do escalonador
        print("\n================ MÉTRICAS FINAIS DO ESCALONADOR ================")
        print("+----------+------------+---------------+-------------------+---------------------+")
        print("| Processo | Prioridade | Tempo Chegada | Tempo Espera (WT) | Turnaround Time(TAT)|")
        print("+----------+------------+---------------+-------------------+---------------------+")
        total_wt, total_tat = 0, 0
        for p in sorted(completed, key=lambda x: x.pid):
            tat = p.completion_time - p.arrival_time
            wt = tat - p.burst_time
            total_tat += tat
            total_wt += wt
            print(f"| PID {p.pid:<4} | {p.priority:^10} | {f'{p.arrival_time} ms':^13} | {f'{wt} ms':^17} | {f'{tat} ms':^19} |")
        print("+----------+------------+---------------+-------------------+---------------------+")
        awt = total_wt / len(completed)
        att = total_tat / len(completed)
        cpu_util = (cpu_busy / t) * 100 if t > 0 else 0
        print(f"- Tempo Médio de Espera (AWT)  : {awt:.2f} ms")
        print(f"- Tempo Médio de Retorno (ATT) : {att:.2f} ms")
        print(f"- Trocas de Contexto Totais    : {context_switches} trocas")
        print(f"- Utilização Global da CPU     : {cpu_util:.1f}%\n")


#NUCLEO DO SO TOTALMNETE INTEGRADO + INTERFACE
class OperatingSystem:
    def __init__(self):
        self.auth = UserManager()
        self.mem = MemoryManager()
        self.sched = Scheduler(self.mem)
        self.current_user = "root"
        self.current_group = "admin"
        self.mode = "MODO_KERNEL"

def get_arg(parts, flag, default=None):
    if flag in parts:
        idx = parts.index(flag)
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return default

def start_shell():
    os_sim = OperatingSystem()
    print("Simulador SO Completo (Etapas 1 a 5). Digite 'help' para comandos.")

    while True:
        try:
            prompt = f"[{os_sim.mode}] {os_sim.current_user}@/> "
            cmd_input = input(prompt).strip()
            if not cmd_input: continue

            parts = shlex.split(cmd_input)
            cmd = parts[0].lower()

            if cmd in ["exit", "quit"]: break

            elif cmd == "create_process":
                name = get_arg(parts, "--name")
                burst_str = get_arg(parts, "--burst", "5ms").lower().replace("ms", "")
                prio = int(get_arg(parts, "--priority", "2"))
                size_str = get_arg(parts, "--size", "32KB").upper().replace("KB", "")
                ptype = get_arg(parts, "--type", "normal")
                syscall = get_arg(parts, "--syscall", None)
                if name:
                    os_sim.mem.create_process(name, float(size_str), ptype, os_sim.mode, int(burst_str), prio, syscall)
                else:
                    print('Uso: create_process --name "App" --burst 8ms --priority 1 --syscall "read_disk at 3ms (duration: 4ms)"')

            elif cmd == "run_simulation":
                proc = get_arg(parts, "--process")
                steps = int(get_arg(parts, "--steps", "3"))
                if proc:
                    os_sim.sched.run_simulation(proc, steps)

            elif cmd == "test_mutex":
                proc = get_arg(parts, "--process")
                res = get_arg(parts, "--resource", "Buffer_Video")
                if proc:
                    os_sim.sched.test_mutex(proc, res)

            elif cmd == "schedule":
                q_str = get_arg(parts, "--quantum", "2ms").lower().replace("ms", "")
                os_sim.sched.schedule_priority_rr(int(q_str))

            elif cmd == "memory_status":
                os_sim.mem.memory_status_reserved()
                os_sim.mem.print_ram_summary_table()

            elif cmd == "memory_compact":
                os_sim.mem.compact_reserved(os_sim.mode)

            elif cmd == "login":
                user = get_arg(parts, "--user")
                senha = input("Senha: ")
                if os_sim.auth.authenticate(user, senha):
                    os_sim.current_user = user
                    os_sim.current_group = os_sim.auth.users[user]["group"]
                    os_sim.mode = "MODO_KERNEL" if user == "root" else "MODO_USUARIO"
                    print(f"Autenticado: '{user}' | Modo: {os_sim.mode}")
                else:
                    print("Falha na autenticação.")

            elif cmd == "help":
                print("\n--- Comandos Etapa 5 (Processos, Memória e Escalonamento) ---")
                print('create_process --name "App_Web" --burst 8ms --priority 1 --syscall "read_disk at 3ms (duration: 4ms)"')
                print('run_simulation --process App_Web --steps 3')
                print('test_mutex --process App_Render --resource Buffer_Video')
                print('schedule --algorithm Priority_RR --quantum 2ms')
                print('memory_status | memory_compact | login --user root|carlos\n')
            else:
                print("Comando inválido. Digite 'help'.")
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    start_shell()