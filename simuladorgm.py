import math
import hashlib
import os
import time
import shlex

#config
BLOCK_SIZE = 4096        # 4KB Disco e pag
TOTAL_BLOCKS = 16        # 64KB Disco fisico
RESERVED_RAM_KB = 4096   # 4 MB Area reservada 
DYNAMIC_FRAMES = 4       # 4 (16 KB) testes de Page Fault LRU

#IDENTIDADE E AUTENTICAÇÃO
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

# GERENCIAMENTO DE MEMORIA HIBRIDA SENDO CONTIGUA E PAGINADA/LRU
class MemorySegment:
    """Representa um bloco contíguo real na Área Reservada da RAM."""
    def __init__(self, start_kb, size_kb, owner_name=None):
        self.start_kb = start_kb
        self.size_kb = size_kb
        self.owner_name = owner_name  #segmento LIVRE

    @property
    def end_kb(self):
        return self.start_kb + self.size_kb

class Process:
    """Representa um processo no sistema (Crítico ou Normal)."""
    def __init__(self, pid, name, size_bytes, is_critical):
        self.pid = pid
        self.name = name
        self.size_bytes = size_bytes
        self.is_critical = is_critical
        self.page_table = {}  #pagina_logica: moldura_fisica / segmento livre

class MemoryManager:
    def __init__(self):
        self.next_pid = 100
        self.processes = {}

        #area reservada 4MB / Núcleo ocupa os primeiros 1024 KB
        self.reserved_segments = [
            MemorySegment(0, 1024, "Núcleo Base do SO"),
            MemorySegment(1024, RESERVED_RAM_KB - 1024, None)
        ]

        #Memória Virtual Paginada
        #Cada moldura salva segmento livre ou {'pid', 'name', 'page', 'last_used'}
        self.frames = [None] * DYNAMIC_FRAMES
        self.swap_space = set()  #Tuplas (pid, page_num) salvas no disco Swap

    def create_process(self, name, size_kb, proc_type, current_mode):
        if name in self.processes:
            return print(f"Erro: Processo '{name}' já existe.")

        is_critical = (proc_type == "critical")
        if is_critical and current_mode != "MODO_KERNEL":
            return print("[NEGADO]: Apenas MODO_KERNEL (root) pode alocar processos críticos na Área Reservada.")

        pid = self.next_pid
        self.next_pid += 1
        size_bytes = int(size_kb * 1024)

        if is_critical:
            # Alocação Contígua (First-Fit) na area reservada
            allocated = False
            for i, seg in enumerate(self.reserved_segments):
                if seg.owner_name is None and seg.size_kb >= size_kb:
                    start = seg.start_kb
                    rem = seg.size_kb - size_kb
                    self.reserved_segments[i] = MemorySegment(start, size_kb, name)
                    if rem > 0:
                        self.reserved_segments.insert(i + 1, MemorySegment(start + size_kb, rem, None))
                    allocated = True
                    print(f"- Alocado de forma contígua na Área Reservada: [{start/1024:.1f} MB até {(start+size_kb)/1024:.1f} MB] ({int(size_kb)} KB)")
                    break
            if not allocated:
                return print(f"[FALHA DE ALOCAÇÃO]: Sem bloco contíguo de {int(size_kb)} KB na Área Reservada. Execute 'memory_compact --reserved'.")
            self.processes[name] = Process(pid, name, size_bytes, True)

        else:
            #alocação por demanda na memória virtual/paginacao
            num_pages = math.ceil(size_bytes / BLOCK_SIZE)
            proc = Process(pid, name, size_bytes, False)
            for p in range(num_pages):
                proc.page_table[p] = None  #alocacao por demanda / fora da mem ram
                self.swap_space.add((pid, p))
            self.processes[name] = proc

            print(f"\n[CRIAÇÃO DE PROCESSO NÃO CRÍTICO - MEMÓRIA VIRTUAL] (PID: {pid})")
            print(f"Tamanho do Processo : {size_kb:g} KB ({size_bytes} Bytes)")
            print(f"Tamanho da Página   : {BLOCK_SIZE//1024} KB ({BLOCK_SIZE} Bytes)")
            print(f"Cálculo de Páginas  : {size_kb:g} KB / {BLOCK_SIZE//1024} KB = {size_kb/(BLOCK_SIZE/1024):.2f} -> Requer {num_pages} Páginas Lógicas (0 a {num_pages-1}).\n")
            print("--- ANÁLISE DE FRAGMENTAÇÃO INTERNA ---")
            bytes_restantes = size_bytes
            frag_total = 0
            for p in range(num_pages):
                ocupado = min(BLOCK_SIZE, bytes_restantes)
                pct = (ocupado / BLOCK_SIZE) * 100
                print(f"Página Lógica {p} : {ocupado} Bytes ocupados ({pct:.0f}%)")
                if ocupado < BLOCK_SIZE:
                    frag_total += (BLOCK_SIZE - ocupado)
                bytes_restantes -= ocupado
            print(f"Fragmentação Interna Total: {frag_total} Bytes de desperdício na última página.")
            print("Status: Tabela de Páginas gerada sem alocar molduras na RAM (Alocação por demanda).\n")

    def terminate_process(self, name, current_mode):
        if name not in self.processes:
            return print(f"Erro: Processo '{name}' não encontrado.")
        proc = self.processes[name]

        if proc.is_critical:
            if current_mode != "MODO_KERNEL":
                return print("[NEGADO]: Apenas MODO_KERNEL pode encerrar processos críticos.")
            for seg in self.reserved_segments:
                if seg.owner_name == name:
                    print(f"[ENCERRAMENTO DE PROCESSO CRÍTICO] Processo '{name}' finalizado.")
                    print(f"Área de {int(seg.size_kb)} KB no intervalo [{seg.start_kb/1024:.1f} MB a {seg.end_kb/1024:.1f} MB] liberada na Área Reservada da RAM.")
                    seg.owner_name = None
                    break
            self._coalesce_free_segments()
        else:
            #libera RAM dinamica e limpa Swap
            for i, f in enumerate(self.frames):
                if f and f["pid"] == proc.pid:
                    self.frames[i] = None
            self.swap_space = {item for item in self.swap_space if item[0] != proc.pid}
            print(f"Processo '{name}' (PID {proc.pid}) encerrado e molduras liberadas.")

        del self.processes[name]

    def _coalesce_free_segments(self):
        """Une segmentos livres adjacentes na Área Reservada."""
        i = 0
        while i < len(self.reserved_segments) - 1:
            curr = self.reserved_segments[i]
            nxt = self.reserved_segments[i + 1]
            if curr.owner_name is None and nxt.owner_name is None:
                curr.size_kb += nxt.size_kb
                self.reserved_segments.pop(i + 1)
            else:
                i += 1

    def memory_status_reserved(self):
        print(f"\n--- MAPA DA ÁREA CRÍTICA/RESERVADA DA RAM (Total: {RESERVED_RAM_KB//1024} MB - Alocação Fixa) ---")
        free_frags = []
        frag_idx = 1
        for seg in self.reserved_segments:
            intervalo = f"[{seg.start_kb/1024:.1f} MB - {seg.end_kb/1024:.1f} MB]"
            if seg.owner_name:
                print(f"{intervalo} : {seg.owner_name:<22} ({int(seg.size_kb)} KB) [OCUPADO]")
            else:
                label = f"FRAGMENTO LIVRE {frag_idx}"
                print(f"{intervalo} : {label:<22} ({int(seg.size_kb)} KB) [LIVRE - LACUNA]")
                free_frags.append(seg.size_kb)
                frag_idx += 1

        total_free = sum(free_frags)
        max_contig = max(free_frags) if free_frags else 0
        has_ext_frag = len(free_frags) > 1

        print("\n--- DIAGNÓSTICO DE FRAGMENTAÇÃO EXTERNA ---")
        print(f"Total de Memória Livre na Área Reservada : {int(total_free)} KB ({total_free/1024:.1f} MB)")
        print(f"Maior Bloco Contíguo Disponível          : {int(max_contig)} KB ({max_contig/1024:.1f} MB)")
        print(f"Fragmentação Externa Detectada           : {'SIM' if has_ext_frag else 'NÃO'} ({len(free_frags)} bloco(s) livre(s))")
        if has_ext_frag:
            print(f"Status: Uma requisição contígua de {int(max_contig + 512)} KB falhará por ausência de bloco único.\n")
        else:
            print("Status: Memória contígua saudável.\n")

    def compact_reserved(self, current_mode):
        if current_mode != "MODO_KERNEL":
            return print("[NEGADO]: Compactação da RAM exige MODO_KERNEL.")
        print("\n[EXECUTANDO COMPACTAÇÃO DA ÁREA RESERVADA DA RAM]")
        print("Realocando blocos contíguos para eliminar a fragmentação externa...")

        new_segments = []
        cursor_kb = 0
        for seg in self.reserved_segments:
            if seg.owner_name is not None:
                if seg.start_kb != cursor_kb:
                    print(f"- Mapeamento de '{seg.owner_name}': [{seg.start_kb/1024:.1f} MB a {seg.end_kb/1024:.1f} MB] -> Ajustado para: [{cursor_kb/1024:.1f} MB a {(cursor_kb+seg.size_kb)/1024:.1f} MB]")
                new_segments.append(MemorySegment(cursor_kb, seg.size_kb, seg.owner_name))
                cursor_kb += seg.size_kb

        free_total = RESERVED_RAM_KB - cursor_kb
        if free_total > 0:
            new_segments.append(MemorySegment(cursor_kb, free_total, None))

        self.reserved_segments = new_segments
        print("\n--- MAPA APÓS COMPACTAÇÃO ---")
        for seg in self.reserved_segments:
            intervalo = f"[{seg.start_kb/1024:.1f} MB - {seg.end_kb/1024:.1f} MB]"
            status = "[OCUPADO]" if seg.owner_name else "[LIVRE]"
            nome = seg.owner_name if seg.owner_name else "Bloco Livre Contíguo"
            print(f"{intervalo} : {nome:<22} ({int(seg.size_kb)} KB) {status}")
        print(f"Resultado: Fragmentação externa eliminada. Maior bloco contíguo: {int(free_total)} KB.\n")

    def memory_status_virtual(self):
        print(f"\n--- MAPA DA MEMÓRIA VIRTUAL / RAM DINÂMICA ({DYNAMIC_FRAMES} Molduras de {BLOCK_SIZE//1024} KB) ---")
        for i, f in enumerate(self.frames):
            if f is None:
                print(f"Moldura Física {i:02d} : [LIVRE]")
            else:
                idade_ms = int((time.time() - f["last_used"]) * 1000)
                print(f"Moldura Física {i:02d} : Processo '{f['name']}' (PID {f['pid']}) - Página Lógica {f['page']} (Último acesso há {idade_ms}ms)")
        print(f"Páginas no Swap (Disco): {len(self.swap_space)}\n")

    def translate_address(self, proc_name, page_num):
        if proc_name not in self.processes or self.processes[proc_name].is_critical:
            return print(f"Erro: Processo paginado '{proc_name}' não encontrado.")
        proc = self.processes[proc_name]
        if page_num not in proc.page_table:
            return print(f"Erro: Página Lógica {page_num} fora dos limites de '{proc_name}'.")

        print("\n[TRADUÇÃO DE ENDEREÇO: PÁGINA LÓGICA -> MOLDURA FÍSICA]")
        frame_idx = proc.page_table[page_num]
        if frame_idx is not None:
            self.frames[frame_idx]["last_used"] = time.time()
            print(f"Solicitação: Página Lógica {page_num} -> Mapeada na Moldura Física {frame_idx} (RAM Dinâmica) [HIT]\n")
        else:
            print(f"Solicitação: Página Lógica {page_num} -> NÃO MAPEADA NA RAM [PAGE FAULT - Use execute_step para carregar]\n")

    def execute_step(self, proc_name, page_num):
        if proc_name not in self.processes or self.processes[proc_name].is_critical:
            return print(f"Erro: Processo paginado '{proc_name}' não encontrado.")
        proc = self.processes[proc_name]
        if page_num not in proc.page_table:
            return print(f"Erro: Página Lógica {page_num} inválida para '{proc_name}'.")

        print("\n[CPU - REFERÊNCIA DE MEMÓRIA EM EXECUÇÃO]")
        print(f"{proc_name} (PID {proc.pid}) requisita acesso à Página Lógica {page_num}...")

        frame_idx = proc.page_table[page_num]
        if frame_idx is not None:
            self.frames[frame_idx]["last_used"] = time.time()
            print(f"- Consulta Tabela de Páginas -> [HIT] Presente na Moldura Física {frame_idx}. Timestamp LRU atualizado.\n")
            return

        #PAGEFAULT REAL
        print(f"- Consulta Tabela de Páginas -> Página Lógica {page_num} NÃO ESTÁ NA RAM!")
        print(f"\n[PAGE FAULT DETECTADO]: Página Lógica {page_num} ausente na RAM!")

        #Verificacao se tem moldura livre
        free_frame = next((i for i, f in enumerate(self.frames) if f is None), None)

        if free_frame is not None:
            target_frame = free_frame
            print(f"- Moldura livre encontrada: Carregando do Swap para a Moldura Física {target_frame}.")
        else:
            #ALGORITMO LRU REAL / Least Recently Used
            print("Memória RAM cheia. Executando Substituição de Página (Algoritmo LRU):")
            lru_frame_idx = min(range(DYNAMIC_FRAMES), key=lambda i: self.frames[i]["last_used"])
            vitima = self.frames[lru_frame_idx]
            idade_ms = int((time.time() - vitima["last_used"]) * 1000)

            print(f"- Analisando histórico de acesso: Página Lógica {vitima['page']} do PID {vitima['pid']} ('{vitima['name']}') não é usada há {idade_ms}ms (Mais antiga).")
            print(f"- Removendo Página Lógica {vitima['page']} do PID {vitima['pid']} da RAM -> Salvando no Swap (Disco).")

            #Atualiza tabela de pag da vitima e devolve ao Swap
            self.processes[vitima["name"]].page_table[vitima["page"]] = None
            self.swap_space.add((vitima["pid"], vitima["page"]))
            target_frame = lru_frame_idx

        #carrega a nova pag na moldura escolhida
        self.swap_space.discard((proc.pid, page_num))
        self.frames[target_frame] = {
            "pid": proc.pid,
            "name": proc.name,
            "page": page_num,
            "last_used": time.time()
        }
        proc.page_table[page_num] = target_frame
        print(f"- Carregando Página Lógica {page_num} de '{proc_name}' na Moldura Física {target_frame} (RAM Dinâmica).")
        print(f"- Tabela de Páginas atualizada: Página Lógica {page_num} ---> Moldura Física {target_frame}.\n")

# integracao / SISTEMA DE ARQUIVOS E/S (SSTF/RAID) E SEGURANÇA
class DiskBlock:
    def __init__(self):
        self.is_free = True
        self.type = None
        self.data = bytearray(BLOCK_SIZE)
        self.used_bytes = 0
        self.references = []
        self.metadata_name = ""

class FileNode:
    def __init__(self, name, is_dir, owner="root", group="admin", parent=None):
        self.name = name
        self.is_dir = is_dir
        self.parent = parent
        self.children = {}
        self.inode_block_idx = -1
        self.size_bytes = 0
        self.owner = owner
        self.group = group
        self.permissions = "rwxr-x---" if is_dir else "rw-r-----"
        self.integrity_hash = None
        self.is_encrypted = False

class OperatingSystem:
    def __init__(self):
        self.disk = [DiskBlock() for _ in range(TOTAL_BLOCKS)]
        self.root = FileNode("/", is_dir=True)
        self.cwd = self.root
        self.disk[0].is_free = False
        self.disk[0].type = "INODE_DIR"
        self.disk[0].metadata_name = "/"
        self.root.inode_block_idx = 0

        self.auth = UserManager()
        self.mem = MemoryManager()
        self.current_user = "root"
        self.current_group = "admin"
        self.mode = "MODO_KERNEL"

    def _get_free_blocks(self, count):
        free = [i for i, b in enumerate(self.disk) if b.is_free]
        return free[:count] if len(free) >= count else None

    def resolve_path(self, path):
        if path == "/": return self.root
        curr = self.root if path.startswith("/") else self.cwd
        for p in [x for x in path.split("/") if x not in ("", ".")]:
            if p == "..": curr = curr.parent if curr.parent else curr
            elif p in curr.children: curr = curr.children[p]
            else: return None
        return curr

    def resolve_parent(self, path):
        parts = path.rsplit("/", 1)
        if len(parts) == 1: return self.cwd, parts[0]
        return self.resolve_path(parts[0] if parts[0] else "/"), parts[1]

    def get_full_path(self, node):
        if node == self.root: return "/"
        path = []
        while node != self.root:
            path.append(node.name)
            node = node.parent
        return "/" + "/".join(reversed(path))

    def check_permission(self, node, action):
        if self.current_user == "root": return True
        base = 0 if self.current_user == node.owner else (3 if self.current_group == node.group else 6)
        p = node.permissions
        ok = (action == 'r' and p[base] == 'r') or (action == 'w' and p[base+1] == 'w') or (action == 'x' and p[base+2] == 'x')
        if not ok:
            print(f"\n[NEGADO - ACL]: Usuário '{self.current_user}' sem permissão '{action}' em '{self.get_full_path(node)}'.\n")
        return ok

    def mkdir(self, path):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir or not self.check_permission(parent, 'w'): return
        blocks = self._get_free_blocks(1)
        if not blocks: return print("Erro: Disco cheio.")
        nd = FileNode(name, True, self.current_user, self.current_group, parent)
        nd.inode_block_idx = blocks[0]
        parent.children[name] = nd
        self.disk[blocks[0]].is_free = False
        self.disk[blocks[0]].type = "INODE_DIR"
        self.disk[blocks[0]].metadata_name = self.get_full_path(nd)

    def create(self, path, texto):
        parent, name = self.resolve_parent(path)
        if not parent or not parent.is_dir or not self.check_permission(parent, 'w'): return
        dados = texto.encode('utf-8')
        n_blocks = max(1, math.ceil(len(dados) / BLOCK_SIZE))
        blocks = self._get_free_blocks(1 + n_blocks)
        if not blocks: return print("Erro: Disco cheio.")
        nf = FileNode(name, False, self.current_user, self.current_group, parent)
        nf.size_bytes = len(dados)
        nf.inode_block_idx = blocks[0]
        parent.children[name] = nf
        self.disk[blocks[0]].is_free = False
        self.disk[blocks[0]].type = "INODE_FILE"
        self.disk[blocks[0]].references = blocks[1:]
        h = hashlib.sha256()
        offset = 0
        for idx in blocks[1:]:
            db = self.disk[idx]
            db.is_free = False
            db.type = "DATA"
            chunk = dados[offset:offset+BLOCK_SIZE]
            db.used_bytes = len(chunk)
            db.data[:len(chunk)] = chunk
            h.update(chunk)
            offset += len(chunk)
        nf.integrity_hash = h.hexdigest()

    def tree(self, node=None, prefix=""):
        if node is None:
            node = self.root
            print("\n[ÁRVORE DE DIRETÓRIOS]")
        items = list(node.children.values())
        for i, child in enumerate(items):
            is_last = (i == len(items) - 1)
            conn = "└── " if is_last else "├── "
            print(f"{prefix}{conn}{child.name}{'/' if child.is_dir else ''} ({child.owner} | {child.permissions})")
            if child.is_dir:
                self.tree(child, prefix + ("    " if is_last else "│   "))

# interface
def get_arg(parts, flag, default=None):
    if flag in parts:
        idx = parts.index(flag)
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return default

def start_shell():
    os_sim = OperatingSystem()
    os_sim.mkdir("/sistema")
    os_sim.create("/sistema/config.sys", "KERNEL_CONFIG_DATA")
    print("Simulador SO Completo (Etapas 1 a 4). Digite 'help' para ver os comandos da Etapa 4.")

    while True:
        try:
            prompt = f"[{os_sim.mode}] {os_sim.current_user}@{os_sim.get_full_path(os_sim.cwd)}> "
            cmd_input = input(prompt).strip()
            if not cmd_input: continue

            parts = shlex.split(cmd_input)
            cmd = parts[0].lower()

            if cmd in ["exit", "quit"]: break

            #gerenciamento de mem
            elif cmd == "create_process":
                name = get_arg(parts, "--name")
                size_str = get_arg(parts, "--size", "0").upper().replace("KB", "")
                ptype = get_arg(parts, "--type", "normal")
                if name and size_str:
                    os_sim.mem.create_process(name, float(size_str), ptype, os_sim.mode)
                else:
                    print("Uso: create_process --name <nome> --size <N>KB --type <critical|normal>")

            elif cmd == "terminate_process":
                name = get_arg(parts, "--name")
                if name: os_sim.mem.terminate_process(name, os_sim.mode)

            elif cmd == "memory_status":
                if "--reserved" in parts:
                    os_sim.mem.memory_status_reserved()
                elif "--virtual" in parts:
                    os_sim.mem.memory_status_virtual()
                else:
                    os_sim.mem.memory_status_reserved()
                    os_sim.mem.memory_status_virtual()

            elif cmd == "memory_compact" and "--reserved" in parts:
                os_sim.mem.compact_reserved(os_sim.mode)

            elif cmd == "translate_address":
                proc = get_arg(parts, "--process")
                page = get_arg(parts, "--page")
                if proc and page is not None:
                    os_sim.mem.translate_address(proc, int(page))

            elif cmd == "execute_step":
                proc = get_arg(parts, "--process")
                instr = get_arg(parts, "--instruction", "")
                #extrai o num da pag da instrução 
                page_tokens = [int(t) for t in instr.split() if t.isdigit()]
                if proc and page_tokens:
                    os_sim.mem.execute_step(proc, page_tokens[-1])
                else:
                    print('Uso: execute_step --process <nome> --instruction "LOAD_DATA Página <N>"')

            #cmd
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

            elif cmd == "tree": os_sim.tree()
            elif cmd == "help":
                print("\n--- Comandos Etapa 4 (Memória) ---")
                print('create_process --name "Nome" --size 512KB --type critical|normal')
                print('terminate_process --name "Nome"')
                print('memory_status --reserved | --virtual')
                print('memory_compact --reserved')
                print('translate_address --process Nome --page 1')
                print('execute_step --process Nome --instruction "LOAD_DATA Página 2"')
                print('login --user root|carlos (senhas: toor / 1234)\n')
            else:
                print("Comando inválido. Digite 'help'.")
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    start_shell()